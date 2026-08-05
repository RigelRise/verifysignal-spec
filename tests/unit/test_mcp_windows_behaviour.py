from __future__ import annotations

import signal
import subprocess

from verifysignal_spec.integrations import mcp
from verifysignal_spec.integrations.mcp import register_agent_user_mcp


class _Runner:
    def __init__(self, responses: list[subprocess.CompletedProcess[str]]) -> None:
        self.responses = list(responses)
        self.calls: list[list[str]] = []

    def __call__(self, command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        self.calls.append(command)
        assert self.responses, f"unexpected agent command: {command}"
        response = self.responses.pop(0)
        response.args = command
        return response


def _result(returncode: int, *, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def _claude_managed_server() -> str:
    return (
        "playwright:\n"
        "  Scope: User config\n"
        "  Type: stdio\n"
        "  Command: verifysignal\n"
        "  Args: integration playwright-mcp\n"
    )


# A real user hit `agent-mcp.inspect-failed` on `verifysignal init` and was told to go fix an agent
# configuration that was fine. The classifier decided between "missing" and "hard block" by looking
# for English prose from another tool's output.
def test_an_unfamiliar_refusal_registers_instead_of_blocking(monkeypatch) -> None:
    monkeypatch.delenv(mcp.PLAYWRIGHT_MCP_CACHE_ENV, raising=False)
    runner = _Runner(
        [
            # Not "no mcp server named", not "not found". Any rewording, any newer agent version, or
            # any localized build produced exactly this shape — and the old rule called it fatal.
            _result(1, stderr="Server 'playwright' is not configured in user scope."),
            _result(0, stdout="Added user MCP server 'playwright'."),
            _result(0, stdout=_claude_managed_server()),
        ]
    )

    result = register_agent_user_mcp("claude", agent_command="/tools/claude", command_runner=runner)

    assert result["status"] == "ready"
    assert result["added"] == ["playwright"]


def test_an_agent_that_cannot_answer_is_still_a_hard_block(monkeypatch) -> None:
    # `error` is reserved for "the agent did not answer at all" — the runner raising OSError or
    # timing out. That is a genuine dead end, unlike a non-zero exit we can act on.
    monkeypatch.delenv(mcp.PLAYWRIGHT_MCP_CACHE_ENV, raising=False)

    def unusable(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise OSError("agent binary is not executable")

    result = register_agent_user_mcp("claude", agent_command="/tools/claude", command_runner=unusable)

    assert result["status"] == "blocked"
    assert result["code"] == "agent-mcp.inspect-failed"
    # Name the command that ACTUALLY failed, not a different one.
    assert "mcp get playwright" in result["nextAction"]


def test_a_broken_agent_degrades_into_the_accurate_blocker(monkeypatch) -> None:
    # Treating a non-zero exit as "missing" is safe precisely because the ADD then fails and reports
    # the truthful blocker, rather than this code guessing at which failure it was.
    monkeypatch.delenv(mcp.PLAYWRIGHT_MCP_CACHE_ENV, raising=False)
    runner = _Runner(
        [
            _result(1, stderr="config parse error at line 3"),
            _result(1, stderr="config parse error at line 3"),
        ]
    )

    result = register_agent_user_mcp("claude", agent_command="/tools/claude", command_runner=runner)

    assert result["status"] == "blocked"
    assert result["code"] == "agent-mcp.registration-failed"


def test_child_exit_codes_stay_in_range_on_both_platforms() -> None:
    # POSIX reports a signalled child as a NEGATIVE return code.
    assert mcp._exit_code_for(-signal.SIGINT) == 128 + int(signal.SIGINT)
    assert mcp._exit_code_for(0) == 0
    assert mcp._exit_code_for(3) == 3

    # Windows never does. A Ctrl-C'd child exits with STATUS_CONTROL_C_EXIT, so the negative branch
    # was dead there and this raw NTSTATUS leaked out as the CLI's exit code.
    assert mcp._exit_code_for(0xC000013A) == 130
    assert mcp._exit_code_for(0xC0000005) == 139
    # Anything else out of range becomes a plain failure rather than a truncated nonsense byte.
    assert mcp._exit_code_for(0xDEADBEEF) == 1


def test_stopping_the_child_uses_what_the_host_supports(monkeypatch) -> None:
    class _Process:
        def __init__(self) -> None:
            self.signals: list[int] = []
            self.terminated = False

        def send_signal(self, signum: int) -> None:
            # Popen.send_signal on Windows accepts only SIGTERM, CTRL_C_EVENT and CTRL_BREAK_EVENT;
            # SIGINT raises. Reproducing that here is what makes this test meaningful off-Windows.
            if signum == int(signal.SIGINT):
                raise ValueError("Unsupported signal: 2")
            self.signals.append(signum)

        def terminate(self) -> None:
            self.terminated = True

    monkeypatch.setattr(mcp.os, "name", "nt")
    windows_child = _Process()
    mcp._stop_child(windows_child, int(signal.SIGINT))
    assert windows_child.terminated is True
    assert windows_child.signals == []

    monkeypatch.setattr(mcp.os, "name", "posix")
    posix_child = _Process()
    mcp._stop_child(posix_child, int(signal.SIGTERM))
    assert posix_child.signals == [int(signal.SIGTERM)]
    assert posix_child.terminated is False
