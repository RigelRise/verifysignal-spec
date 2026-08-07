from __future__ import annotations

from verifysignal_spec.commands import run as run_command
from verifysignal_spec.workspace.repository import load_use_case, run_confirmation_requirements, save_use_case
from tests.fixtures.workflows.live_write_readiness import (
    create_live_write_readiness_workspace,
    save_ready_snapshot,
)


def test_passed_legacy_write_without_core_envelope_is_reported_as_unknown_write_activity(tmp_path, monkeypatch) -> None:
    from tests.helpers import FAKE_CORE

    monkeypatch.setenv("VERIFYSIGNAL_CORE_CMD", str(FAKE_CORE))
    create_live_write_readiness_workspace(tmp_path)
    record = load_use_case(tmp_path, "add-collaboration-project")
    record.status = "ready"
    record.sideEffectLifecycle = {"cleanupPolicy": "manual", "cleanupRequired": True, "instructions": "Delete the project manually."}
    record.lastRun = None
    save_use_case(tmp_path, record)
    save_ready_snapshot(
        tmp_path,
        "add-collaboration-project",
        side_effect_class="write",
    )
    confirmation_ids = [
        item.id
        for item in run_confirmation_requirements(
            tmp_path,
            load_use_case(tmp_path, "add-collaboration-project"),
        )
    ]

    result = run_command.run(
        tmp_path,
        "add-collaboration-project",
        interactive=False,
        core_cmd=str(FAKE_CORE),
        confirmed_risks=confirmation_ids,
    )

    assert result["status"] == "passed"
    assert result["postCommitInterpretation"]["sideEffectMayExist"] is True
    assert result["postCommitInterpretation"]["sideEffectStatus"] == "unknown"
    assert "without a structured Core side-effect envelope" in result["postCommitInterpretation"]["message"]
    assert result["rerunDecision"]["decision"] == "allowed"
