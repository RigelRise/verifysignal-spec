from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from verifysignal_spec.integrations.invocation import project_integration
from verifysignal_spec.workspace import layout
from verifysignal_spec.workspace.repository import (
    load_document,
    load_readiness_snapshot,
    load_use_case,
    now_iso,
)
from verifysignal_spec.workspace.time_ordering import parse_utc_iso_ns

from .models import (
    WORKFLOW_ARTIFACT_PLAN_SCHEMA,
    WORKFLOW_STAGES,
    WORKFLOW_TASK_SET_SCHEMA,
    WorkflowRun,
    WorkflowStageState,
    native_invocation,
)
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
_CANONICAL_STAGE_TITLES = {
    "understand": "Understanding Snapshot: {alias}",
    "specify": "Use Case Specification: {alias}",
    "clarify": "Clarifications: {alias}",
    "plan": "Artifact Plan: {alias}",
    "tasks": "Authoring Tasks: {alias}",
    "implement": "Workflow Handoff: {alias}",
}
_DURABLE_STAGE_PROJECTION_SCHEMAS = {
    "plan": WORKFLOW_ARTIFACT_PLAN_SCHEMA,
    "tasks": WORKFLOW_TASK_SET_SCHEMA,
}
_LEGACY_WORKFLOW_STATUSES = {
    "not-started",
    "running",
    "paused",
    "blocked",
    "failed",
    "completed",
}


def validate_workflow_stage_position(
    project: Path,
    alias: str,
    stage: str,
) -> None:
    project = project.resolve()
    alias = layout.ensure_path_safe_alias(alias)
    try:
        run = load_active_workflow_run(project, alias)
    except FileNotFoundError:
        run = None
    if run is None:
        # The first mutating persistence is the lazy-migration boundary. Legacy
        # workspaces are intentionally allowed to reach transition_workflow(),
        # which infers one authoritative run from the artifacts just persisted.
        return
    if run.currentStage == stage:
        return
    if _is_authored_stage_reentry(run, stage):
        # Re-persisting an already-passed authored stage is the documented
        # recovery for a blocked validate/run: fix the artifact, re-enter the
        # loop. Only forward jumps past the workflow's position are illegal.
        return
    raise ValueError(
        f"Workflow current stage is {run.currentStage}; cannot persist {stage}."
    )


def _is_authored_stage_reentry(run: WorkflowRun, stage: str) -> bool:
    if stage not in _MIGRATABLE_AUTHORED_STAGES:
        return False
    if run.status == "completed":
        return False
    if run.currentStage in _MIGRATABLE_AUTHORED_STAGES:
        # The ordered authoring walk stays strict; recovery reentry exists for
        # the execution loop (validate/run/repair) only.
        return False
    return WORKFLOW_STAGES.index(stage) < WORKFLOW_STAGES.index(run.currentStage)


def resolve_managed_workflow_stage(
    project: Path,
    alias: str,
    requested_stage: str,
) -> tuple[dict[str, Any], WorkflowRun | None]:
    """Return the stage decision and the exact WorkflowRun authority it used."""

    project = project.resolve()
    alias = layout.ensure_path_safe_alias(alias)
    record_path = layout.use_case_path(project, alias)
    if not record_path.is_file() or record_path.is_symlink():
        return {"managed": False, "blocker": None}, None
    record = load_use_case(project, alias)
    try:
        run = load_active_workflow_run(project, alias)
    except ValueError:
        workflow_reference = (
            record.workflow if isinstance(record.workflow, dict) else {}
        )
        referenced_run_id = str(
            workflow_reference.get("lastWorkflowRunId") or ""
        )
        try:
            safe_run_id = layout.ensure_path_safe_run_id(referenced_run_id)
        except ValueError:
            safe_run_id = ""
        recovery_command = (
            f"verifysignal workflow status {safe_run_id} --json"
            if safe_run_id
            else "verifysignal workflow list --json"
        )
        blocker = {
            "code": "workflow.authority-invalid",
            "severity": "blocker",
            "category": "workflow",
            "message": (
                "The referenced WorkflowRun authority is unreadable; "
                "execution is blocked until it is repaired or replaced."
            ),
            "currentStage": "unknown",
            "requestedStage": requested_stage,
            "recoveryCommand": recovery_command,
        }
        return (
            {
                "managed": True,
                "currentStage": "unknown",
                "requestedStage": requested_stage,
                "blocker": blocker,
            },
            None,
        )
    if run is None and not _has_legacy_workflow_evidence(
        project,
        alias,
        record,
    ):
        return {"managed": False, "blocker": None}, None

    current_stage = (
        run.currentStage
        if run is not None
        else _legacy_current_stage(project, alias, record)
    )
    allowed_sources = (
        {"validate", "run", "repair"}
        if requested_stage == "validate"
        else {requested_stage}
    )
    if current_stage in allowed_sources:
        return (
            {
                "managed": True,
                "currentStage": current_stage,
                "requestedStage": requested_stage,
                "blocker": None,
            },
            run,
        )

    integration = run.integration if run is not None else project_integration(project)
    recovery_command = _next_command(current_stage, alias, integration)
    blocker = {
        "code": "workflow.stage-out-of-order",
        "severity": "blocker",
        "category": "workflow",
        "message": (
            f"Workflow current stage is {current_stage}; "
            f"cannot execute {requested_stage}."
        ),
        "currentStage": current_stage,
        "requestedStage": requested_stage,
        "recoveryCommand": recovery_command,
    }
    return (
        {
            "managed": True,
            "currentStage": current_stage,
            "requestedStage": requested_stage,
            "blocker": blocker,
        },
        run,
    )


