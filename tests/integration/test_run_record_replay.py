from __future__ import annotations

from pathlib import Path

from tests.fixtures.workflows.main_skill_run_coverage import create_main_skill_coverage_workspace
from verifysignal_spec.commands import run as run_command

# The Core adapter has supported `--record`/`--replay` all along, and Core's own contract advertises
# both run flags — but the Spec CLI never exposed them, so record/replay was reachable only from
# Python. These guards pin the CLI-to-Core wiring end to end: a flag that argparse accepts but never
# forwards is worse than a missing flag, because it silently runs a NORMAL live run while the user
# believes they are recording or replaying.


def _workspace(tmp_path: Path, monkeypatch) -> str:
    from tests.helpers import FAKE_CORE

    # Record/replay are now capability-negotiated: forwarding requires a Core that ADVERTISES the run
    # modes in its version entry (an older Core blocks with core.run-record-unsupported instead). The
    # env flag composes with any behavior mode (some tests also need e.g. full-coverage).
    monkeypatch.setenv("VERIFYSIGNAL_CORE_CMD", str(FAKE_CORE))
    monkeypatch.setenv("FAKE_VERIFYSIGNAL_ADVERTISE_RUN_MODES", "1")
    monkeypatch.setenv("VERIFYSIGNAL_RUNTIME_CACHE_DIR", str(tmp_path / "runtime-cache"))
    create_main_skill_coverage_workspace(
        tmp_path,
        helper_first=True,
        core_cmd=str(FAKE_CORE),
        protected_ready=True,
    )
    return str(FAKE_CORE)


def test_record_flag_reaches_core_argv(tmp_path, monkeypatch) -> None:
    core = _workspace(tmp_path, monkeypatch)

    result = run_command.run(tmp_path, "profile-view-unauth", interactive=False, core_cmd=core, record=True)

    assert "--record" in result["core"]["data"]["args"]
    assert result["core"]["data"]["record"] is True


def test_replay_flag_reaches_core_argv_with_its_fixture(tmp_path, monkeypatch) -> None:
    core = _workspace(tmp_path, monkeypatch)
    fixture = tmp_path / "fixtures" / "login" / "manifest.json"

    result = run_command.run(tmp_path, "profile-view-unauth", interactive=False, core_cmd=core, replay=fixture)

    args = result["core"]["data"]["args"]
    assert "--replay" in args
    assert args[args.index("--replay") + 1] == str(fixture)
    assert result["core"]["data"]["replay"] == str(fixture)


def test_a_plain_run_stays_live_and_passes_neither_flag(tmp_path, monkeypatch) -> None:
    # Scope guard: the default must not silently start recording (it writes extra evidence) or replay.
    core = _workspace(tmp_path, monkeypatch)

    result = run_command.run(tmp_path, "profile-view-unauth", interactive=False, core_cmd=core)

    args = result["core"]["data"]["args"]
    assert "--record" not in args
    assert "--replay" not in args


def test_cli_run_forwards_record_to_core(tmp_path, monkeypatch, capsys) -> None:
    # The CLI layer is where the wiring was missing, so assert through `main` rather than the Python
    # entry point: argparse accepting `--record` proves nothing about it reaching Core.
    from verifysignal_spec.cli import main

    _workspace(tmp_path, monkeypatch)
    monkeypatch.setenv("FAKE_VERIFYSIGNAL_MODE", "full-coverage")  # exit 0 needs a covered run

    code = main(["run", "profile-view-unauth", "--project", str(tmp_path), "--non-interactive", "--record", "--json"])

    assert code == 0
    assert '"record": true' in capsys.readouterr().out
