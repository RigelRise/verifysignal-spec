from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import tomllib

import pytest

from helpers import CliTestCase, FAKE_CORE
from verifysignal_spec import cli
from verifysignal_spec.integrations.claude import ClaudeIntegration
from verifysignal_spec.integrations.codex import CodexIntegration

from verifysignal_spec.integrations.mcp import (
    LEGACY_PLAYWRIGHT_MCP_SERVER,
    PLAYWRIGHT_MCP_PACKAGE,
    PLAYWRIGHT_MCP_SERVER,
    ensure_playwright_mcp_runtime,
    merge_codex_mcp_servers,
    merge_mcp_servers,
    register_agent_user_mcp,
    run_playwright_mcp,
)


def _read_mcp(project) -> dict:
    return json.loads((project / ".mcp.json").read_text(encoding="utf-8"))


def _read_codex_mcp(project) -> dict:
    return tomllib.loads((project / ".codex" / "config.toml").read_text(encoding="utf-8"))


class _AgentCommandRunner:
    def __init__(
        self,
        responses: list[subprocess.CompletedProcess[str]],
    ) -> None:
        self.responses = list(responses)
        self.calls: list[list[str]] = []

    def __call__(
        self,
        command: list[str],
        **_kwargs,
    ) -> subprocess.CompletedProcess[str]:
        self.calls.append(command)
        assert self.responses, f"unexpected agent command: {command}"
        response = self.responses.pop(0)
        response.args = command
        return response


