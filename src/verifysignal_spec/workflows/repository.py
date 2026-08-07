from __future__ import annotations

import hashlib
import os
import stat
import time
from pathlib import Path
from typing import Any

from verifysignal_spec.workspace import layout
from verifysignal_spec.workspace.models import UseCaseRecord
from verifysignal_spec.workspace.path_safety import (
    ensure_no_casefold_sibling_collision,
    ensure_unredirected_project_path,
)
from verifysignal_spec.workspace.repository import (
    create_default_use_case,
    load_document,
    load_registry,
    load_use_case,
    now_iso,
    save_document,
    save_use_case,
    update_use_case_workflow_reference,
)
from verifysignal_spec.workspace.time_ordering import format_utc_ns, parse_utc_iso_ns
from verifysignal_spec.workspace.validation import validate_no_secret_values
from verifysignal_spec.integrations.invocation import (
    SUPPORTED_INTEGRATIONS,
    project_integration,
    render_agent_invocations_in_value,
)

from .models import (
    WORKFLOW_ARTIFACT_PLAN_SCHEMA,
    WORKFLOW_ID,
    WORKFLOW_RUN_SCHEMA,
    WORKFLOW_STAGES,
    WORKFLOW_STATE_SCHEMA,
    ArtifactPlan,
    AuthoringTaskSet,
    GoldenPathWorkspaceState,
    UseCaseWorkflowReference,
    WorkflowRun,
    WorkflowStageState,
)


_WORKFLOW_STATUSES = {
    "not-started",
    "running",
    "paused",
    "blocked",
    "failed",
    "completed",
}
_STAGE_STATUSES = {
    "pending",
    "running",
    "completed",
    "blocked",
    "skipped",
    "failed",
}
_GATE_DECISIONS = {"approved", "rejected"}


def _reject_secrets(data: Any) -> None:
    findings = validate_no_secret_values(data)
    if findings:
        first = findings[0]
        raise ValueError(f"Secret-looking workflow value at {first.get('path')}: {first.get('message')}")


