from __future__ import annotations

from pathlib import Path
from typing import Any

from verifysignal_spec.workflows import engine
from verifysignal_spec.workflows import migration as workflow_migration
from verifysignal_spec.workflows import readiness as workflow_readiness
from verifysignal_spec.workflows import stage_persistence
from verifysignal_spec.workflows.first_run import accept_first_run, build_first_run_recommendation, skip_first_run
from verifysignal_spec.workflows.repository import inspect_golden_path_workspace_state, reset_golden_path_workspace_state
from verifysignal_spec.workflows.models import WORKFLOW_ID
from verifysignal_spec.workflows.prerequisites import (
    check_prerequisites,
    stage_position_blocked_check_result,
)
from verifysignal_spec.workflows.transitions import managed_workflow_stage_decision
from verifysignal_spec.workflows.write_safety import build_rerun_approval_review, evaluate_rerun_decision
from verifysignal_spec.workspace.models import SupersedeReview
from verifysignal_spec.workspace.repository import load_supersede_reviews, load_use_case, now_iso, save_supersede_review
from verifysignal_spec.workspace.validation import validate_no_secret_values
from verifysignal_spec.integrations.invocation import (
    project_integration,
    render_agent_invocations_in_value,
)


def _agent_output(
    project: Path,
    value: dict[str, Any],
    integration: str | None = None,
) -> dict[str, Any]:
    selected = integration or value.get("integration") or project_integration(project)
    return render_agent_invocations_in_value(value, str(selected))


def run_workflow(project: Path, workflow_id: str, goal: str, alias: str | None = None, integration: str | None = None) -> dict[str, Any]:
    if workflow_id != WORKFLOW_ID:
        raise ValueError(f"Unsupported workflow: {workflow_id}")
    run = engine.create_workflow_run(project, goal=goal, alias=alias, integration=integration)
    return _agent_output(project, run.to_dict(), run.integration)


def resume(project: Path, run_id: str) -> dict[str, Any]:
    run = engine.resume_workflow(project, run_id)
    return _agent_output(project, run.to_dict(), run.integration)


def status(project: Path, run_id: str | None = None, alias: str | None = None) -> dict[str, Any]:
    if run_id and alias:
        raise ValueError("Use workflow status with either a run_id or --alias, not both.")
    if alias:
        result = engine.workflow_status_for_alias(project, alias)
        return _agent_output(project, result)
    if run_id:
        try:
            result = engine.workflow_status(project, run_id)
        except FileNotFoundError as original:
            try:
                result = engine.workflow_status_for_alias(project, run_id)
            except FileNotFoundError:
                raise original
        return _agent_output(project, result)
    return _agent_output(project, engine.workflow_status(project, run_id))


def show(project: Path, alias: str) -> dict[str, Any]:
    return _agent_output(project, engine.workflow_show(project, alias))


def list_runs(project: Path) -> dict[str, Any]:
    return engine.workflow_list(project)


def info(project: Path, workflow_id: str = WORKFLOW_ID, integration: str | None = None) -> dict[str, Any]:
    selected = project_integration(project, integration)
    return _agent_output(
        project,
        engine.workflow_info(project, workflow_id, integration=selected),
        selected,
    )


def check(project: Path, stage: str, alias: str | None = None, refresh_decision: str | None = None) -> dict[str, Any]:
    if stage == "validate":
        stage_decision = (
            managed_workflow_stage_decision(project, alias, stage)
            if isinstance(alias, str)
            else {"blocker": None}
        )
        stage_blocker = stage_decision.get("blocker")
        if isinstance(stage_blocker, dict) and isinstance(alias, str):
            result = stage_position_blocked_check_result(
                stage,
                alias,
                stage_blocker,
            )
        else:
            result = workflow_readiness.validation_readiness(project, alias=alias)
    else:
        result = check_prerequisites(
            project,
            stage,
            alias=alias,
            refresh_decision=refresh_decision,
        )
    return _agent_output(project, result)