def _command_result(
    returncode: int,
    *,
    stdout: str = "",
    stderr: str = "",
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=[],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


def _codex_managed_server_json(
    *,
    command: str = "verifysignal",
    args: list[str] | None = None,
) -> str:
    return json.dumps(
        {
            "name": "playwright",
            "enabled": True,
            "transport": {
                "type": "stdio",
                "command": command,
                "args": args or ["integration", "playwright-mcp"],
                "env": None,
                "env_vars": [],
                "cwd": None,
            },
        }
    )


def test_codex_user_mcp_registration_uses_public_global_command() -> None:
    runner = _AgentCommandRunner(
        [
            _command_result(1, stderr="No MCP server named 'playwright' found."),
            _command_result(0, stdout="Added global MCP server 'playwright'."),
            _command_result(0, stdout=_codex_managed_server_json()),
        ]
    )

    result = register_agent_user_mcp(
        "codex",
        agent_command="/tools/codex",
        command_runner=runner,
    )

    assert result["status"] == "ready"
    assert result["scope"] == "user"
    assert result["added"] == ["playwright"]
    assert runner.calls == [
        ["/tools/codex", "mcp", "get", "playwright", "--json"],
        [
            "/tools/codex",
            "mcp",
            "add",
            "playwright",
            "--",
            "verifysignal",
            "integration",
            "playwright-mcp",
        ],
        ["/tools/codex", "mcp", "get", "playwright", "--json"],
    ]


def test_codex_user_mcp_registration_is_idempotent() -> None:
    runner = _AgentCommandRunner(
        [_command_result(0, stdout=_codex_managed_server_json())]
    )

    result = register_agent_user_mcp(
        "codex",
        agent_command="/tools/codex",
        command_runner=runner,
    )

    assert result["status"] == "ready"
    assert result["unchanged"] is True
    assert result["managedServers"] == ["playwright"]
    assert len(runner.calls) == 1


def test_codex_user_mcp_registration_preserves_conflicting_server() -> None:
    runner = _AgentCommandRunner(
        [
            _command_result(
                0,
                stdout=_codex_managed_server_json(
                    command="custom-playwright",
                    args=["--user-owned"],
                ),
            )
        ]
    )

    result = register_agent_user_mcp(
        "codex",
        agent_command="/tools/codex",
        command_runner=runner,
    )

    assert result["status"] == "blocked"
    assert result["code"] == "agent-mcp.conflict"
    assert result["preserved"] == ["playwright"]
    assert len(runner.calls) == 1


def test_claude_user_mcp_registration_uses_explicit_user_scope() -> None:
    runner = _AgentCommandRunner(
        [
            _command_result(1, stderr='No MCP server named "playwright".'),
            _command_result(0, stdout="Added stdio MCP server playwright."),
            _command_result(
                0,
                stdout=(
                    "playwright:\n"
                    "  Scope: User config\n"
                    "  Type: stdio\n"
                    "  Command: verifysignal\n"
                    "  Args: integration playwright-mcp\n"
                ),
            ),
        ]
    )

    result = register_agent_user_mcp(
        "claude",
        agent_command="/tools/claude",
        command_runner=runner,
    )

    assert result["status"] == "ready"
    assert result["added"] == ["playwright"]
    assert runner.calls[1] == [
        "/tools/claude",
        "mcp",
        "add",
        "--scope",
        "user",
        "playwright",
        "--",
        "verifysignal",
        "integration",
        "playwright-mcp",
    ]


def test_claude_user_mcp_registration_is_idempotent() -> None:
    runner = _AgentCommandRunner(
        [
            _command_result(
                0,
                stdout=(
                    "playwright:\n"
                    "  Scope: User config\n"
                    "  Type: stdio\n"
                    "  Command: verifysignal\n"
                    "  Args: integration playwright-mcp\n"
                ),
            )
        ]
    )

    result = register_agent_user_mcp(
        "claude",
        agent_command="/tools/claude",
        command_runner=runner,
    )

    assert result["status"] == "ready"
    assert result["unchanged"] is True
    assert result["managedServers"] == ["playwright"]
    assert len(runner.calls) == 1


def test_claude_user_mcp_registration_preserves_conflicting_server() -> None:
    runner = _AgentCommandRunner(
        [
            _command_result(
                0,
                stdout=(
                    "playwright:\n"
                    "  Scope: User config\n"
                    "  Type: stdio\n"
                    "  Command: custom-playwright\n"
                    "  Args: --user-owned\n"
                ),
            )
        ]
    )

    result = register_agent_user_mcp(
        "claude",
        agent_command="/tools/claude",
        command_runner=runner,
    )

    assert result["status"] == "blocked"
    assert result["code"] == "agent-mcp.conflict"
    assert result["preserved"] == ["playwright"]
    assert len(runner.calls) == 1


def test_agent_user_mcp_registration_blocks_when_agent_is_missing(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "verifysignal_spec.integrations.mcp.shutil.which",
        lambda _name: None,
    )

    result = register_agent_user_mcp("codex")

    assert result["status"] == "blocked"
    assert result["code"] == "agent.command-missing"
    assert result["nextAction"] == "Install Codex and rerun the same command."


def test_merge_creates_mcp_json_when_absent(tmp_path) -> None:
    result = merge_mcp_servers(tmp_path, {"playwright": PLAYWRIGHT_MCP_SERVER})

    assert result["skipped"] is False
    assert "playwright" in result["added"]
    data = _read_mcp(tmp_path)
    assert data["mcpServers"]["playwright"]["command"] == "verifysignal"
    assert data["mcpServers"]["playwright"]["args"] == [
        "integration",
        "playwright-mcp",
    ]


def test_merge_preserves_unrelated_servers(tmp_path) -> None:
    (tmp_path / ".mcp.json").write_text(
        json.dumps({"mcpServers": {"foo": {"command": "foo-server"}}}), encoding="utf-8"
    )

    result = merge_mcp_servers(tmp_path, {"playwright": PLAYWRIGHT_MCP_SERVER})

    assert result["skipped"] is False
    data = _read_mcp(tmp_path)
    assert "foo" in data["mcpServers"]
    assert "playwright" in data["mcpServers"]
    assert "foo" in result["preserved"]


def test_merge_is_idempotent(tmp_path) -> None:
    merge_mcp_servers(tmp_path, {"playwright": PLAYWRIGHT_MCP_SERVER})
    second = merge_mcp_servers(tmp_path, {"playwright": PLAYWRIGHT_MCP_SERVER})

    assert second["unchanged"] is True
    assert second["added"] == []


def test_merge_does_not_clobber_malformed_file(tmp_path) -> None:
    (tmp_path / ".mcp.json").write_text("{not valid json", encoding="utf-8")

    result = merge_mcp_servers(tmp_path, {"playwright": PLAYWRIGHT_MCP_SERVER})

    assert result["skipped"] is True
    # The user's file is left exactly as-is — we never destroy what we cannot safely merge.
    assert (tmp_path / ".mcp.json").read_text(encoding="utf-8") == "{not valid json"


def test_merge_reports_node_missing_but_still_writes(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("verifysignal_spec.integrations.mcp.shutil.which", lambda _name: None)

    result = merge_mcp_servers(tmp_path, {"playwright": PLAYWRIGHT_MCP_SERVER})

    assert result["nodeAvailable"] is False
    # Config is still written so it is ready the moment Node is installed.
    assert (tmp_path / ".mcp.json").exists()


def test_codex_merge_creates_project_config_when_absent(tmp_path) -> None:
    result = merge_codex_mcp_servers(tmp_path, {"playwright": PLAYWRIGHT_MCP_SERVER})

    assert result["path"] == ".codex/config.toml"
    assert result["integrationKey"] == "codex"
    assert result["skipped"] is False
    assert result["added"] == ["playwright"]
    data = _read_codex_mcp(tmp_path)
    assert data["mcp_servers"]["playwright"]["command"] == "verifysignal"
    assert data["mcp_servers"]["playwright"]["args"] == [
        "integration",
        "playwright-mcp",
    ]


def test_codex_managed_playwright_is_required_but_claude_entry_is_not(
    tmp_path,
) -> None:
    codex_server = CodexIntegration().mcp_servers()["playwright"]
    claude_server = ClaudeIntegration().mcp_servers()["playwright"]

    assert codex_server["required"] is True
    assert "required" not in claude_server

    result = merge_codex_mcp_servers(
        tmp_path,
        {"playwright": codex_server},
    )

    assert result["added"] == ["playwright"]
    assert _read_codex_mcp(tmp_path)["mcp_servers"]["playwright"] == {
        "command": "verifysignal",
        "args": ["integration", "playwright-mcp"],
        "required": True,
    }


def test_codex_merge_upgrades_the_exact_pre_required_managed_entry(
    tmp_path,
) -> None:
    config = tmp_path / ".codex" / "config.toml"
    config.parent.mkdir(parents=True)
    config.write_text(
        """# managed by an earlier VerifySignal build
[mcp_servers.playwright]
command = "verifysignal"
args = ["integration", "playwright-mcp"]
""",
        encoding="utf-8",
    )

    result = merge_codex_mcp_servers(
        tmp_path,
        CodexIntegration().mcp_servers(),
    )

    assert result["updated"] == ["playwright"]
    assert result["managedServers"] == ["playwright"]
    assert "# managed by an earlier VerifySignal build" in config.read_text(
        encoding="utf-8"
    )
    assert _read_codex_mcp(tmp_path)["mcp_servers"]["playwright"][
        "required"
    ] is True


def test_codex_merge_preserves_user_owned_required_override(
    tmp_path,
) -> None:
    config = tmp_path / ".codex" / "config.toml"
    config.parent.mkdir(parents=True)
    original = """[mcp_servers.playwright]
command = "verifysignal"
args = ["integration", "playwright-mcp"]
required = false
"""
    config.write_text(original, encoding="utf-8")

    result = merge_codex_mcp_servers(
        tmp_path,
        CodexIntegration().mcp_servers(),
    )

    assert result["updated"] == []
    assert result["preserved"] == ["playwright"]
    assert result["warnings"]
    assert config.read_text(encoding="utf-8") == original


def test_codex_merge_preserves_comments_unrelated_config_and_custom_playwright(tmp_path) -> None:
    config = tmp_path / ".codex" / "config.toml"
    config.parent.mkdir(parents=True)
    original = """# keep this project setting
model = "gpt-5.6"

[mcp_servers.docs]
command = "docs-mcp"

[mcp_servers.playwright]
command = "npx"
args = ["@playwright/mcp", "--isolated"]
"""
    config.write_text(original, encoding="utf-8")

    result = merge_codex_mcp_servers(tmp_path, {"playwright": PLAYWRIGHT_MCP_SERVER})

    assert result["added"] == []
    assert result["preserved"] == ["docs", "playwright"]
    assert result["unchanged"] is True
    assert config.read_text(encoding="utf-8") == original


def test_codex_merge_is_idempotent_and_preserves_unrelated_server(tmp_path) -> None:
    config = tmp_path / ".codex" / "config.toml"
    config.parent.mkdir(parents=True)
    config.write_text(
        """# user comment
[mcp_servers.docs]
command = "docs-mcp"
""",
        encoding="utf-8",
    )

    first = merge_codex_mcp_servers(tmp_path, {"playwright": PLAYWRIGHT_MCP_SERVER})
    first_content = config.read_text(encoding="utf-8")
    second = merge_codex_mcp_servers(tmp_path, {"playwright": PLAYWRIGHT_MCP_SERVER})

    assert first["added"] == ["playwright"]
    assert "docs" in first["preserved"]
    assert "# user comment" in first_content
    assert second["unchanged"] is True
    assert second["added"] == []
    assert config.read_text(encoding="utf-8") == first_content


def test_codex_merge_does_not_clobber_malformed_toml(tmp_path) -> None:
    config = tmp_path / ".codex" / "config.toml"
    config.parent.mkdir(parents=True)
    config.write_text("[mcp_servers.playwright\nbroken", encoding="utf-8")

    result = merge_codex_mcp_servers(tmp_path, {"playwright": PLAYWRIGHT_MCP_SERVER})

    assert result["skipped"] is True
    assert "valid TOML" in result["reason"]
    assert config.read_text(encoding="utf-8") == "[mcp_servers.playwright\nbroken"


def test_claude_merge_migrates_exact_legacy_entry(tmp_path) -> None:
    (tmp_path / ".mcp.json").write_text(
        json.dumps(
            {"mcpServers": {"playwright": LEGACY_PLAYWRIGHT_MCP_SERVER}}
        ),
        encoding="utf-8",
    )

    result = merge_mcp_servers(
        tmp_path, {"playwright": PLAYWRIGHT_MCP_SERVER}
    )

    assert result["updated"] == ["playwright"]
    assert _read_mcp(tmp_path)["mcpServers"]["playwright"] == (
        PLAYWRIGHT_MCP_SERVER
    )


def test_claude_merge_preserves_custom_playwright_entry(tmp_path) -> None:
    custom = {
        "type": "stdio",
        "command": "custom-playwright",
        "args": ["--user-owned"],
    }
    original = json.dumps({"mcpServers": {"playwright": custom}}, indent=2)
    (tmp_path / ".mcp.json").write_text(original, encoding="utf-8")

    result = merge_mcp_servers(
        tmp_path, {"playwright": PLAYWRIGHT_MCP_SERVER}
    )

    assert result["unchanged"] is True
    assert result["updated"] == []
    assert result["preserved"] == ["playwright"]
    assert result["warnings"]
    assert (tmp_path / ".mcp.json").read_text(encoding="utf-8") == original


def test_codex_merge_migrates_exact_legacy_entry_and_preserves_comments(
    tmp_path,
) -> None:
    config = tmp_path / ".codex" / "config.toml"
    config.parent.mkdir(parents=True)
    config.write_text(
        """# keep
[mcp_servers.playwright]
command = "npx"
args = ["-y", "@playwright/mcp@latest"]
""",
        encoding="utf-8",
    )

    result = merge_codex_mcp_servers(
        tmp_path, {"playwright": PLAYWRIGHT_MCP_SERVER}
    )

    assert result["updated"] == ["playwright"]
    assert "# keep" in config.read_text(encoding="utf-8")
    assert _read_codex_mcp(tmp_path)["mcp_servers"]["playwright"] == {
        "command": "verifysignal",
        "args": ["integration", "playwright-mcp"],
    }


def _fake_mcp_provider(
    root: Path,
    *,
    exit_code: int = 0,
    wait_for_signal: bool = False,
) -> tuple[Path, Path]:
    executable = root / "playwright-mcp"
    record = root / "record.json"
    loop = (
        """
import signal
import time
signal.signal(signal.SIGINT, lambda *_: raise_exit(130))
signal.signal(signal.SIGTERM, lambda *_: raise_exit(143))
while True:
    time.sleep(0.05)
"""
        if wait_for_signal
        else f"raise SystemExit({exit_code})\n"
    )
    executable.write_text(
        f"""#!{sys.executable}
import json
import os
from pathlib import Path
import stat
import sys

def raise_exit(code):
    raise SystemExit(code)

cwd = Path.cwd()
(cwd / ".playwright-mcp").mkdir(exist_ok=True)
(cwd / ".playwright-mcp" / "snapshot.yml").write_text("raw snapshot", encoding="utf-8")
Path(os.environ["FAKE_MCP_RECORD"]).write_text(
    json.dumps({{
        "cwd": str(cwd),
        "mode": stat.S_IMODE(cwd.stat().st_mode),
        "args": sys.argv[1:],
    }}),
    encoding="utf-8",
)
{loop}
""",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    return executable, record


def _fake_npm_with_mcp_provider(root: Path) -> tuple[Path, Path]:
    executable = root / "npm"
    record = root / "npm-record.json"
    provider = f"""#!{sys.executable}
import json
import sys

for raw_line in sys.stdin:
    message = json.loads(raw_line)
    request_id = message.get("id")
    method = message.get("method")
    if method == "initialize":
        response = {{
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {{
                "protocolVersion": "2025-06-18",
                "capabilities": {{"tools": {{}}}},
                "serverInfo": {{"name": "Playwright", "version": "test"}},
            }},
        }}
    elif method == "tools/list":
        response = {{
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {{
                "tools": [
                    {{"name": "browser_navigate"}},
                    {{"name": "browser_snapshot"}},
                ]
            }},
        }}
    else:
        continue
    sys.stdout.write(json.dumps(response) + "\\n")
    sys.stdout.flush()
"""
    executable.write_text(
        f"""#!{sys.executable}
import json
import os
from pathlib import Path
import sys

args = sys.argv[1:]
prefix = Path(args[args.index("--prefix") + 1])
package = prefix / "node_modules" / "@playwright" / "mcp"
binary = prefix / "node_modules" / ".bin" / "playwright-mcp"
package.mkdir(parents=True)
binary.parent.mkdir(parents=True)
(package / "package.json").write_text(
    json.dumps({{"name": "@playwright/mcp", "version": "0.0.78"}}),
    encoding="utf-8",
)
binary.write_text({provider!r}, encoding="utf-8")
binary.chmod(0o755)
Path(os.environ["FAKE_NPM_RECORD"]).write_text(
    json.dumps({{"args": args, "prefix": str(prefix)}}),
    encoding="utf-8",
)
""",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    return executable, record


def _mcp_handshake(
    command: list[str],
    *,
    cwd: Path,
    environment: dict[str, str],
    timeout: float = 10,
) -> list[dict]:
    requests = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {
                    "name": "verifysignal-regression-test",
                    "version": "1",
                },
            },
        },
        {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
        },
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {},
        },
    ]
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=environment,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    payload = "".join(json.dumps(item) + "\n" for item in requests)
    try:
        stdout, stderr = process.communicate(payload, timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        stdout, stderr = process.communicate()
        pytest.fail(
            "Playwright MCP did not complete initialize/tools-list within "
            f"{timeout}s. stdout={stdout!r} stderr={stderr!r}"
        )
    assert process.returncode == 0, stderr
    return [
        json.loads(line)
        for line in stdout.splitlines()
        if line.strip()
    ]


def test_managed_playwright_runtime_installs_once_then_is_offline_ready(
    tmp_path, monkeypatch
) -> None:
    cache = tmp_path / "mcp-cache"
    fake_npm, record = _fake_npm_with_mcp_provider(tmp_path)
    monkeypatch.setenv("FAKE_NPM_RECORD", str(record))

    first = ensure_playwright_mcp_runtime(
        npm_command=str(fake_npm),
        cache_root=cache,
    )
    fake_npm.unlink()
    second = ensure_playwright_mcp_runtime(
        npm_command=str(fake_npm),
        cache_root=cache,
    )

    assert first["status"] == "ready"
    assert first["source"] == "managed-install"
    assert second["status"] == "ready"
    assert second["source"] == "managed-cache"
    assert second["executable"] == first["executable"]
    observed = json.loads(record.read_text(encoding="utf-8"))
    assert observed["args"][-1] == PLAYWRIGHT_MCP_PACKAGE
    assert "--prefix" in observed["args"]


def test_managed_cli_launcher_completes_real_mcp_handshake_without_npx(
    tmp_path, monkeypatch
) -> None:
    cache = tmp_path / "mcp-cache"
    fake_npm, record = _fake_npm_with_mcp_provider(tmp_path)
    monkeypatch.setenv("FAKE_NPM_RECORD", str(record))
    runtime = ensure_playwright_mcp_runtime(
        npm_command=str(fake_npm),
        cache_root=cache,
    )
    fake_npm.unlink()
    environment = dict(os.environ)
    environment["VERIFYSIGNAL_PLAYWRIGHT_MCP_CACHE_DIR"] = str(cache)
    source_root = Path(__file__).resolve().parents[2] / "src"
    environment["PYTHONPATH"] = os.pathsep.join(
        filter(
            None,
            [str(source_root), environment.get("PYTHONPATH", "")],
        )
    )
    command = [
        sys.executable,
        "-c",
        (
            "from verifysignal_spec.cli import main; "
            "raise SystemExit(main(['integration', 'playwright-mcp']))"
        ),
    ]

    messages = _mcp_handshake(
        command,
        cwd=tmp_path,
        environment=environment,
    )

    assert Path(runtime["executable"]).is_file()
    initialize = next(item for item in messages if item.get("id") == 1)
    tools = next(item for item in messages if item.get("id") == 2)
    assert initialize["result"]["serverInfo"]["name"] == "Playwright"
    assert {item["name"] for item in tools["result"]["tools"]} >= {
        "browser_navigate",
        "browser_snapshot",
    }


@pytest.mark.skipif(
    os.environ.get("VERIFYSIGNAL_RUN_REAL_MCP_TESTS") != "1",
    reason="real pinned Playwright MCP acceptance is enabled explicitly in CI",
)
def test_pinned_playwright_provider_initialize_and_tools_list(
    tmp_path,
) -> None:
    cache = Path(
        os.environ.get(
            "VERIFYSIGNAL_PLAYWRIGHT_MCP_CACHE_DIR",
            str(tmp_path / "real-mcp-cache"),
        )
    )
    runtime = ensure_playwright_mcp_runtime(cache_root=cache)
    assert runtime["status"] == "ready", runtime
    environment = dict(os.environ)
    environment["VERIFYSIGNAL_PLAYWRIGHT_MCP_CACHE_DIR"] = str(cache)
    source_root = Path(__file__).resolve().parents[2] / "src"
    environment["PYTHONPATH"] = os.pathsep.join(
        filter(
            None,
            [str(source_root), environment.get("PYTHONPATH", "")],
        )
    )

    messages = _mcp_handshake(
        [
            sys.executable,
            "-c",
            (
                "from verifysignal_spec.cli import main; "
                "raise SystemExit(main(['integration', 'playwright-mcp']))"
            ),
        ],
        cwd=tmp_path,
        environment=environment,
        timeout=45,
    )

    initialize = next(item for item in messages if item.get("id") == 1)
    tools = next(item for item in messages if item.get("id") == 2)
    assert initialize["result"]["serverInfo"]["name"] == "Playwright"
    assert {item["name"] for item in tools["result"]["tools"]} >= {
        "browser_navigate",
        "browser_snapshot",
    }


def test_playwright_launcher_uses_private_temporary_cwd_and_cleans_outputs(
    tmp_path, monkeypatch
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    fake_provider, record = _fake_mcp_provider(tmp_path)
    monkeypatch.setenv("FAKE_MCP_RECORD", str(record))
    monkeypatch.chdir(project)

    code = run_playwright_mcp(provider_command=str(fake_provider))

    assert code == 0
    observed = json.loads(record.read_text(encoding="utf-8"))
    assert observed["mode"] == 0o700
    assert PLAYWRIGHT_MCP_PACKAGE not in observed["args"]
    assert "--isolated" in observed["args"]
    assert "--output-dir" in observed["args"]
    assert not Path(observed["cwd"]).exists()
    assert not (project / ".playwright-mcp").exists()


def test_playwright_launcher_cleans_temporary_outputs_after_child_failure(
    tmp_path, monkeypatch
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    fake_provider, record = _fake_mcp_provider(tmp_path, exit_code=7)
    monkeypatch.setenv("FAKE_MCP_RECORD", str(record))
    monkeypatch.chdir(project)

    code = run_playwright_mcp(provider_command=str(fake_provider))

    assert code == 7
    observed = json.loads(record.read_text(encoding="utf-8"))
    assert not Path(observed["cwd"]).exists()
    assert not (project / ".playwright-mcp").exists()


def test_cli_routes_playwright_mcp_without_json_emission(monkeypatch) -> None:
    monkeypatch.setattr(
        "verifysignal_spec.commands.integration.playwright_mcp",
        lambda: 23,
    )

    assert cli.main(["integration", "playwright-mcp"]) == 23


def test_setup_playwright_mcp_command_reports_offline_ready(
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setattr(
        "verifysignal_spec.commands.integration.setup_playwright_mcp",
        lambda: {
            "status": "ready",
            "source": "managed-install",
            "offlineReady": True,
        },
    )

    assert (
        cli.main(["integration", "setup-playwright-mcp", "--json"])
        == 0
    )
    assert json.loads(capsys.readouterr().out) == {
        "status": "ready",
        "source": "managed-install",
        "offlineReady": True,
    }


def test_codex_init_prepares_managed_mcp_before_new_agent_session(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    prepared = {
        "status": "ready",
        "source": "managed-install",
        "offlineReady": True,
        "executable": "/managed/playwright-mcp",
    }
    monkeypatch.setenv("VERIFYSIGNAL_CORE_CMD", str(FAKE_CORE))
    monkeypatch.setenv(
        "VERIFYSIGNAL_PLAYWRIGHT_MCP_AUTO_INSTALL",
        "1",
    )
    monkeypatch.setenv(
        "VERIFYSIGNAL_AGENT_MCP_AUTO_REGISTER",
        "1",
    )
    monkeypatch.setattr(
        "verifysignal_spec.commands.integration.ensure_playwright_mcp_runtime",
        lambda: prepared,
    )
    registered = {
        "status": "ready",
        "scope": "user",
        "integrationKey": "codex",
        "serverName": "playwright",
        "added": ["playwright"],
        "preserved": [],
        "managedServers": ["playwright"],
        "unchanged": False,
        "nextAction": None,
    }
    monkeypatch.setattr(
        "verifysignal_spec.commands.integration.register_agent_user_mcp",
        lambda _integration: registered,
    )

    code = cli.main(
        [
            "init",
            str(tmp_path),
            "--integration",
            "codex",
            "--json",
        ]
    )

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["mcp"]["runtime"] == prepared
    assert payload["mcp"]["managedServers"] == ["playwright"]
    assert payload["mcp"]["userRegistration"] == registered


def test_codex_init_blocks_before_agent_when_provider_setup_fails(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    blocked = {
        "status": "blocked",
        "source": "managed-install",
        "offlineReady": False,
        "message": "provider setup failed",
        "nextAction": (
            "verifysignal integration setup-playwright-mcp --json"
        ),
    }
    monkeypatch.setenv("VERIFYSIGNAL_CORE_CMD", str(FAKE_CORE))
    monkeypatch.setenv(
        "VERIFYSIGNAL_PLAYWRIGHT_MCP_AUTO_INSTALL",
        "1",
    )
    monkeypatch.setattr(
        "verifysignal_spec.commands.integration.ensure_playwright_mcp_runtime",
        lambda: blocked,
    )

    code = cli.main(
        [
            "init",
            str(tmp_path),
            "--integration",
            "codex",
            "--json",
        ]
    )

    assert code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "blocked"
    assert payload["mcp"]["runtime"] == blocked
    assert payload["next"] == blocked["nextAction"]


def test_codex_init_blocks_before_agent_when_user_registration_fails(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    prepared = {
        "status": "ready",
        "source": "managed-cache",
        "offlineReady": True,
        "executable": "/managed/playwright-mcp",
    }
    registration = {
        "status": "blocked",
        "scope": "user",
        "integrationKey": "codex",
        "serverName": "playwright",
        "code": "agent-mcp.conflict",
        "message": "user-owned conflict",
        "nextAction": "Review the existing user-scoped MCP server.",
    }
    monkeypatch.setenv("VERIFYSIGNAL_CORE_CMD", str(FAKE_CORE))
    monkeypatch.setenv(
        "VERIFYSIGNAL_PLAYWRIGHT_MCP_AUTO_INSTALL",
        "1",
    )
    monkeypatch.setenv(
        "VERIFYSIGNAL_AGENT_MCP_AUTO_REGISTER",
        "1",
    )
    monkeypatch.setattr(
        "verifysignal_spec.commands.integration.ensure_playwright_mcp_runtime",
        lambda: prepared,
    )
    monkeypatch.setattr(
        "verifysignal_spec.commands.integration.register_agent_user_mcp",
        lambda _integration: registration,
    )

    code = cli.main(
        [
            "init",
            str(tmp_path),
            "--integration",
            "codex",
            "--json",
        ]
    )

    assert code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "blocked"
    assert payload["mcp"]["runtime"] == prepared
    assert payload["mcp"]["userRegistration"] == registration
    assert payload["next"] == registration["nextAction"]


@pytest.mark.parametrize(
    "integration_args",
    [
        ["integration", "install", "codex"],
        ["integration", "upgrade", "codex"],
    ],
)
def test_integration_commands_fail_when_user_registration_is_blocked(
    integration_args,
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    prepared = {
        "status": "ready",
        "source": "managed-cache",
        "offlineReady": True,
        "executable": "/managed/playwright-mcp",
    }
    registration = {
        "status": "blocked",
        "scope": "user",
        "integrationKey": "codex",
        "serverName": "playwright",
        "code": "agent-mcp.conflict",
        "message": "user-owned conflict",
        "nextAction": "Review the existing user-scoped MCP server.",
    }
    monkeypatch.setenv("VERIFYSIGNAL_CORE_CMD", str(FAKE_CORE))
    monkeypatch.setenv(
        "VERIFYSIGNAL_PLAYWRIGHT_MCP_AUTO_INSTALL",
        "1",
    )
    monkeypatch.setenv(
        "VERIFYSIGNAL_AGENT_MCP_AUTO_REGISTER",
        "1",
    )
    monkeypatch.setattr(
        "verifysignal_spec.commands.integration.ensure_playwright_mcp_runtime",
        lambda: prepared,
    )
    monkeypatch.setattr(
        "verifysignal_spec.commands.integration.register_agent_user_mcp",
        lambda _integration: registration,
    )

    code = cli.main(
        [
            *integration_args,
            "--project",
            str(tmp_path),
            "--json",
        ]
    )

    assert code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "blocked"
    installed = (
        payload["upgraded"][0]
        if "upgraded" in payload
        else payload
    )
    assert installed["status"] == "blocked"
    assert installed["mcp"]["userRegistration"] == registration


def test_playwright_launcher_without_managed_runtime_fails_fast(
    tmp_path,
    capsys,
) -> None:
    started = time.monotonic()

    code = run_playwright_mcp(cache_root=tmp_path / "empty-cache")

    assert code == 78
    assert time.monotonic() - started < 1
    assert "setup-playwright-mcp" in capsys.readouterr().err


def test_human_mcp_output_reports_preserved_custom_configuration(
    capsys,
) -> None:
    warning = (
        "Preserved user-owned MCP server 'playwright' because it differs "
        "from the exact legacy VerifySignal entry."
    )

    cli._emit_mcp(
        {
            "path": ".codex/config.toml",
            "integrationKey": "codex",
            "unchanged": True,
            "skipped": False,
            "nodeAvailable": True,
            "warnings": [warning],
        }
    )

    output = capsys.readouterr().out
    assert "left unchanged" in output
    assert "written" not in output
    assert warning in output


@pytest.mark.parametrize("termination_signal", [signal.SIGINT, signal.SIGTERM])
def test_playwright_launcher_forwards_signals_and_cleans_temporary_outputs(
    tmp_path, termination_signal
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    fake_provider, record = _fake_mcp_provider(
        tmp_path,
        wait_for_signal=True,
    )
    environment = dict(os.environ)
    environment["FAKE_MCP_RECORD"] = str(record)
    code = (
        "from verifysignal_spec.integrations.mcp import run_playwright_mcp; "
        "raise SystemExit(run_playwright_mcp("
        f"provider_command={str(fake_provider)!r}))"
    )
    process = subprocess.Popen(
        [sys.executable, "-c", code],
        cwd=project,
        env=environment,
    )
    deadline = time.monotonic() + 5
    while not record.exists() and time.monotonic() < deadline:
        time.sleep(0.02)
    assert record.exists()
    observed = json.loads(record.read_text(encoding="utf-8"))

    process.send_signal(termination_signal)
    process.wait(timeout=5)

    assert not Path(observed["cwd"]).exists()
    assert not (project / ".playwright-mcp").exists()


class McpConfigInstallTest(CliTestCase):
    def test_claude_install_writes_playwright_mcp(self) -> None:
        code, _, err = self.cli(["init", str(self.project), "--integration", "claude", "--json"])
        self.assertEqual(code, 0, err)
        mcp = self.project / ".mcp.json"
        assert mcp.exists()
        data = json.loads(mcp.read_text(encoding="utf-8"))
        assert "playwright" in data["mcpServers"]
        assert data["mcpServers"]["playwright"]["args"] == [
            "integration",
            "playwright-mcp",
        ]

    def test_codex_install_writes_project_scoped_playwright_mcp(self) -> None:
        code, out, err = self.cli(["init", str(self.project), "--integration", "codex", "--json"])
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        assert not (self.project / ".mcp.json").exists()
        assert payload["mcp"]["path"] == ".codex/config.toml"
        assert payload["mcp"]["integrationKey"] == "codex"
        data = _read_codex_mcp(self.project)
        assert data["mcp_servers"]["playwright"]["args"] == [
            "integration",
            "playwright-mcp",
        ]
        assert data["mcp_servers"]["playwright"]["required"] is True

    def test_codex_upgrade_restores_missing_project_mcp_config(self) -> None:
        code, _, err = self.cli(["init", str(self.project), "--integration", "codex", "--json"])
        self.assertEqual(code, 0, err)
        (self.project / ".codex" / "config.toml").unlink()

        code, out, err = self.cli(
            ["integration", "upgrade", "codex", "--project", str(self.project), "--json"]
        )

        self.assertEqual(code, 0, err)
        payload = json.loads(out)["upgraded"][0]
        assert payload["integration"]["default"] is True
        assert payload["mcp"]["added"] == ["playwright"]
        assert _read_codex_mcp(self.project)["mcp_servers"]["playwright"]["command"] == "verifysignal"

    def test_claude_upgrade_preserves_default_integration(self) -> None:
        code, _, err = self.cli(
            ["init", str(self.project), "--integration", "claude", "--json"]
        )
        self.assertEqual(code, 0, err)

        code, out, err = self.cli(
            [
                "integration",
                "upgrade",
                "claude",
                "--project",
                str(self.project),
                "--json",
            ]
        )

        self.assertEqual(code, 0, err)
        payload = json.loads(out)["upgraded"][0]
        assert payload["integration"]["default"] is True