def _validate_workflow_run_document(
    data: Any,
    *,
    expected_run_id: str,
) -> None:
    if not isinstance(data, dict):
        raise ValueError("Workflow run authority must be a structured document.")
    if data.get("schemaVersion") != WORKFLOW_RUN_SCHEMA:
        raise ValueError(
            f"Unsupported workflow run schema: {data.get('schemaVersion')}"
        )
    run_id = data.get("runId")
    if not isinstance(run_id, str):
        raise ValueError("Workflow run authority requires a runId.")
    try:
        safe_run_id = layout.ensure_path_safe_run_id(run_id)
    except ValueError as exc:
        raise ValueError("Workflow run authority has an invalid runId.") from exc
    if safe_run_id != expected_run_id:
        raise ValueError("Workflow run document identity does not match its path.")
    if data.get("workflowId") != WORKFLOW_ID:
        raise ValueError("Workflow run authority has an invalid workflowId.")
    alias = data.get("useCaseAlias")
    if not isinstance(alias, str):
        raise ValueError("Workflow run authority requires a useCaseAlias.")
    try:
        layout.ensure_path_safe_alias(alias)
    except ValueError as exc:
        raise ValueError("Workflow run authority has an invalid useCaseAlias.") from exc
    if data.get("status") not in _WORKFLOW_STATUSES:
        raise ValueError("Workflow run authority has an invalid status.")
    current_stage = data.get("currentStage")
    if current_stage not in WORKFLOW_STAGES:
        raise ValueError("Workflow run authority has an invalid currentStage.")
    integration = data.get("integration")
    if integration is not None and integration not in SUPPORTED_INTEGRATIONS:
        raise ValueError("Workflow run authority has an invalid integration.")
    started_at_ns = _require_workflow_timestamp(data.get("startedAt"), "startedAt")
    updated_at_ns = _require_workflow_timestamp(data.get("updatedAt"), "updatedAt")
    completed_at = data.get("completedAt")
    completed_at_ns: int | None = None
    if completed_at is not None:
        completed_at_ns = _require_workflow_timestamp(completed_at, "completedAt")
    if updated_at_ns < started_at_ns:
        raise ValueError(
            "Workflow run authority updatedAt cannot precede startedAt."
        )
    if completed_at_ns is not None and updated_at_ns < completed_at_ns:
        raise ValueError(
            "Workflow run authority updatedAt cannot precede completedAt."
        )
    if data.get("status") == "completed" and completed_at is None:
        raise ValueError("Completed workflow run authority requires completedAt.")
    if data.get("status") != "completed" and completed_at is not None:
        raise ValueError(
            "Non-completed workflow run authority cannot carry completedAt."
        )
    for field in ("workflowDir", "nextCommand", "resumeCommand"):
        value = data.get(field)
        if value is not None and not isinstance(value, str):
            raise ValueError(f"Workflow run authority has an invalid {field}.")

    stage_states = data.get("stageStates")
    if not isinstance(stage_states, list):
        raise ValueError("Workflow run authority requires stageStates.")
    observed_stages: list[str] = []
    for state in stage_states:
        if not isinstance(state, dict):
            raise ValueError("Workflow stage authority must be structured.")
        stage = state.get("stage")
        if stage not in WORKFLOW_STAGES:
            raise ValueError("Workflow stage authority has an invalid stage.")
        if state.get("status") not in _STAGE_STATUSES:
            raise ValueError("Workflow stage authority has an invalid status.")
        observed_stages.append(str(stage))
        for field in ("startedAt", "completedAt"):
            value = state.get(field)
            if value is not None:
                _require_workflow_timestamp(value, f"stageStates.{field}")
        blockers = state.get("blockers", [])
        if not isinstance(blockers, list) or any(
            not isinstance(blocker, dict)
            or not isinstance(blocker.get("code"), str)
            or not blocker.get("code")
            or (
                blocker.get("severity") is not None
                and not isinstance(blocker.get("severity"), str)
            )
            or any(
                blocker.get(field) is not None
                and not isinstance(blocker.get(field), str)
                for field in (
                    "category",
                    "message",
                    "recoveryCommand",
                    "documentationRef",
                )
            )
            or (
                blocker.get("repairable") is not None
                and not isinstance(blocker.get("repairable"), bool)
            )
            for blocker in blockers
        ):
            raise ValueError("Workflow stage authority has invalid blockers.")
    if (
        len(observed_stages) != len(WORKFLOW_STAGES)
        or len(set(observed_stages)) != len(observed_stages)
        or set(observed_stages) != set(WORKFLOW_STAGES)
    ):
        raise ValueError(
            "Workflow run authority requires exactly one state for every stage."
        )
    states_by_stage = {
        str(state["stage"]): str(state["status"])
        for state in stage_states
    }
    post_repair_validation = bool(
        current_stage == "validate" and states_by_stage["repair"] == "completed"
    )
    incomplete_predecessors = []
    for predecessor in WORKFLOW_STAGES[: WORKFLOW_STAGES.index(current_stage)]:
        allowed = {"completed", "skipped"}
        if current_stage == "repair" and predecessor == "run":
            allowed = {"failed"}
        if states_by_stage[predecessor] not in allowed:
            incomplete_predecessors.append(predecessor)
    if incomplete_predecessors:
        raise ValueError(
            "Workflow run authority cannot enter its current stage before "
            "every predecessor has a coherent terminal state."
        )
    if current_stage == "repair" and states_by_stage["run"] != "failed":
        raise ValueError(
            "Workflow repair stage requires a failed run predecessor."
        )
    if post_repair_validation and (
        states_by_stage["validate"] != "pending"
        or states_by_stage["run"] != "pending"
    ):
        raise ValueError(
            "Post-repair validation requires validate and run to be reset to pending."
        )
    for later_stage in WORKFLOW_STAGES[WORKFLOW_STAGES.index(current_stage) + 1 :]:
        if post_repair_validation and later_stage == "repair":
            continue
        if states_by_stage[later_stage] != "pending":
            raise ValueError(
                "Workflow stages later than the current stage must remain pending."
            )
    if states_by_stage["run"] == "completed" and (
        data.get("status") != "completed" or current_stage != "run"
    ):
        raise ValueError(
            "A completed run stage requires a completed workflow at currentStage run."
        )
    if data.get("status") == "completed" and (
        current_stage != "run" or states_by_stage["run"] != "completed"
    ):
        raise ValueError(
            "Completed workflow authority requires a completed current run stage."
        )

    gate_decisions = data.get("gateDecisions", [])
    if not isinstance(gate_decisions, list):
        raise ValueError("Workflow run authority has invalid gateDecisions.")
    for decision in gate_decisions:
        if (
            not isinstance(decision, dict)
            or not isinstance(decision.get("gateId"), str)
            or not decision.get("gateId")
            or decision.get("stageBefore") not in WORKFLOW_STAGES
            or decision.get("decision") not in _GATE_DECISIONS
            or (
                decision.get("reason") is not None
                and not isinstance(decision.get("reason"), str)
            )
        ):
            raise ValueError("Workflow run authority has an invalid gate decision.")
        _require_workflow_timestamp(decision.get("decidedAt"), "decidedAt")

    confirmation = data.get("targetEnvironmentConfirmation")
    if confirmation is not None:
        if not isinstance(confirmation, dict):
            raise ValueError("Workflow target confirmation must be structured.")
        if set(confirmation) != {"questionId", "url", "source", "confirmedAt"}:
            raise ValueError("Workflow target confirmation has an invalid shape.")
        if confirmation.get("questionId") != "browser-target-environment":
            raise ValueError("Workflow target confirmation has an invalid questionId.")
        if not isinstance(confirmation.get("url"), str) or not confirmation.get("url"):
            raise ValueError("Workflow target confirmation requires a URL.")
        if confirmation.get("source") not in {"direct-user", "explicit-command"}:
            raise ValueError("Workflow target confirmation has an invalid source.")
        _require_workflow_timestamp(
            confirmation.get("confirmedAt"),
            "targetEnvironmentConfirmation.confirmedAt",
        )
    _reject_secrets(data)


