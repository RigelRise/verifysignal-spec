from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from verifysignal_spec.integrations.invocation import project_integration
from verifysignal_spec.workspace import layout
from verifysignal_spec.workspace.repository import (
    load_readiness_snapshot,
    load_use_case,
    now_iso,
)

from .models import WORKFLOW_STAGES, WorkflowRun, WorkflowStageState, native_invocation
from .repository import (
    create_stage_states,
    fingerprint_text,
    load_active_workflow_run,
    load_workflow_run,
    save_workflow_projections,
    save_workflow_run,
    workflow_dir_rel,
    workflow_projection_differences,
)


TransitionOutcome = Literal["completed", "blocked", "failed"]


@dataclass(slots=True)
class WorkflowTransitionResult:
    run: WorkflowRun
    workflowReference: dict[str, Any]
    renderedState: dict[str, Any]
    migrated: bool = False


_TRANSITION_TARGETS: dict[
    tuple[str, TransitionOutcome],
    tuple[str, Literal["paused", "completed"]],
] = {
    ("understand", "completed"): ("specify", "paused"),
    ("specify", "completed"): ("clarify", "paused"),
    ("clarify", "completed"): ("plan", "paused"),
    ("clarify", "blocked"): ("clarify", "paused"),
    ("plan", "completed"): ("tasks", "paused"),
    ("tasks", "completed"): ("implement", "paused"),
    ("implement", "completed"): ("validate", "paused"),
    ("validate", "completed"): ("run", "paused"),
    ("validate", "blocked"): ("validate", "paused"),
    ("run", "completed"): ("run", "completed"),
    ("run", "failed"): ("repair", "paused"),
    ("run", "blocked"): ("run", "paused"),
    ("repair", "completed"): ("validate", "paused"),
}
_MIGRATABLE_AUTHORED_STAGES = [
    "understand",
    "specify",
    "clarify",
    "plan",
    "tasks",
    "implement",
]


def validate_workflow_stage_position(
    project: Path,
    alias: str,
    stage: str,
) -> None:
    project = project.resolve()
    alias = layout.ensure_path_safe_alias(alias)
    try:
        run = load_active_workflow_run(project, alias)
    except FileNotFoundError as exc:
        raise ValueError(
            f"No staged workflow exists for {alias}; start the workflow first."
        ) from exc
    current_stage = (
        run.currentStage
        if run is not None
        else _legacy_current_stage(project, alias)
    )
    if current_stage != stage:
        raise ValueError(
            f"Workflow current stage is {current_stage}; cannot persist {stage}."
        )


def transition_workflow(
    project: Path,
    alias: str,
    *,
    stage: str,
    outcome: TransitionOutcome,
    blockers: list[dict[str, Any]] | None = None,
    document_path: str | None = None,
    target_confirmation: dict[str, Any] | None = None,
    handoff_summary: str | None = None,
) -> WorkflowTransitionResult:
    project = project.resolve()
    alias = layout.ensure_path_safe_alias(alias)
    target = _TRANSITION_TARGETS.get((stage, outcome))
    if target is None:
        raise ValueError(
            f"Unsupported workflow transition: {stage} -> {outcome}."
        )
    now = now_iso()
    normalized_blockers = _normalized_blockers(blockers or [])
    normalized_confirmation = (
        _validated_target_confirmation(target_confirmation, now=now)
        if target_confirmation is not None
        else None
    )

    run, migrated = _load_or_migrate_active_run(project, alias)
    _normalize_stage_states(project, run)
    _validate_transition_position(
        run,
        stage=stage,
        outcome=outcome,
        target=target,
        migrated=migrated,
    )
    if not migrated and workflow_projection_differences(project, run):
        save_workflow_projections(project, run)
    stage_state = _stage_state(run, stage)

    stage_state.status = outcome
    if outcome == "completed":
        stage_state.startedAt = stage_state.startedAt or now
        stage_state.completedAt = now
        stage_state.blockers = []
    elif outcome == "failed":
        stage_state.startedAt = stage_state.startedAt or now
        stage_state.completedAt = now
        stage_state.blockers = normalized_blockers
    else:
        stage_state.completedAt = None
        stage_state.blockers = normalized_blockers
    if document_path:
        stage_state.documentPath = document_path
    if handoff_summary:
        stage_state.handoffSummary = handoff_summary

    current_stage, workflow_status = target
    run.currentStage = current_stage
    run.status = workflow_status
    run.completedAt = now if workflow_status == "completed" else None
    run.nextCommand = (
        None
        if workflow_status == "completed"
        else _next_command(current_stage, alias, run.integration)
    )
    run.resumeCommand = (
        None
        if workflow_status == "completed"
        else f"verifysignal workflow resume {run.runId}"
    )
    stage_state.nextCommand = run.nextCommand
    if normalized_confirmation is not None:
        run.targetEnvironmentConfirmation = normalized_confirmation

    result = persist_authoritative_workflow(project, run)
    result.migrated = migrated
    return result


