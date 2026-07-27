from __future__ import annotations

import copy
import re
import uuid
from pathlib import Path
from typing import Any

from verifysignal_spec.core.adapter import CoreAdapter
from verifysignal_spec.core.errors import CoreExecutionError, CoreIncompatibleError, CoreMissingError
from verifysignal_spec.core.executable_contract import ContractCompatibilityFinding, project_core_contract
from verifysignal_spec.commands import list as list_command
from verifysignal_spec.commands import repair as repair_command
from verifysignal_spec.commands import run as run_command
from verifysignal_spec.commands import validate as validate_command
from verifysignal_spec.workspace import layout
from verifysignal_spec.workspace.models import ArtifactReference, AuthoringQuestion
from verifysignal_spec.workspace.repository import get_core_command, load_document, load_use_case, now_iso, save_use_case

from .definitions import load_workflow_definition
from .browser_authoring import browser_authoring_contract
from .stage_contracts import stage_contracts_payload
from .models import WORKFLOW_ID, WORKFLOW_STAGES, ArtifactPlan, WorkflowRun, native_invocation
from .repository import (
    create_or_load_use_case,
    create_stage_states,
    ensure_workflow_workspace,
    import_legacy_use_case,
    link_workflow_reference,
    list_workflow_runs,
    load_artifact_plan,
    load_workflow_run,
    load_workflow_state,
    project_relative,
    save_artifact_plan,
    save_workflow_run,
    save_workflow_state,
    state_document,
    workflow_dir_rel,
)
from .stage_documents import write_artifact_plan, write_clarifications, write_handoff, write_specification, write_validation_summary
from .stages import initialize_understanding
from .tasks import generate_authoring_tasks
from .stage_documents import write_task_set
from .repository import save_task_set