def _require_workflow_timestamp(value: Any, field: str) -> int:
    parsed = parse_utc_iso_ns(value)
    if parsed is None:
        raise ValueError(f"Workflow run authority has an invalid {field} timestamp.")
    return parsed


def project_relative(project: Path, path: Path) -> str:
    return layout.to_project_relative(project, path)


def workflow_dir_rel(project: Path, alias: str) -> str:
    return project_relative(project, layout.workflow_use_case_dir(project, alias))


def ensure_workflow_workspace(project: Path, alias: str | None = None) -> None:
    workflow_paths = [
        layout.workflows_root(project),
        layout.workflow_definitions_dir(project),
        layout.workflow_runs_dir(project),
        layout.workflow_use_cases_dir(project),
    ]
    if alias:
        layout.ensure_path_safe_alias(alias)
        workflow_paths.append(layout.workflow_use_case_dir(project, alias))
    for path in workflow_paths:
        ensure_unredirected_project_path(
            project,
            path,
            authority="Workflow workspace",
        )
    for directory in layout.workspace_dirs(project):
        directory.mkdir(parents=True, exist_ok=True)
    if alias:
        layout.workflow_use_case_dir(project, alias).mkdir(parents=True, exist_ok=True)


def create_stage_states(project: Path, alias: str) -> list[WorkflowStageState]:
    return [
        WorkflowStageState(stage="understand", documentPath=project_relative(project, layout.workflow_stage_document_path(project, alias, "understand"))),
        WorkflowStageState(stage="specify", documentPath=project_relative(project, layout.workflow_stage_document_path(project, alias, "specify"))),
        WorkflowStageState(stage="clarify", documentPath=project_relative(project, layout.workflow_stage_document_path(project, alias, "clarify"))),
        WorkflowStageState(stage="plan", documentPath=project_relative(project, layout.workflow_stage_document_path(project, alias, "plan"))),
        WorkflowStageState(stage="tasks", documentPath=project_relative(project, layout.workflow_stage_document_path(project, alias, "tasks"))),
        WorkflowStageState(stage="implement", documentPath=project_relative(project, layout.workflow_stage_document_path(project, alias, "implement"))),
        WorkflowStageState(stage="validate", documentPath=project_relative(project, layout.workflow_stage_document_path(project, alias, "validate"))),
        WorkflowStageState(stage="run", documentPath=project_relative(project, layout.workflow_stage_document_path(project, alias, "run"))),
        WorkflowStageState(stage="repair", documentPath=project_relative(project, layout.workflow_stage_document_path(project, alias, "repair"))),
    ]


