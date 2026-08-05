from __future__ import annotations

from verifysignal_spec.workflows.prerequisites import check_prerequisites
from verifysignal_spec.workspace.repository import load_use_case, save_use_case
from tests.fixtures.workflows.live_write_readiness import (
    create_live_write_readiness_workspace,
    save_ready_snapshot,
)
from tests.fixtures.workflows.prerequisites import create_current_understanding_workspace


def test_workflow_check_run_surfaces_structured_confirmation_without_execution(tmp_path) -> None:
    create_current_understanding_workspace(tmp_path)
    create_live_write_readiness_workspace(tmp_path)
    record = load_use_case(tmp_path, "add-collaboration-project")
    record.status = "ready"
    save_use_case(tmp_path, record)
    save_ready_snapshot(tmp_path, record.alias, side_effect_class="write")

    result = check_prerequisites(tmp_path, "run", alias="add-collaboration-project")

    assert result["requiresConfirmation"] is True
    confirmation = result["confirmation"]
    assert confirmation["id"].startswith("confirm.add-collaboration-project.")
    assert confirmation["alias"] == "add-collaboration-project"
    assert confirmation["riskClass"] == "write"
    assert confirmation["scope"]
    assert confirmation["reason"]
    assert confirmation["recommendedAction"]
    assert confirmation["blocksExecution"] is True


def test_workflow_check_run_requires_confirmation_for_unresolved_side_effect_risk_even_when_legacy_class_is_none(tmp_path) -> None:
    create_current_understanding_workspace(tmp_path)
    create_live_write_readiness_workspace(tmp_path)
    record = load_use_case(tmp_path, "add-collaboration-project")
    record.status = "ready"
    record.sideEffects = {"class": "none"}
    record.sideEffectLifecycle = {"cleanupPolicy": "none", "cleanupRequired": False}
    record.artifactCapabilities = {
        "capabilities": [
            "explicit-confirmation",
            "generated-runtime-inputs",
            "side-effect-lifecycle",
            "write-activity-interpretation",
        ]
    }
    record.lastRun = {
        "runId": "previous-write-run",
        "status": "passed",
        "postCommitInterpretation": {
            "postCommit": False,
            "sideEffectMayExist": True,
            "sideEffectStatus": "unknown",
            "message": "Prior run left unresolved side-effect risk.",
        },
    }
    save_use_case(tmp_path, record)
    save_ready_snapshot(tmp_path, record.alias, side_effect_class="none")

    result = check_prerequisites(tmp_path, "run", alias="add-collaboration-project")

    assert result["requiresConfirmation"] is True
    confirmation = result["confirmation"]
    assert confirmation["riskClass"] == "unknown-write-risk"
    assert confirmation["scope"] == "unresolved-side-effect-risk"
    assert result["recommendedAction"] == "confirm-risk"
