from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from verifysignal_spec.workspace import layout
from verifysignal_spec.workspace.models import UseCaseRecord
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
from verifysignal_spec.workspace.validation import validate_no_secret_values
from verifysignal_spec.integrations.invocation import (
    project_integration,
    render_agent_invocations_in_value,
)

from .models import (
    WORKFLOW_ARTIFACT_PLAN_SCHEMA,
    WORKFLOW_ID,
    WORKFLOW_RUN_SCHEMA,
    WORKFLOW_STATE_SCHEMA,
    ArtifactPlan,
    AuthoringTaskSet,
    GoldenPathWorkspaceState,
    UseCaseWorkflowReference,
    WorkflowRun,
    WorkflowStageState,
)


def _reject_secrets(data: Any) -> None:
    findings = validate_no_secret_values(data)
    if findings:
        first = findings[0]
        raise ValueError(f"Secret-looking workflow value at {first.get('path')}: {first.get('message')}")


def project_relative(project: Path, path: Path) -> str:
    return layout.to_project_relative(project, path)


def workflow_dir_rel(project: Path, alias: str) -> str:
    return project_relative(project, layout.workflow_use_case_dir(project, alias))


def ensure_workflow_workspace(project: Path, alias: str | None = None) -> None:
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


def state_document(project: Path, alias: str, run: WorkflowRun | None = None, current_stage: str = "understand", status: str = "paused") -> dict[str, Any]:
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
        "currentStage": current_stage,
        "status": status,
        "documents": documents,
        "stageStates": [item.to_dict() for item in states],
        "nextCommand": run.nextCommand if run else f"/verifysignal-{current_stage} {alias}",
        "updatedAt": now_iso(),
    }


def save_workflow_state(project: Path, alias: str, data: dict[str, Any]) -> None:
    layout.ensure_path_safe_alias(alias)
    rendered = render_agent_invocations_in_value(
        data,
        project_integration(project),
    )
    _reject_secrets(rendered)
    save_document(layout.workflow_state_path(project, alias), rendered)


def load_workflow_state(project: Path, alias: str) -> dict[str, Any]:
    return load_document(layout.workflow_state_path(project, alias), default={}) or {}


def save_workflow_run(project: Path, run: WorkflowRun) -> None:
    run.updatedAt = now_iso()
    rendered = render_agent_invocations_in_value(
        run.to_dict(),
        run.integration or project_integration(project),
    )
    _reject_secrets(rendered)
    save_document(layout.workflow_run_path(project, run.runId), rendered)


def load_workflow_run(project: Path, run_id: str) -> WorkflowRun:
    data = load_document(layout.workflow_run_path(project, run_id))
    if not data:
        raise FileNotFoundError(f"Workflow run not found: {run_id}")
    if data.get("schemaVersion") and data.get("schemaVersion") != WORKFLOW_RUN_SCHEMA:
        raise ValueError(f"Unsupported workflow run schema: {data.get('schemaVersion')}")
    return WorkflowRun.from_dict(data)


def list_workflow_runs(project: Path) -> list[WorkflowRun]:
    runs: list[WorkflowRun] = []
    directory = layout.workflow_runs_dir(project)
    if not directory.exists():
        return runs
    for path in sorted(directory.glob("*.yaml")):
        data = load_document(path)
        if data:
            runs.append(WorkflowRun.from_dict(data))
    runs.sort(key=lambda item: item.updatedAt or item.startedAt or "", reverse=True)
    return runs


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


def link_workflow_reference(project: Path, alias: str, run: WorkflowRun, status: str = "paused") -> UseCaseRecord:
    reference = UseCaseWorkflowReference(
        workflowDir=workflow_dir_rel(project, alias),
        currentStage=run.currentStage,
        workflowStatus=status,
        lastWorkflowRunId=run.runId,
        lastUpdatedAt=now_iso(),
    )
    return update_use_case_workflow_reference(project, alias, reference.to_dict())


def import_legacy_use_case(project: Path, alias: str, run_id: str | None = None) -> dict[str, Any]:
    record = load_use_case(project, alias)
    ensure_workflow_workspace(project, alias)
    run = WorkflowRun(
        runId=run_id or f"wf-import-{alias}",
        useCaseAlias=alias,
        status="paused",
        currentStage="validate" if record.runRequest and record.mainSkill else "plan",
        workflowDir=workflow_dir_rel(project, alias),
        startedAt=now_iso(),
        updatedAt=now_iso(),
        stageStates=create_stage_states(project, alias),
        nextCommand=f"/verifysignal-{('validate' if record.runRequest and record.mainSkill else 'plan')} {alias}",
    )
    save_workflow_run(project, run)
    save_workflow_state(project, alias, state_document(project, alias, run, run.currentStage, run.status))
    link_workflow_reference(project, alias, run, run.status)
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