def slug_from_goal(goal: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", goal.lower()).strip("-")
    return (slug[:40].strip("-") or "use-case")


def choose_integration(project: Path, requested: str | None = None) -> str:
    if requested:
        return requested
    from verifysignal_spec.integrations.manifests import load_all_states

    states = load_all_states(project).get("integrations", {})
    for key, value in states.items():
        if isinstance(value, dict) and value.get("default"):
            return key
    return "codex"


def next_command(stage: str, alias: str, integration: str | None = None) -> str:
    invocation = native_invocation(stage, "skill")
    return f"{invocation} {alias}".strip()


def create_workflow_run(project: Path, goal: str, alias: str | None = None, integration: str | None = None) -> WorkflowRun:
    alias = layout.ensure_path_safe_alias(alias or slug_from_goal(goal))
    integration = choose_integration(project, integration)
    ensure_workflow_workspace(project, alias)
    record = create_or_load_use_case(project, alias, goal)
    _reset_target_confirmation_for_new_run(record)
    save_use_case(project, record)
    initialized = initialize_understanding(project, alias, goal)
    run_id = (
        f"wf-{now_iso().replace('-', '').replace(':', '').replace('Z', '').replace('T', '-')}"
        f"-{uuid.uuid4().hex[:8]}-{alias}"
    )
    run = WorkflowRun(
        runId=run_id,
        useCaseAlias=alias,
        integration=integration,
        status="paused",
        currentStage="understand",
        startedAt=now_iso(),
        updatedAt=now_iso(),
        workflowDir=workflow_dir_rel(project, alias),
        stageStates=create_stage_states(project, alias),
        nextCommand=next_command("understand", alias, integration),
        resumeCommand=f"verifysignal workflow resume {run_id}",
    )
    run.stageStates[0].status = "completed"
    run.stageStates[0].completedAt = now_iso()
    run.stageStates[0].handoffSummary = "Repository understanding initialized."
    save_workflow_run(project, run)
    save_workflow_state(project, alias, state_document(project, alias, run, run.currentStage, run.status))
    link_workflow_reference(project, alias, run, run.status)
    return run


def _reset_target_confirmation_for_new_run(record: Any) -> None:
    workflow = dict(record.workflow or {})
    decisions = [
        dict(item)
        for item in workflow.get("stageHandoffDecisions", [])
        if isinstance(item, dict)
    ]
    prior_target: str | None = None
    for decision in decisions:
        if decision.get("key") == "browserTargetEnvironment":
            prior_target = str(decision.get("valueSummary") or "").strip() or prior_target
            decision["status"] = "stale"
    if decisions:
        workflow["stageHandoffDecisions"] = decisions
        record.workflow = workflow
    question = next(
        (
            item
            for item in record.authoringQuestions
            if item.id == "browser-target-environment"
        ),
        None,
    )
    if not question and prior_target:
        question = AuthoringQuestion(
            id="browser-target-environment",
            prompt="Which target application environment should this browser validation run against?",
            reason="Browser validation requires confirmation for each workflow run.",
            affects="runtimeInputs.baseUrl",
            requiresConfirmation=True,
        )
        record.authoringQuestions.append(question)
    if question:
        previous = (
            str(question.answerSummary or "").strip()
            or str((question.suggestedAnswer or {}).get("baseUrl") or "").strip()
            or prior_target
        )
        question.status = "pending"
        question.answerSummary = None
        question.confirmationSource = None
        question.requiresConfirmation = True
        if previous:
            question.suggestedAnswer = {"baseUrl": previous}
            question.suggestionSource = "previous-workflow"


def resume_workflow(project: Path, run_id: str) -> WorkflowRun:
    run = load_workflow_run(project, run_id)
    if run.status in {"completed", "failed"}:
        return run
    run.status = "paused"
    run.resumeCommand = f"verifysignal workflow resume {run.runId}"
    if not run.nextCommand:
        run.nextCommand = next_command(run.currentStage, run.useCaseAlias, run.integration)
    save_workflow_run(project, run)
    return run


def workflow_status(project: Path, run_id: str | None = None) -> dict[str, Any]:
    run = load_workflow_run(project, run_id) if run_id else (list_workflow_runs(project)[0] if list_workflow_runs(project) else None)
    if not run:
        return {"schemaVersion": "verifysignal-spec-workflow-status/v1", "status": "not-started", "runs": []}
    state = load_workflow_state(project, run.useCaseAlias)
    return {
        "schemaVersion": "verifysignal-spec-workflow-status/v1",
        "runId": run.runId,
        "workflowId": run.workflowId,
        "useCaseAlias": run.useCaseAlias,
        "status": run.status,
        "currentStage": run.currentStage,
        "integration": run.integration,
        "workflowDir": run.workflowDir,
        "nextCommand": run.nextCommand,
        "resumeCommand": run.resumeCommand,
        "stageStates": [item.to_dict() for item in run.stageStates],
        "state": state,
    }


def workflow_status_for_alias(project: Path, alias: str) -> dict[str, Any]:
    alias = layout.ensure_path_safe_alias(alias)
    record = load_use_case(project, alias)
    state = load_workflow_state(project, alias)
    workflow = record.workflow or {}
    run_id = workflow.get("lastWorkflowRunId")
    if run_id:
        try:
            return workflow_status(project, str(run_id))
        except FileNotFoundError:
            pass
    return {
        "schemaVersion": "verifysignal-spec-workflow-status/v1",
        "useCaseAlias": alias,
        "status": state.get("status") or workflow.get("workflowStatus") or record.status,
        "currentStage": state.get("currentStage") or workflow.get("currentStage"),
        "workflowDir": workflow.get("workflowDir") or workflow_dir_rel(project, alias),
        "nextCommand": state.get("nextCommand"),
        "state": state,
    }


def workflow_show(project: Path, alias: str) -> dict[str, Any]:
    alias = layout.ensure_path_safe_alias(alias)
    record = load_use_case(project, alias)
    state = load_workflow_state(project, alias)
    documents = {
        stage: _workflow_document(project, alias, stage)
        for stage in ["understand", "specify", "clarify", "plan", "tasks", "implement", "validate", "run", "repair"]
    }
    artifact_plan = load_document(layout.workflow_stage_document_path(project, alias, "plan").with_suffix(".yaml"), default={}) or {}
    task_set = load_document(layout.workflow_stage_document_path(project, alias, "tasks").with_suffix(".yaml"), default={}) or {}
    return {
        "schemaVersion": "verifysignal-spec-workflow-show/v1",
        "useCaseAlias": alias,
        "status": state.get("status") or record.status,
        "currentStage": state.get("currentStage") or (record.workflow or {}).get("currentStage"),
        "useCase": record.to_dict(),
        "workflowState": state,
        "documents": documents,
        "artifactPlan": artifact_plan,
        "taskSet": task_set,
    }


def _workflow_document(project: Path, alias: str, stage: str) -> dict[str, Any]:
    path = layout.workflow_stage_document_path(project, alias, stage)
    if not path.exists():
        return {"path": project_relative(project, path), "exists": False}
    return {
        "path": project_relative(project, path),
        "exists": True,
        "content": path.read_text(encoding="utf-8"),
    }


def workflow_list(project: Path) -> dict[str, Any]:
    return {
        "schemaVersion": "verifysignal-spec-workflow-list/v1",
        "runs": [
            {
                "runId": run.runId,
                "workflowId": run.workflowId,
                "useCaseAlias": run.useCaseAlias,
                "status": run.status,
                "currentStage": run.currentStage,
                "integration": run.integration,
                "updatedAt": run.updatedAt,
            }
            for run in list_workflow_runs(project)
        ],
    }


def workflow_info(project: Path, workflow_id: str = WORKFLOW_ID, integration: str | None = None) -> dict[str, Any]:
    definition = load_workflow_definition(project, workflow_id)
    integration = choose_integration(project, integration)
    core_contract = _core_executable_contract(project)
    return {
        "schemaVersion": "verifysignal-spec-workflow-info/v1",
        "workflowId": definition.workflowId,
        "name": definition.name,
        "version": definition.version,
        "stages": definition.stages,
        "gates": definition.gates,
        "supportedIntegrations": ["codex", "claude"],
        "nativeCommands": {stage: native_invocation(stage, "skill") for stage in [*WORKFLOW_STAGES, "list"]},
        "stagePayloadContracts": stage_contracts_payload(),
        "coreExecutableContract": core_contract,
        "browserAuthoringContract": browser_authoring_contract(core_contract=core_contract),
        "specWorkflowPolicy": _spec_workflow_policy(),
        "integration": integration,
    }


def _core_executable_contract(project: Path) -> dict[str, Any]:
    command = get_core_command(project)
    adapter = CoreAdapter(executable=command, cwd=project)
    try:
        compatibility = adapter.check_compatibility()
        if not compatibility.compatible:
            return _blocked_core_contract(
                "core-contract.bootstrap-incompatible",
                compatibility.message,
                contract_version=compatibility.contractVersion,
                core_version=compatibility.verifysignalVersion,
            )
        raw = adapter.contracts()
        return _apply_public_redaction_policy(
            project_core_contract(
                raw,
                runtime_identity=adapter.executable,
                core_version=compatibility.verifysignalVersion,
                public_contract_version=compatibility.contractVersion,
            )
        )
    except (CoreMissingError, CoreIncompatibleError, CoreExecutionError) as exc:
        return _blocked_core_contract("core-contract.discovery-failed", str(exc))
    except Exception as exc:
        return _blocked_core_contract("core-contract.discovery-error", str(exc))


def _blocked_core_contract(
    code: str,
    message: str,
    *,
    contract_version: str | None = None,
    core_version: str | None = None,
) -> dict[str, Any]:
    finding = ContractCompatibilityFinding(code=code, message=message, contractSection="contracts").to_dict()
    return {
        "source": "core-public-contract",
        "runtimeIdentity": None,
        "coreVersion": core_version,
        "publicContractVersion": contract_version,
        "schemaVersion": None,
        "sections": {
            "operations": {},
            "runRequest": {},
            "skill": {},
            "browserWorkflow": {},
            "credentials": {},
            "placeholders": {},
            "reportCoverage": {},
            "publicRedactionPolicy": {},
            "runtimeTrustHandoff": {},
        },
        "stableOnlyAuthoring": True,
        "findings": [finding],
    }


def _apply_public_redaction_policy(core_contract: dict[str, Any]) -> dict[str, Any]:
    redacted = copy.deepcopy(core_contract)
    policy = redacted.get("sections", {}).get("publicRedactionPolicy", {})
    redact_fields = _public_redaction_field_names(policy)
    if not redact_fields:
        return redacted
    _redact_named_fields(redacted, redact_fields)
    return redacted


def _public_redaction_field_names(policy: Any) -> set[str]:
    redact_fields = {"runtimeIdentity", "runtimeCommand", "credentialValues"}
    if not isinstance(policy, dict):
        return redact_fields
    redact_fields.update(_string_items(policy.get("redactFields")))
    redact_fields.update(_string_items(policy.get("publicOutputForbiddenFields")))
    public_error_shape = policy.get("publicErrorShape") if isinstance(policy.get("publicErrorShape"), dict) else {}
    safe_evidence = policy.get("safeEvidenceReferences") if isinstance(policy.get("safeEvidenceReferences"), dict) else {}
    redact_fields.update(_string_items(public_error_shape.get("forbiddenFields")))
    redact_fields.update(_string_items(safe_evidence.get("forbiddenFields")))
    return {field for field in redact_fields if field}


def _string_items(value: Any) -> set[str]:
    if not isinstance(value, list):
        return set()
    return {str(item) for item in value if item}


def _redact_named_fields(value: Any, redact_fields: set[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in redact_fields and child not in {None, ""}:
                value[key] = "[redacted]"
            else:
                _redact_named_fields(child, redact_fields)
    elif isinstance(value, list):
        for child in value:
            _redact_named_fields(child, redact_fields)


def _spec_workflow_policy() -> dict[str, Any]:
    return {
        "source": "verifysignal-spec",
        "policies": [
            {"name": "stage-order", "description": "Use case workflows progress through understand, specify, clarify, plan, tasks, implement, validate, run, repair."},
            {"name": "one-run-request-per-use-case", "description": "Each use case references exactly one run request."},
            {"name": "reusable-skills", "description": "Skills are decoupled reusable artifacts and may be shared by run requests."},
            {"name": "gate-adequacy", "description": "Spec evaluates whether Core evidence adequately proves planned gates."},
            {"name": "workspace-portability", "description": "Target-project state remains under .verifysignal/."},
        ],
    }


def specify(project: Path, alias: str, goal: str) -> dict[str, Any]:
    ensure_workflow_workspace(project, alias)
    create_or_load_use_case(project, alias, goal)
    write_specification(project, alias, goal)
    return {"alias": alias, "documentPath": project_relative(project, layout.workflow_stage_document_path(project, alias, "specify"))}


def clarify(project: Path, alias: str, questions: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    questions = questions or [{"prompt": "What target URL, credential group, and success evidence should this use case use?", "status": "pending"}]
    write_clarifications(project, alias, questions)
    return {"alias": alias, "questions": questions}


def plan_artifacts(project: Path, alias: str) -> ArtifactPlan:
    plan = ArtifactPlan(
        useCaseAlias=alias,
        runRequest=f".verifysignal/run-requests/{alias}.yaml",
        mainSkill=f".verifysignal/skills/{alias}.browser.md",
        supportingSkills=[],
        runtimeInputs=[{"name": "baseUrl", "kind": "parameter"}, {"name": "qa-user", "kind": "credential"}],
        validationGates=["authoring-check", "runtime-readiness"],
    )
    save_artifact_plan(project, plan)
    write_artifact_plan(project, plan)
    return plan


def generate_tasks(project: Path, alias: str) -> dict[str, Any]:
    plan = load_artifact_plan(project, alias)
    task_set = generate_authoring_tasks(project, plan)
    task_set.generatedAt = now_iso()
    save_task_set(project, task_set)
    write_task_set(project, task_set)
    return task_set.to_dict()


def implement_artifacts(project: Path, alias: str) -> dict[str, Any]:
    from verifysignal_spec.workspace import artifacts

    plan = load_artifact_plan(project, alias)
    record = load_use_case(project, alias)
    record.runRequest = ArtifactReference(path=plan.runRequest, kind="run-request", generated=True, id=f"request.{alias}", version="1.0.0")
    record.mainSkill = ArtifactReference(path=plan.mainSkill, kind="skill", generated=True, id=f"skill.{alias}", version="1.0.0")
    record.skills = [record.mainSkill, *[ArtifactReference(path=path, kind="skill", generated=True) for path in plan.supportingSkills]]
    record.status = "draft"
    artifacts.write_generated_artifacts(project, record)
    save_use_case(project, record)
    write_handoff(project, alias, "implement", "Draft artifacts were generated from the approved artifact plan. Validation is still required.")
    return {"alias": alias, "status": record.status, "runRequest": plan.runRequest, "skills": [skill.path for skill in record.skills]}


def validate_stage(project: Path, alias: str, core_cmd: str | None = None) -> dict[str, Any]:
    result = validate_command.run(project, alias, runtime_readiness=True, core_cmd=core_cmd)
    write_validation_summary(project, alias, result, stage="validate")
    return result


def run_stage(project: Path, alias: str, core_cmd: str | None = None, non_interactive: bool = True) -> dict[str, Any]:
    result = run_command.run(project, alias, interactive=not non_interactive, core_cmd=core_cmd)
    write_validation_summary(project, alias, result, stage="run")
    return result


def classify_repair_stage(finding: dict[str, Any]) -> str:
    text = " ".join(str(value).lower() for value in finding.values())
    if any(term in text for term in ["requirement", "expected", "product", "missing context"]):
        return "clarify"
    if any(term in text for term in ["skill reuse", "artifact plan", "wrong skill", "run request"]):
        return "plan"
    if "task" in text or "fingerprint" in text:
        return "tasks"
    return "implement"


def repair_stage(project: Path, alias: str, from_report: str | None = None, approve: bool = False, core_cmd: str | None = None) -> dict[str, Any]:
    result = repair_command.run(project, alias, from_report=from_report, approve=approve, core_cmd=core_cmd)
    findings = result.get("repair", {}).get("findings", [])
    revisit = classify_repair_stage(findings[0]) if findings else "implement"
    result["returnStage"] = revisit
    write_handoff(project, alias, "repair", f"Repair should revisit {revisit} before edits are approved.")
    return result


def non_ai_list(project: Path) -> dict[str, Any]:
    return list_command.run(project)
