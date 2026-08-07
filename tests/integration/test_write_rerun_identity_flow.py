from __future__ import annotations

import time

from verifysignal_spec.commands import run as run_command
from verifysignal_spec.workspace.repository import refresh_collision_findings


def test_collision_preflight_uses_local_state_under_50ms(tmp_path) -> None:
    from tests.fixtures.workflows.write_rerun_identity import committed_last_run, write_use_case_record

    write_use_case_record(tmp_path, last_run=committed_last_run(value="VerifySignal collab seed"))

    started = time.perf_counter()
    findings = refresh_collision_findings(
        tmp_path,
        use_case_alias="add-collaboration-project",
        target_scope="https://example.test",
        bindings={"projectTitle": "VerifySignal collab seed"},
    )
    elapsed_ms = (time.perf_counter() - started) * 1000

    assert findings
    assert elapsed_ms < 50


def test_committed_write_rerun_preflight_allows_refreshed_project_title(tmp_path, monkeypatch) -> None:
    from tests.fixtures.workflows.write_rerun_identity import committed_last_run, write_use_case_record
    from tests.helpers import FAKE_CORE

    monkeypatch.setenv("VERIFYSIGNAL_CORE_CMD", str(FAKE_CORE))
    write_use_case_record(
        tmp_path,
        rerun_policy={"afterCommit": "allowed-with-new-inputs", "refreshRuntimeInputs": ["projectTitle"]},
        last_run=committed_last_run(),
        protected_ready=True,
    )

    result = run_command.run(tmp_path, "add-collaboration-project", interactive=False, core_cmd=str(FAKE_CORE))

    assert result["status"] == "passed"
    assert result["rerunDecision"]["decision"] == "allowed-with-new-inputs"
    assert result["rerunDecision"]["refreshRuntimeInputs"] == ["projectTitle"]