def persist_authoritative_workflow(
    project: Path,
    run: WorkflowRun,
) -> WorkflowTransitionResult:
    project = project.resolve()
    layout.ensure_path_safe_alias(run.useCaseAlias)
    _normalize_stage_states(project, run)
    save_workflow_run(project, run)
    workflow_reference, rendered_state = save_workflow_projections(project, run)
    persisted = load_workflow_run(project, run.runId)
    differences = workflow_projection_differences(project, persisted)
    if differences:
        raise RuntimeError(
            "Workflow projection verification failed: "
            + ", ".join(differences)
        )
    return WorkflowTransitionResult(
        run=persisted,
        workflowReference=workflow_reference,
        renderedState=rendered_state,
    )


def _load_or_migrate_active_run(
    project: Path,
    alias: str,
) -> tuple[WorkflowRun, bool]:
    run = load_active_workflow_run(project, alias)
    if run is not None:
        return run, False
    return _migrate_legacy_workflow(project, alias), True


def _migrate_legacy_workflow(project: Path, alias: str) -> WorkflowRun:
    record = load_use_case(project, alias)
    now = now_iso()
    integration = project_integration(project)
    stage_states = create_stage_states(project, alias)
    durable_fingerprint_parts = [alias]
    first_incomplete = "understand"
    all_authored_complete = True
    for stage_name in _MIGRATABLE_AUTHORED_STAGES:
        path = layout.workflow_stage_document_path(project, alias, stage_name)
        content = _durable_stage_document(path)
        if content is None:
            first_incomplete = stage_name
            all_authored_complete = False
            break
        state = next(item for item in stage_states if item.stage == stage_name)
        state.status = "completed"
        state.startedAt = now
        state.completedAt = now
        state.handoffSummary = "Migrated from the durable stage document."
        durable_fingerprint_parts.extend([stage_name, content])

    if all_authored_complete:
        snapshot = load_readiness_snapshot(project, alias)
        if _protected_readiness_is_valid(snapshot):
            validation = next(
                item for item in stage_states if item.stage == "validate"
            )
            validation.status = "completed"
            validation.startedAt = now
            validation.completedAt = now
            validation.handoffSummary = (
                "Migrated from a protected-operation readiness snapshot."
            )
            current_stage = "run"
        else:
            current_stage = "validate"
    else:
        current_stage = first_incomplete

    nonce = fingerprint_text("\n".join(durable_fingerprint_parts))[:12]
    run_id = layout.ensure_path_safe_id(
        f"wf-migration-{alias}-{nonce}"
    )
    return WorkflowRun(
        runId=run_id,
        useCaseAlias=alias,
        integration=integration,
        status="paused",
        currentStage=current_stage,
        startedAt=now,
        updatedAt=now,
        workflowDir=workflow_dir_rel(project, alias),
        stageStates=stage_states,
        nextCommand=_next_command(current_stage, alias, integration),
        resumeCommand=f"verifysignal workflow resume {run_id}",
        targetEnvironmentConfirmation=_legacy_target_confirmation(record, now),
    )