def state_document(
    project: Path,
    alias: str,
    run: WorkflowRun | None = None,
    current_stage: str = "understand",
    status: str = "paused",
) -> dict[str, Any]:
    if run is not None:
        if run.useCaseAlias != alias:
            raise ValueError("Workflow run alias does not match rendered state alias.")
        current_stage = run.currentStage
        status = run.status
    states = run.stageStates if run else create_stage_states(project, alias)
    documents = {
        "understanding": project_relative(project, layout.workflow_stage_document_path(project, alias, "understand")),
        "spec": project_relative(project, layout.workflow_stage_document_path(project, alias, "specify")),
        "clarifications": project_relative(project, layout.workflow_stage_document_path(project, alias, "clarify")),
        "plan": project_relative(project, layout.workflow_stage_document_path(project, alias, "plan")),
        "tasks": project_relative(project, layout.workflow_stage_document_path(project, alias, "tasks")),
    }
    return {
        "schemaVersion": WORKFLOW_STATE_SCHEMA,
        "useCaseAlias": alias,
        "workflowId": WORKFLOW_ID,
        **({"runId": run.runId} if run else {}),
        "currentStage": current_stage,
        "status": status,
        "documents": documents,
        "stageStates": [item.to_dict() for item in states],
        "nextCommand": run.nextCommand if run else f"/verifysignal-{current_stage} {alias}",
        **({"resumeCommand": run.resumeCommand} if run and run.resumeCommand else {}),
        "updatedAt": run.updatedAt if run and run.updatedAt else now_iso(),
    }


def render_workflow_state(project: Path, run: WorkflowRun) -> dict[str, Any]:
    return state_document(
        project,
        run.useCaseAlias,
        run,
        current_stage=run.currentStage,
        status=run.status,
    )


def save_workflow_state(
    project: Path,
    alias: str,
    data: dict[str, Any],
    *,
    integration: str | None = None,
) -> None:
    layout.ensure_path_safe_alias(alias)
    rendered = render_agent_invocations_in_value(
        data,
        integration or project_integration(project),
    )
    _reject_secrets(rendered)
    save_document(layout.workflow_state_path(project, alias), rendered)


def load_workflow_state(project: Path, alias: str) -> dict[str, Any]:
    data = load_document(layout.workflow_state_path(project, alias), default={})
    return data if isinstance(data, dict) else {}


def save_workflow_run(project: Path, run: WorkflowRun) -> None:
    layout.ensure_path_safe_run_id(run.runId)
    layout.ensure_path_safe_alias(run.useCaseAlias)
    path = _safe_workflow_run_path(project, run.runId)
    _ensure_portable_workflow_run_filenames(path.parent)
    ensure_no_casefold_sibling_collision(
        path,
        authority="Workflow run authority",
    )
    run.startedAt = run.startedAt or now_iso()
    if not run.stageStates:
        run.stageStates = create_stage_states(project, run.useCaseAlias)
    run.updatedAt = _next_workflow_update_iso(
        project,
        after=[run.startedAt, run.updatedAt, run.completedAt],
    )
    rendered = render_agent_invocations_in_value(
        run.to_dict(),
        run.integration or project_integration(project),
    )
    _reject_secrets(rendered)
    _validate_workflow_run_document(rendered, expected_run_id=run.runId)
    save_document(path, rendered)