def managed_workflow_stage_decision(
    project: Path,
    alias: str,
    requested_stage: str,
) -> dict[str, Any]:
    """Return the compatible public stage-position decision projection."""

    decision, _run = resolve_managed_workflow_stage(
        project,
        alias,
        requested_stage,
    )
    return decision


def validate_managed_workflow_stage_position(
    project: Path,
    alias: str,
    stage: str,
) -> bool:
    """Validate an active/legacy staged workflow without claiming standalone use cases.

    Direct ``author`` use cases predate staged workflows and intentionally have
    neither a WorkflowRun nor durable workflow documents. Protected commands
    remain available for those records. Once any staged-workflow authority or
    durable projection exists, however, terminal commands must obey the same
    exact source-stage rule as authored-stage persistence.
    """

    decision = managed_workflow_stage_decision(project, alias, stage)
    blocker = decision.get("blocker")
    if isinstance(blocker, dict):
        raise ValueError(
            str(blocker["message"])
        )
    return bool(decision["managed"])


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
    source_stage = run.currentStage
    stage_state = _stage_state(run, stage)

    if stage == "validate":
        _reset_stages_after_validation(run)
    if stage == "repair" and outcome == "completed":
        _reset_stages_after_repair(run)
    if outcome == "completed" and _is_authored_stage_reentry(run, stage):
        # The re-persisted artifact invalidates every later stage result; the
        # transition target then re-enters the loop at the stage's normal
        # successor.
        _reset_stages_after(run, stage)

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
    furthest_stage, evidence = _legacy_furthest_authored_stage(
        project,
        alias,
        record,
    )
    furthest_index = (
        _MIGRATABLE_AUTHORED_STAGES.index(furthest_stage)
        if furthest_stage is not None
        else -1
    )
    for index, stage_name in enumerate(_MIGRATABLE_AUTHORED_STAGES):
        if index > furthest_index:
            break
        state = next(item for item in stage_states if item.stage == stage_name)
        state.status = "completed"
        state.startedAt = now
        state.completedAt = now
        state.handoffSummary = "Migrated from durable workflow evidence."
        durable_fingerprint_parts.extend([stage_name, evidence.get(stage_name, "inferred")])

    if furthest_index == len(_MIGRATABLE_AUTHORED_STAGES) - 1:
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
        current_stage = _MIGRATABLE_AUTHORED_STAGES[furthest_index + 1]

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


def _legacy_current_stage(project: Path, alias: str, record: Any | None = None) -> str:
    record = record or load_use_case(project, alias)
    furthest_stage, _evidence = _legacy_furthest_authored_stage(
        project,
        alias,
        record,
    )
    if furthest_stage != "implement":
        if furthest_stage is None:
            return "understand"
        return _MIGRATABLE_AUTHORED_STAGES[
            _MIGRATABLE_AUTHORED_STAGES.index(furthest_stage) + 1
        ]
    snapshot = load_readiness_snapshot(project, alias)
    return "run" if _protected_readiness_is_valid(snapshot) else "validate"


def _has_legacy_workflow_evidence(
    project: Path,
    alias: str,
    record: Any,
) -> bool:
    workflow_reference = getattr(record, "workflow", None)
    if _compatible_legacy_workflow_reference(
        project,
        alias,
        workflow_reference,
    ):
        return True
    state_path = layout.workflow_state_path(project, alias)
    if state_path.is_file() and not state_path.is_symlink():
        return True
    if any(
        _durable_stage_document(project, alias, stage) is not None
        for stage in _MIGRATABLE_AUTHORED_STAGES
    ):
        return True
    references = [
        getattr(record, "runRequest", None),
        getattr(record, "mainSkill", None),
        *list(getattr(record, "skills", []) or []),
        *list(getattr(record, "sourceOnlySkills", []) or []),
    ]
    return any(
        _durable_artifact_reference(project, reference)
        for reference in references
    )