def persist(project: Path, stage: str, alias: str | None = None, scope: str | None = None, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return _agent_output(
        project,
        stage_persistence.persist_stage(
            project,
            stage,
            alias=alias,
            scope=scope,
            payload=payload,
        ),
    )


def supersede_write_outcome(project: Path, alias: str, payload: dict[str, Any]) -> dict[str, Any]:
    review_data = dict(payload)
    review_data.setdefault("createdAt", now_iso())
    review = SupersedeReview.from_dict(review_data)
    findings = [*review.validate(), *validate_no_secret_values(review.to_dict(), "supersedeReview")]
    blockers = [item for item in findings if item.get("severity") == "blocking"]
    if blockers:
        return {
            "schemaVersion": "verifysignal-spec-supersede-review-result/v1",
            "alias": alias,
            "status": "blocked",
            "blockers": blockers,
        }
    saved = save_supersede_review(project, alias, review)
    # Recompute through the same run preflight used by workflow check/direct run
    # so the single active gate is removed or replaced before this command returns.
    check_prerequisites(project, "run", alias=alias)
    return {
        "schemaVersion": "verifysignal-spec-supersede-review-result/v1",
        "alias": alias,
        "status": "persisted",
        "review": saved.to_dict(),
        "nextAction": f"verifysignal workflow check run --alias {alias} --json",
    }


def approve_rerun(project: Path, alias: str, confirm_risk: str | None = None) -> dict[str, Any]:
    record = load_use_case(project, alias)
    rerun_decision = evaluate_rerun_decision(record, supersede_reviews=load_supersede_reviews(project, alias))
    if rerun_decision.get("decision") != "requires-confirmation":
        if rerun_decision.get("decision") == "blocked":
            return {
                "schemaVersion": "verifysignal-spec-rerun-approval-result/v1",
                "alias": alias,
                "status": "blocked",
                "rerunDecision": rerun_decision,
                "blockers": [
                    {
                        "code": "runtime.rerun-policy-blocked",
                        "severity": "blocker",
                        "category": "write-flow-safety",
                        "message": rerun_decision.get("reason"),
                        "recoveryCommand": f"verifysignal workflow supersede-write-outcome --alias {alias} --json",
                    }
                ],
                "nextAction": f"verifysignal workflow supersede-write-outcome --alias {alias} --json",
            }
        return {
            "schemaVersion": "verifysignal-spec-rerun-approval-result/v1",
            "alias": alias,
            "status": "ready",
            "rerunDecision": rerun_decision,
            "message": "No write rerun approval is required.",
            "nextAction": f"verifysignal workflow check run --alias {alias} --json",
        }
    expected = rerun_decision.get("confirmationId")
    if confirm_risk and confirm_risk != expected:
        return {
            "schemaVersion": "verifysignal-spec-rerun-approval-result/v1",
            "alias": alias,
            "status": "blocked",
            "rerunDecision": rerun_decision,
            "blockers": [
                {
                    "code": "runtime.confirmation-id-mismatch",
                    "severity": "blocker",
                    "category": "write-flow-safety",
                    "message": "The provided rerun confirmation id does not match the current write outcome.",
                    "expectedConfirmationId": expected,
                    "recoveryCommand": rerun_decision.get("nextAction"),
                }
            ],
            "nextAction": rerun_decision.get("nextAction"),
        }
    review = build_rerun_approval_review(record, rerun_decision, created_at=now_iso(), created_by="workflow approve-rerun")
    findings = [*review.validate(), *validate_no_secret_values(review.to_dict(), "rerunApproval")]
    blockers = [item for item in findings if item.get("severity") == "blocking"]
    if blockers:
        return {
            "schemaVersion": "verifysignal-spec-rerun-approval-result/v1",
            "alias": alias,
            "status": "blocked",
            "blockers": blockers,
        }
    saved = save_supersede_review(project, alias, review)
    current_preflight = check_prerequisites(project, "run", alias=alias)
    updated_decision = current_preflight.get("rerunDecision")
    if not isinstance(updated_decision, dict):
        updated_decision = evaluate_rerun_decision(
            record,
            supersede_reviews=load_supersede_reviews(project, alias),
        )
    return {
        "schemaVersion": "verifysignal-spec-rerun-approval-result/v1",
        "alias": alias,
        "status": "persisted",
        "review": saved.to_dict(),
        "rerunDecision": updated_decision,
        "nextAction": f"verifysignal workflow check run --alias {alias} --json",
    }


def migrate(project: Path, migration_id: str) -> dict[str, Any]:
    return workflow_migration.apply_migration(project, migration_id)


def recommend_first_run(project: Path) -> dict[str, Any]:
    return _agent_output(project, build_first_run_recommendation(project).to_dict())


def accept_golden_path_first_run(project: Path, alias: str) -> dict[str, Any]:
    return _agent_output(project, accept_first_run(project, alias))


def skip_golden_path_first_run(project: Path) -> dict[str, Any]:
    return _agent_output(project, skip_first_run(project))


def inspect_golden_path_state(project: Path) -> dict[str, Any]:
    return _agent_output(project, inspect_golden_path_workspace_state(project))


def reset_golden_path_state(project: Path, *, preview: bool = False, confirm: bool = False) -> dict[str, Any]:
    return _agent_output(
        project,
        reset_golden_path_workspace_state(
            project,
            preview=preview,
            confirm=confirm,
        ),
    )