def load_workflow_run(project: Path, run_id: str) -> WorkflowRun:
    run_id = layout.ensure_path_safe_run_id(run_id)
    path = _safe_workflow_run_path(project, run_id)
    _ensure_portable_workflow_run_filenames(path.parent)
    ensure_no_casefold_sibling_collision(
        path,
        authority="Workflow run authority",
    )
    try:
        metadata = os.lstat(path)
    except FileNotFoundError:
        raise FileNotFoundError(f"Workflow run not found: {run_id}")
    except OSError as exc:
        raise ValueError("Workflow run authority cannot be inspected safely.") from exc
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError("Workflow run authority must be a regular file.")
    data = load_document(path)
    _validate_workflow_run_document(data, expected_run_id=run_id)
    run = WorkflowRun.from_dict(data)
    return run


def list_workflow_runs(project: Path) -> list[WorkflowRun]:
    runs: list[WorkflowRun] = []
    directory = _safe_workflow_runs_dir(project)
    if not directory.exists():
        return runs
    _ensure_portable_workflow_run_filenames(directory)
    for path in sorted(directory.glob("*.yaml")):
        runs.append(load_workflow_run(project, path.stem))
    runs.sort(key=_workflow_run_stamp, reverse=True)
    return runs


def load_active_workflow_run(project: Path, alias: str) -> WorkflowRun | None:
    record = load_use_case(project, alias)
    workflow = record.workflow if isinstance(record.workflow, dict) else {}
    run_id = workflow.get("lastWorkflowRunId")
    referenced: WorkflowRun | None = None
    if run_id:
        try:
            referenced = load_workflow_run(project, str(run_id))
        except FileNotFoundError:
            # A stale projection may legitimately point at a removed run while
            # a newer matching authority is still recoverable from disk.
            referenced = None
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"Referenced workflow run {run_id} is unreadable or incoherent."
            ) from exc
        if referenced is not None and referenced.useCaseAlias != alias:
            raise ValueError(
                f"Referenced workflow run {run_id} belongs to another use case."
            )
    matching = _matching_workflow_runs(project, alias)
    if not matching:
        return None
    newest_stamp = max(_workflow_run_stamp(run) for run in matching)
    newest = [
        run for run in matching if _workflow_run_stamp(run) == newest_stamp
    ]
    if len(newest) != 1:
        raise ValueError(
            "Workflow authority is ambiguous: multiple matching runs have the "
            "same newest update timestamp."
        )
    if referenced is not None and _workflow_run_stamp(referenced) == newest_stamp:
        return referenced
    return newest[0]


def _matching_workflow_runs(
    project: Path,
    alias: str,
) -> list[WorkflowRun]:
    runs: list[WorkflowRun] = []
    directory = _safe_workflow_runs_dir(project)
    if not directory.exists():
        return runs
    _ensure_portable_workflow_run_filenames(directory)
    for path in directory.glob("*.yaml"):
        try:
            ensure_unredirected_project_path(
                project,
                path,
                authority="Workflow run authority",
            )
        except ValueError:
            continue
        if not _is_regular_workflow_candidate(path):
            continue
        try:
            data = load_document(path, default=None)
        except (OSError, UnicodeError):
            continue
        if not isinstance(data, dict) or data.get("useCaseAlias") != alias:
            continue
        try:
            run = load_workflow_run(project, path.stem)
        except FileNotFoundError:
            continue
        if run.useCaseAlias == alias:
            runs.append(run)
    return runs


def _workflow_run_stamp(run: WorkflowRun) -> int:
    stamp = parse_utc_iso_ns(run.updatedAt or run.startedAt)
    if stamp is None:  # pragma: no cover - load boundary validates this
        raise ValueError("Workflow run authority has no comparable timestamp.")
    return stamp