def _legacy_furthest_authored_stage(
    project: Path,
    alias: str,
    record: Any,
) -> tuple[str | None, dict[str, str]]:
    evidence: dict[str, str] = {}
    for stage_name in _MIGRATABLE_AUTHORED_STAGES:
        content = _durable_stage_document(project, alias, stage_name)
        if content is not None:
            evidence[stage_name] = content

    workflow_reference = getattr(record, "workflow", None)
    if _compatible_legacy_workflow_reference(
        project,
        alias,
        workflow_reference,
    ):
        current_stage = str(workflow_reference.get("currentStage") or "")
        current_index = WORKFLOW_STAGES.index(current_stage)
        completed_index = min(
            current_index - 1,
            len(_MIGRATABLE_AUTHORED_STAGES) - 1,
        )
        if completed_index >= 0:
            stage_name = _MIGRATABLE_AUTHORED_STAGES[completed_index]
            evidence.setdefault(stage_name, f"workflow:{current_stage}")

    for stage_name in ("plan", "tasks"):
        projection_path = _durable_stage_projection(
            project,
            alias,
            stage_name,
        )
        if projection_path is not None:
            evidence.setdefault(stage_name, str(projection_path.relative_to(project)))

    executable_references = [
        getattr(record, "runRequest", None),
        getattr(record, "mainSkill", None),
        *list(getattr(record, "skills", []) or []),
        *list(getattr(record, "sourceOnlySkills", []) or []),
    ]
    if any(
        _durable_artifact_reference(project, reference)
        for reference in executable_references
    ):
        evidence.setdefault("implement", "use-case:executable-references")

    furthest_stage = next(
        (
            stage_name
            for stage_name in reversed(_MIGRATABLE_AUTHORED_STAGES)
            if stage_name in evidence
        ),
        None,
    )
    return furthest_stage, evidence


def _compatible_legacy_workflow_reference(
    project: Path,
    alias: str,
    value: Any,
) -> bool:
    if not isinstance(value, dict):
        return False
    if value.get("workflowDir") != workflow_dir_rel(project, alias):
        return False
    if value.get("currentStage") not in WORKFLOW_STAGES:
        return False
    if value.get("workflowStatus") not in _LEGACY_WORKFLOW_STATUSES:
        return False
    if "lastWorkflowRunId" in value:
        run_id = value.get("lastWorkflowRunId")
        if not isinstance(run_id, str) or not run_id:
            return False
        try:
            layout.ensure_path_safe_run_id(run_id)
        except ValueError:
            return False
    if "lastUpdatedAt" in value and parse_utc_iso_ns(value.get("lastUpdatedAt")) is None:
        return False
    return True


def _durable_artifact_reference(project: Path, reference: Any) -> bool:
    raw_path = getattr(reference, "path", None)
    if not isinstance(raw_path, str) or not raw_path.strip():
        return False
    return _project_owned_regular_file(project, raw_path) is not None


def _project_owned_regular_file(project: Path, raw_path: str | Path) -> Path | None:
    relative = Path(raw_path)
    if relative.is_absolute() or ".." in relative.parts:
        return None
    current = project.resolve()
    for part in relative.parts:
        if part in {"", "."}:
            continue
        current /= part
        try:
            if current.is_symlink():
                return None
        except OSError:
            return None
    try:
        resolved = current.resolve(strict=True)
        resolved.relative_to(project.resolve())
    except (OSError, RuntimeError, ValueError):
        return None
    return resolved if resolved.is_file() else None


def _durable_stage_document(
    project: Path,
    alias: str,
    stage: str,
) -> str | None:
    path = layout.workflow_stage_document_path(project, alias, stage)
    durable_path = _project_owned_regular_file(project, path.relative_to(project))
    if durable_path is None:
        return None
    try:
        content = durable_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None
    expected_title = _CANONICAL_STAGE_TITLES[stage].format(alias=alias)
    first_line = content.lstrip().partition("\n")[0].rstrip("\r")
    if first_line != f"# {expected_title}":
        return None
    return content


def _durable_stage_projection(
    project: Path,
    alias: str,
    stage: str,
) -> Path | None:
    path = layout.workflow_stage_document_path(
        project,
        alias,
        stage,
    ).with_suffix(".yaml")
    durable_path = _project_owned_regular_file(project, path.relative_to(project))
    if durable_path is None:
        return None
    try:
        content = load_document(durable_path)
    except (OSError, UnicodeError, TypeError, ValueError):
        return None
    if not isinstance(content, dict):
        return None
    if content.get("schemaVersion") != _DURABLE_STAGE_PROJECTION_SCHEMAS[stage]:
        return None
    if content.get("useCaseAlias") != alias:
        return None
    return durable_path


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
    if stage == "validate" and run.currentStage in {"run", "repair"}:
        return
    if outcome == "completed" and _is_authored_stage_reentry(run, stage):
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


def _reset_stages_after_validation(run: WorkflowRun) -> None:
    _reset_stages_after(run, "validate")


def _reset_stages_after(run: WorkflowRun, stage: str) -> None:
    stage_index = WORKFLOW_STAGES.index(stage)
    for state in run.stageStates[stage_index + 1 :]:
        state.status = "pending"
        state.startedAt = None
        state.completedAt = None
        state.blockers = []
        state.nextCommand = None


def _reset_stages_after_repair(run: WorkflowRun) -> None:
    for stage_name in ("validate", "run"):
        state = _stage_state(run, stage_name)
        state.status = "pending"
        state.startedAt = None
        state.completedAt = None
        state.blockers = []
        state.nextCommand = None


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
