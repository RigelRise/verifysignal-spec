from __future__ import annotations

from verifysignal_spec.commands import run as run_command
from verifysignal_spec.workspace.repository import load_use_case, run_confirmation_requirements, save_use_case
from tests.fixtures.workflows.live_write_readiness import (
    create_live_write_readiness_workspace,
    save_ready_snapshot,
)


def test_write_run_result_contract_distinguishes_browser_status_from_write_interpretation(tmp_path, monkeypatch) -> None:
    from tests.helpers import FAKE_CORE

    monkeypatch.setenv("VERIFYSIGNAL_CORE_CMD", str(FAKE_CORE))
    create_live_write_readiness_workspace(tmp_path)
    record = load_use_case(tmp_path, "add-collaboration-project")
    record.status = "ready"
    record.sideEffectLifecycle = {"cleanupPolicy": "manual", "cleanupRequired": True, "instructions": "Delete manually."}
    save_use_case(tmp_path, record)
    save_ready_snapshot(
        tmp_path,
        "add-collaboration-project",
        side_effect_class="write",
    )
    confirmation_id = run_confirmation_requirements(tmp_path, load_use_case(tmp_path, "add-collaboration-project"))[0].id

    result = run_command.run(
        tmp_path,
        "add-collaboration-project",
        interactive=False,
        core_cmd=str(FAKE_CORE),
        confirmed_risks=[confirmation_id],
    )

    assert result["coreBrowserStatus"] == "passed"
    assert result["specCoverageStatus"] in {"complete", "not-run"}
    assert result["postCommitInterpretation"]["sideEffectStatus"] == "unknown"
    assert result["sideEffectLifecycle"]["cleanupPolicy"] == "manual"
    assert result["sideEffectLifecycle"]["declared"] is True