def _next_workflow_update_iso(
    project: Path,
    *,
    after: list[Any] | None = None,
) -> str:
    candidate = time.time_ns()
    for value in after or []:
        persisted = parse_utc_iso_ns(value)
        if persisted is not None:
            candidate = max(candidate, persisted + 1)
    directory = _safe_workflow_runs_dir(project)
    if directory.exists():
        for path in directory.glob("*.yaml"):
            try:
                ensure_unredirected_project_path(
                    project,
                    path,
                    authority="Workflow run authority",
                )
            except ValueError:
                continue
            if not _is_regular_workflow_candidate(path):
                continue
            try:
                data = load_document(path, default={})
            except (OSError, UnicodeError):
                continue
            if not isinstance(data, dict):
                continue
            persisted = _workflow_iso_to_ns(data.get("updatedAt"))
            if persisted is not None:
                candidate = max(candidate, persisted + 1)
    return _workflow_ns_to_iso(candidate)


def _workflow_iso_to_ns(value: Any) -> int | None:
    return parse_utc_iso_ns(value)


def _workflow_ns_to_iso(value: int) -> str:
    return format_utc_ns(value)


def _is_regular_workflow_candidate(path: Path) -> bool:
    """Return true only for a no-follow regular-file candidate."""

    try:
        metadata = os.lstat(path)
    except OSError:
        return False
    return stat.S_ISREG(metadata.st_mode)


def _ensure_portable_workflow_run_filenames(directory: Path) -> None:
    """Reject siblings whose names collapse on case-insensitive filesystems."""

    if not directory.exists():
        return
    try:
        candidates = [
            path
            for path in directory.iterdir()
            if path.name.casefold().endswith(".yaml")
        ]
    except OSError as exc:
        raise ValueError(
            "Workflow run filename portability cannot be verified safely."
        ) from exc
    for candidate in candidates:
        ensure_no_casefold_sibling_collision(
            candidate.with_suffix(".yaml"),
            authority="Workflow run authority",
        )


def _safe_workflow_runs_dir(project: Path) -> Path:
    return ensure_unredirected_project_path(
        project,
        layout.workflow_runs_dir(project),
        authority="Workflow run authority",
    )


def _safe_workflow_run_path(project: Path, run_id: str) -> Path:
    return ensure_unredirected_project_path(
        project,
        layout.workflow_run_path(project, run_id),
        authority="Workflow run authority",
    )


def create_or_load_use_case(project: Path, alias: str, goal: str) -> UseCaseRecord:
    try:
        return load_use_case(project, alias)
    except FileNotFoundError:
        record = create_default_use_case(project, alias, goal)
        record.status = "draft"
        record.runRequest = None
        record.mainSkill = None
        record.skills = []
        save_use_case(project, record)
        return record


def workflow_reference_document(
    project: Path,
    alias: str,
    run: WorkflowRun,
) -> dict[str, Any]:
    if run.useCaseAlias != alias:
        raise ValueError("Workflow run alias does not match projection alias.")
    record = load_use_case(project, alias)
    workflow = dict(record.workflow or {})
    reference = UseCaseWorkflowReference(
        workflowDir=workflow_dir_rel(project, alias),
        currentStage=run.currentStage,
        workflowStatus=run.status,
        lastWorkflowRunId=run.runId,
        lastUpdatedAt=run.updatedAt or now_iso(),
    )
    workflow.update(reference.to_dict())
    return workflow


def link_workflow_reference(
    project: Path,
    alias: str,
    run: WorkflowRun,
    status: str | None = None,
) -> UseCaseRecord:
    if status is not None and status != run.status:
        raise ValueError("Workflow reference status must match the authoritative run.")
    return update_use_case_workflow_reference(
        project,
        alias,
        workflow_reference_document(project, alias, run),
    )


