from __future__ import annotations

from verifysignal_spec.commands import workflow as workflow_command
from verifysignal_spec.workspace import layout
from verifysignal_spec.workspace.repository import (
    load_document,
    load_supersede_reviews,
    load_use_case,
    save_document,
    save_use_case,
)
from verifysignal_spec.workflows.prerequisites import check_prerequisites

from tests.fixtures.workflows.prerequisites import create_current_understanding_workspace
from tests.fixtures.workflows.side_effect_contract_alignment import (
    blocked_write_last_run,
    confirmable_write_last_run,
    create_write_policy_workspace,
    supersede_review_payload,
)
from tests.integration.test_workflow_run_preflight_alignment import _write_minimal_stage_artifacts


def test_supersede_review_unblocks_effective_rerun_without_hand_editing_last_run(tmp_path) -> None:
    create_current_understanding_workspace(tmp_path)
    record = create_write_policy_workspace(
        tmp_path,
        last_run=blocked_write_last_run(),
        protected_ready=True,
    )
    record.status = "ready"
    save_use_case(tmp_path, record)
    _write_minimal_stage_artifacts(tmp_path, "add-collaboration-project")
    assert check_prerequisites(tmp_path, "run", alias="add-collaboration-project")["status"] == "blocked"
    confirmation_path = layout.confirmation_requirement_path(tmp_path, record.alias)
    save_document(
        confirmation_path,
        {
            "id": "confirm.stale.review",
            "alias": record.alias,
            "riskClass": "stale",
            "scope": "stale",
            "reason": "Obsolete gate.",
            "recommendedAction": "obsolete",
            "blocksExecution": True,
        },
    )

    result = workflow_command.supersede_write_outcome(
        tmp_path,
        alias="add-collaboration-project",
        payload=supersede_review_payload(source_run_id="violated-run"),
    )

    assert result["status"] == "persisted"
    assert load_use_case(tmp_path, "add-collaboration-project").lastRun["postCommitInterpretation"]["rerunRisk"] == "blocked"
    assert load_supersede_reviews(tmp_path, "add-collaboration-project")[0].sourceRunId == "violated-run"
    assert confirmation_path.exists() is False
    check = check_prerequisites(tmp_path, "run", alias="add-collaboration-project")
    assert check["status"] == "ready"
    assert check["rerunDecision"]["decision"] == "allowed-with-new-inputs"


def test_approve_rerun_records_owner_approval_for_current_committed_run(tmp_path) -> None:
    create_current_understanding_workspace(tmp_path)
    record = create_write_policy_workspace(
        tmp_path,
        last_run=confirmable_write_last_run(),
        protected_ready=True,
    )
    record.status = "ready"
    save_use_case(tmp_path, record)
    _write_minimal_stage_artifacts(tmp_path, "add-collaboration-project")
    check = check_prerequisites(tmp_path, "run", alias="add-collaboration-project")
    confirmation_id = check["rerunDecision"]["confirmationId"]
    confirmation_path = layout.confirmation_requirement_path(tmp_path, record.alias)
    assert load_document(confirmation_path)["id"] == confirmation_id

    result = workflow_command.approve_rerun(
        tmp_path,
        alias="add-collaboration-project",
        confirm_risk=confirmation_id,
    )

    assert result["status"] == "persisted"
    assert result["review"]["sourceRunId"] == "committed-run"
    assert result["review"]["ownerDecision"] == "approved-rerun-after-write"
    assert result["review"]["resultingClassification"]["rerunRisk"] == "safe-with-new-inputs"
    assert load_use_case(tmp_path, "add-collaboration-project").lastRun["postCommitInterpretation"]["rerunRisk"] == "requires-confirmation"
    reviews = load_supersede_reviews(tmp_path, "add-collaboration-project")
    assert reviews[-1].sourceRunId == "committed-run"
    assert confirmation_path.exists() is False
    ready = check_prerequisites(tmp_path, "run", alias="add-collaboration-project")
    assert ready["status"] == "ready"
    assert ready["rerunDecision"]["decision"] == "allowed-with-new-inputs"


def test_approve_rerun_refuses_blocked_write_outcome_without_supersede_review(tmp_path) -> None:
    create_current_understanding_workspace(tmp_path)
    record = create_write_policy_workspace(
        tmp_path,
        last_run=blocked_write_last_run(),
        protected_ready=True,
    )
    record.status = "ready"
    save_use_case(tmp_path, record)
    _write_minimal_stage_artifacts(tmp_path, "add-collaboration-project")

    result = workflow_command.approve_rerun(tmp_path, alias="add-collaboration-project")

    assert result["status"] == "blocked"
    assert result["blockers"][0]["code"] == "runtime.rerun-policy-blocked"
    assert result["nextAction"] == "verifysignal workflow supersede-write-outcome --alias add-collaboration-project --json"
    assert load_supersede_reviews(tmp_path, "add-collaboration-project") == []


def test_approve_rerun_replaces_a_stale_gate_with_a_remaining_current_requirement(tmp_path) -> None:
    create_current_understanding_workspace(tmp_path)
    record = create_write_policy_workspace(
        tmp_path,
        last_run=confirmable_write_last_run(),
        protected_ready=True,
    )
    record.status = "ready"
    record.sideEffectLifecycle = {
        "cleanupPolicy": "not-declared",
        "cleanupRequired": False,
    }
    record.artifactCapabilities = {
        "capabilities": [
            "explicit-confirmation",
            "generated-runtime-inputs",
            "resource-identity",
            "write-activity-interpretation",
        ]
    }
    save_use_case(tmp_path, record)
    _write_minimal_stage_artifacts(tmp_path, record.alias)
    decision = workflow_command.evaluate_rerun_decision(record)
    confirmation_path = layout.confirmation_requirement_path(tmp_path, record.alias)
    save_document(
        confirmation_path,
        {
            "id": "confirm.stale.review",
            "alias": record.alias,
            "riskClass": "stale",
            "scope": "stale",
            "reason": "Obsolete gate.",
            "recommendedAction": "obsolete",
            "blocksExecution": True,
        },
    )

    result = workflow_command.approve_rerun(
        tmp_path,
        alias=record.alias,
        confirm_risk=decision["confirmationId"],
    )

    assert result["status"] == "persisted"
    active = load_document(confirmation_path)
    assert active["id"] != "confirm.stale.review"
    assert active["scope"] == "missing-side-effect-lifecycle"