def _legacy_current_stage(project: Path, alias: str) -> str:
    for stage_name in _MIGRATABLE_AUTHORED_STAGES:
        path = layout.workflow_stage_document_path(project, alias, stage_name)
        if _durable_stage_document(path) is None:
            return stage_name
    snapshot = load_readiness_snapshot(project, alias)
    return "run" if _protected_readiness_is_valid(snapshot) else "validate"


def _durable_stage_document(path: Path) -> str | None:
    if not path.is_file() or path.is_symlink():
        return None
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None
    stripped = content.lstrip()
    if not stripped or not stripped.startswith("# "):
        return None
    return content


def _protected_readiness_is_valid(snapshot: Any) -> bool:
    return bool(
        snapshot is not None
        and snapshot.status == "ready"
        and snapshot.readinessScope == "protected-operation"
        and snapshot.protectedOperationStatus == "passed"
    )


def _legacy_target_confirmation(record: Any, now: str) -> dict[str, Any] | None:
    for question in record.authoringQuestions:
        if (
            question.id != "browser-target-environment"
            or question.status != "answered"
            or question.confirmationSource
            not in {"direct-user", "explicit-command"}
        ):
            continue
        locator = str(question.answerSummary or "").strip()
        if not locator:
            continue
        return {
            "url": locator,
            "source": question.confirmationSource,
            "confirmedAt": now,
            "questionId": question.id,
        }
    return None


def _normalize_stage_states(project: Path, run: WorkflowRun) -> None:
    defaults = {
        item.stage: item
        for item in create_stage_states(project, run.useCaseAlias)
    }
    extras: list[WorkflowStageState] = []
    for state in run.stageStates:
        if state.stage in defaults:
            defaults[state.stage] = state
        else:
            extras.append(state)
    run.stageStates = [defaults[stage] for stage in WORKFLOW_STAGES] + extras


def _stage_state(run: WorkflowRun, stage: str) -> WorkflowStageState:
    return next(item for item in run.stageStates if item.stage == stage)


def _validate_transition_position(
    run: WorkflowRun,
    *,
    stage: str,
    outcome: TransitionOutcome,
    target: tuple[str, Literal["paused", "completed"]],
    migrated: bool,
) -> None:
    if run.currentStage == stage:
        return
    state = _stage_state(run, stage)
    migration_includes_current_write = bool(
        migrated
        and outcome == "completed"
        and state.status == "completed"
        and run.currentStage == target[0]
    )
    if migration_includes_current_write:
        return
    raise ValueError(
        f"Workflow current stage is {run.currentStage}; cannot transition {stage}."
    )


def _normalized_blockers(
    blockers: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for blocker in blockers:
        if hasattr(blocker, "to_dict"):
            blocker = blocker.to_dict()
        if not isinstance(blocker, dict):
            raise ValueError("Workflow blockers must be structured objects.")
        code = str(blocker.get("code") or "").strip()
        if not code:
            raise ValueError("Workflow blockers require a stable code.")
        normalized.append(dict(blocker))
    return normalized


def _validated_target_confirmation(
    confirmation: dict[str, Any],
    *,
    now: str,
) -> dict[str, Any]:
    locator = str(confirmation.get("url") or "").strip()
    source = str(confirmation.get("source") or "").strip()
    if not locator or source not in {"direct-user", "explicit-command"}:
        raise ValueError(
            "Target confirmation requires a locator and a direct confirmation source."
        )
    return {
        "url": locator,
        "source": source,
        "confirmedAt": str(confirmation.get("confirmedAt") or now),
        "questionId": str(
            confirmation.get("questionId") or "browser-target-environment"
        ),
    }


def _next_command(
    stage: str,
    alias: str,
    integration: str | None,
) -> str:
    invocation = native_invocation(
        stage,
        "skill",
        integration=integration or "codex",
    )
    return f"{invocation} {alias}".strip()