def workflow_projection_differences(
    project: Path,
    run: WorkflowRun,
) -> list[str]:
    record = load_use_case(project, run.useCaseAlias)
    workflow = record.workflow if isinstance(record.workflow, dict) else {}
    state = load_workflow_state(project, run.useCaseAlias)
    expected_states = [item.to_dict() for item in run.stageStates]
    differences: list[str] = []
    expected_reference = {
        "lastWorkflowRunId": run.runId,
        "currentStage": run.currentStage,
        "workflowStatus": run.status,
    }
    for key, expected in expected_reference.items():
        if workflow.get(key) != expected:
            differences.append(f"workflow.{key}")
    expected_state = {
        "runId": run.runId,
        "currentStage": run.currentStage,
        "status": run.status,
        "stageStates": expected_states,
    }
    for key, expected in expected_state.items():
        if state.get(key) != expected:
            differences.append(f"state.{key}")
    return differences


def save_workflow_projections(
    project: Path,
    run: WorkflowRun,
) -> tuple[dict[str, Any], dict[str, Any]]:
    record = link_workflow_reference(
        project,
        run.useCaseAlias,
        run,
        run.status,
    )
    save_workflow_state(
        project,
        run.useCaseAlias,
        render_workflow_state(project, run),
        integration=run.integration,
    )
    return dict(record.workflow or {}), load_workflow_state(
        project,
        run.useCaseAlias,
    )


def import_legacy_use_case(project: Path, alias: str, run_id: str | None = None) -> dict[str, Any]:
    record = load_use_case(project, alias)
    ensure_workflow_workspace(project, alias)
    current_stage = "validate" if record.runRequest and record.mainSkill else "plan"
    stage_states = create_stage_states(project, alias)
    for state in stage_states[: WORKFLOW_STAGES.index(current_stage)]:
        state.status = "skipped"
    run = WorkflowRun(
        runId=run_id or f"wf-import-{alias}",
        useCaseAlias=alias,
        status="paused",
        currentStage=current_stage,
        workflowDir=workflow_dir_rel(project, alias),
        startedAt=now_iso(),
        updatedAt=now_iso(),
        stageStates=stage_states,
        nextCommand=f"/verifysignal-{('validate' if record.runRequest and record.mainSkill else 'plan')} {alias}",
    )
    save_workflow_run(project, run)
    save_workflow_projections(project, run)
    return {"alias": alias, "runId": run.runId, "currentStage": run.currentStage}


def save_artifact_plan(project: Path, plan: ArtifactPlan) -> None:
    _reject_secrets(plan.to_dict())
    save_document(layout.workflow_stage_document_path(project, plan.useCaseAlias, "plan").with_suffix(".yaml"), plan.to_dict())


def load_artifact_plan(project: Path, alias: str) -> ArtifactPlan:
    data = load_document(layout.workflow_stage_document_path(project, alias, "plan").with_suffix(".yaml"))
    if not data:
        raise FileNotFoundError(f"Artifact plan not found for {alias}")
    if data.get("schemaVersion") and data.get("schemaVersion") != WORKFLOW_ARTIFACT_PLAN_SCHEMA:
        raise ValueError(f"Unsupported artifact plan schema: {data.get('schemaVersion')}")
    return ArtifactPlan.from_dict(data)


def save_task_set(project: Path, task_set: AuthoringTaskSet) -> None:
    _reject_secrets(task_set.to_dict())
    save_document(layout.workflow_stage_document_path(project, task_set.useCaseAlias, "tasks").with_suffix(".yaml"), task_set.to_dict())


def fingerprint_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def index_skill_reuse(project: Path) -> dict[str, list[dict[str, str]]]:
    index: dict[str, list[dict[str, str]]] = {}
    for item in load_registry(project).get("useCases", []):
        alias = item.get("alias")
        if not alias:
            continue
        try:
            record = load_use_case(project, alias)
        except Exception:
            continue
        seen_paths: set[str] = set()
        for skill in [*record.skills, *record.sourceOnlySkills]:
            if skill.path in seen_paths:
                continue
            seen_paths.add(skill.path)
            index.setdefault(skill.path, []).append({"useCaseAlias": alias, "runRequest": record.runRequest.path if record.runRequest else ""})
    return index


def golden_path_state_path(project: Path) -> Path:
    return layout.workflows_root(project) / "golden-path-state.yaml"


def save_golden_path_state(project: Path, data: dict[str, Any]) -> None:
    rendered = render_agent_invocations_in_value(
        data,
        project_integration(project),
    )
    _reject_secrets(rendered)
    save_document(golden_path_state_path(project), rendered)


def load_golden_path_state(project: Path) -> dict[str, Any]:
    return load_document(golden_path_state_path(project), default={}) or {}


def inspect_golden_path_workspace_state(project: Path) -> dict[str, Any]:
    state = load_golden_path_state(project)
    owned = _golden_path_owned_artifacts(project)
    preserved = _golden_path_preserved_artifacts(project, owned)
    untracked_runs = [] if state else _golden_path_untracked_runs(project)
    selected = state.get("selectedCandidate") if state else None
    first_run_status = state.get("firstRunStatus") if state else None
    if selected and first_run_status != "skipped":
        resume_hint = f"verifysignal run {selected} --json"
    elif untracked_runs:
        resume_hint = f"verifysignal workflow accept-first-run {untracked_runs[0]['alias']} --json"
    else:
        resume_hint = "verifysignal workflow recommend-first-run --json"
    return GoldenPathWorkspaceState(
        status="untracked" if untracked_runs else ("empty" if not state else "ready"),
        projectRoot=str(project),
        firstRunStatus=first_run_status,
        firstRunState=state.get("runState") if isinstance(state.get("runState"), dict) else state or None,
        ownedArtifacts=owned,
        preservedArtifacts=preserved,
        resetPreview=[f"remove {path}" for path in owned],
        resumeHint=resume_hint,
        warnings=[
            "Run history exists, but no Golden Path first run was explicitly accepted before execution; existing runs are not counted as Golden Path state."
        ]
        if untracked_runs
        else [],
        untrackedRuns=untracked_runs or None,
        nextAction="verifysignal workflow reset-golden-path-state --preview --json" if owned else resume_hint,
    ).to_dict()


def reset_golden_path_workspace_state(project: Path, *, preview: bool = False, confirm: bool = False) -> dict[str, Any]:
    if preview == confirm:
        raise ValueError("Use exactly one of --preview or --confirm.")
    inspected = inspect_golden_path_workspace_state(project)
    if preview:
        return inspected
    path = golden_path_state_path(project)
    if path.exists():
        path.unlink()
    inspected["status"] = "reset"
    inspected["firstRunStatus"] = None
    inspected["firstRunState"] = None
    inspected["ownedArtifacts"] = []
    inspected["resetPreview"] = []
    inspected["nextAction"] = "verifysignal workflow recommend-first-run --json"
    return inspected


def _golden_path_owned_artifacts(project: Path) -> list[str]:
    path = golden_path_state_path(project)
    return [project_relative(project, path)] if path.exists() else []


def _golden_path_preserved_artifacts(project: Path, owned: list[str]) -> list[str]:
    root = layout.workspace_root(project)
    if not root.exists():
        return []
    owned_set = set(owned)
    preserved: list[str] = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        rel = project_relative(project, path)
        if rel not in owned_set:
            preserved.append(rel)
    return preserved


def _golden_path_untracked_runs(project: Path) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    registry = load_registry(project)
    for item in registry.get("useCases", []):
        alias = item.get("alias") if isinstance(item, dict) else None
        if not alias:
            continue
        try:
            record = load_use_case(project, str(alias))
        except Exception:
            continue
        last_run = record.lastRun if isinstance(record.lastRun, dict) else None
        if not last_run:
            continue
        runs.append(
            {
                "alias": record.alias,
                "runId": last_run.get("runId"),
                "status": last_run.get("status"),
                "coreStatus": last_run.get("coreStatus"),
                "coverageStatus": last_run.get("coverageStatus"),
                "profile": last_run.get("profile"),
            }
        )
    return runs
