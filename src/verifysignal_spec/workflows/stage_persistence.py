from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from verifysignal_spec.workspace import artifacts, layout
from verifysignal_spec.workspace.models import ArtifactReference, AuthoringQuestion, CredentialReadinessHint, RefreshImpactResult, RuntimeInputRequirement
from verifysignal_spec.workspace.product_context import load_product_context, save_product_context
from verifysignal_spec.workspace.repository import (
    capability_stamp,
    get_core_command,
    get_entitlement_api_base_url,
    init_workspace,
    load_registry,
    load_use_case,
    now_iso,
    save_credential_readiness_hint,
    save_refresh_impact,
    save_use_case,
)
from verifysignal_spec.workspace.validation import validate_credential_readiness_hint, validate_no_secret_values

from .coverage_inventory import candidate_dicts, classify_refresh_impacts, merge_inventory, normalize_scope
from .authoring_coherence import evaluate_implementation_coherence, normalize_artifact_aliases
from .browser_authoring import validate_browser_payload
from .browser_understanding import normalize_browser_understanding_payload
from .models import (
    WORKFLOW_STAGES,
    ArtifactPlan,
    AuthoringTask,
    AuthoringTaskSet,
    ManagedWorkspaceArtifact,
    ReadinessBlocker,
    StagePersistenceResult,
    UnderstandingOnboardingResult,
)
from .prerequisites import current_git_hash
from .repository import (
    create_or_load_use_case,
    ensure_workflow_workspace,
    fingerprint_text,
    project_relative,
    load_artifact_plan,
    save_artifact_plan,
    save_task_set,
)
from .skill_execution_boundary import multi_skill_capability, resolve_execution_boundary
from .stage_documents import (
    write_artifact_plan,
    write_clarifications,
    write_global_understanding,
    write_handoff,
    write_specification,
    write_task_set,
)
from .stage_contracts import StagePayloadContractError, missing_required_field_error, unsupported_field_warnings
from .transitions import transition_workflow, validate_workflow_stage_position

PERSISTABLE_STAGES = {"understand", "specify", "clarify", "plan", "tasks", "implement"}
BLOCKING_CLARIFICATION_AREAS = {"runtime", "data", "credential", "credentials", "permission", "permissions", "outcome", "expectedOutcome"}


def persist_stage(
    project: Path,
    stage: str,
    *,
    alias: str | None = None,
    scope: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if stage not in PERSISTABLE_STAGES:
        return _blocked(
            stage,
            alias,
            code="stage.unsupported",
            message=f"Stage {stage} cannot be persisted. Supported stages: {', '.join(sorted(PERSISTABLE_STAGES))}.",
            invalid=True,
        )
    try:
        normalized_scope = normalize_scope(scope)
    except ValueError as exc:
        return _blocked(stage, alias, code="scope.invalid", message=str(exc), invalid=True)

    content = _payload_content(payload or {})
    if stage == "understand":
        try:
            content = _normalize_understanding_content(content)
        except ValueError as exc:
            return _blocked(
                stage,
                None,
                code="payload.invalid",
                message=str(exc),
                invalid=True,
            )
    resolved_alias = alias or content.get("alias")
    public_contract_warnings = unsupported_field_warnings(stage, content)
    findings = validate_no_secret_values(content)
    if findings:
        first = findings[0]
        return _blocked(
            stage,
            resolved_alias,
            code="payload.secret-looking-value",
            message=f"Secret-looking value must not be persisted at {first.get('path')}.",
            invalid=True,
        )

    project = project.resolve()
    workspace_file = layout.workspace_root(project) / layout.WORKSPACE_FILE
    if not workspace_file.exists():
        init_workspace(project)
    try:
        if stage == "understand":
            result = _persist_understanding(project, content, normalized_scope)
        elif stage == "specify":
            result = _persist_specification(project, str(resolved_alias or ""), content)
        elif stage == "clarify":
            result = _persist_clarifications(project, str(resolved_alias or ""), content)
        elif stage == "plan":
            result = _persist_plan(project, str(resolved_alias or ""), content)
        elif stage == "tasks":
            result = _persist_tasks(project, str(resolved_alias or ""), content)
        else:
            result = _persist_implementation(project, str(resolved_alias or ""), content)
    except StagePayloadContractError as exc:
        finding = exc.finding
        return _blocked(
            stage,
            resolved_alias,
            code="payload.missing-required-field",
            message=finding.message,
            invalid=True,
            recovery_command="verifysignal workflow info verifysignal-use-case --json",
            documentation_ref=f"stagePayloadContracts.{stage}.requiredFields",
            warnings=public_contract_warnings,
        )
    except ValueError as exc:
        return _blocked(stage, resolved_alias, code="payload.invalid", message=str(exc), invalid=True)
    except FileNotFoundError as exc:
        return _blocked(stage, resolved_alias, code="workspace.missing", message=str(exc))
    if public_contract_warnings:
        result.warnings.extend(public_contract_warnings)
    return result.to_dict()


def unresolved_blocking_questions(project: Path, alias: str) -> list[dict[str, Any]]:
    try:
        record = load_use_case(project, alias)
    except FileNotFoundError:
        return []
    blockers: list[dict[str, Any]] = []
    for question in record.authoringQuestions:
        if question.status == "answered":
            continue
        affected = f"{question.affects or ''} {question.reason}".lower()
        if any(area.lower() in affected for area in BLOCKING_CLARIFICATION_AREAS):
            blockers.append(question.to_dict())
    return blockers


def _persist_understanding(project: Path, content: dict[str, Any], scope: str) -> StagePersistenceResult:
    content = _normalize_understanding_content(content)
    mode = str(content.get("understandingMode") or "repository")
    if mode == "repository":
        _require_fields(content, ["repositorySummary", "localStartInstructions", "coverageInventory"])
    elif mode == "browser-first":
        _require_fields(
            content,
            [
                "productSummary",
                "targetEnvironment",
                "explorationScope",
                "productSignals",
                "coverageInventory",
            ],
        )
    else:
        _require_fields(
            content,
            [
                "repositorySummary",
                "localStartInstructions",
                "targetEnvironment",
                "explorationScope",
                "productSignals",
                "coverageInventory",
            ],
        )
    context = load_product_context(project)
    existing_inventory = context.get("coverageInventory")
    inventory = merge_inventory(existing_inventory, content.get("coverageInventory"), scope=scope)
    if mode == "browser-first":
        inventory.generatedGitHash = None
        inventory.gitAvailable = False
        inventory.sourceFilesVisited = 0
        inventory.sourceTraceabilityStatus = "missing"
    generated_at = inventory.generatedAt or now_iso()
    generated_git_hash = None
    if mode != "browser-first":
        generated_git_hash = content.get("generatedGitHash") or inventory.generatedGitHash or current_git_hash(project)
    git_available = mode != "browser-first" and (
        bool(generated_git_hash) or bool(content.get("gitAvailable"))
    )

    partial_reasons = list(inventory.partialInventoryReasons or content.get("partialInventoryReasons", []))
    source_traceability_status = inventory.sourceTraceabilityStatus
    trivial_candidate_count = _trivial_candidate_count(inventory)
    source_files_visited = inventory.sourceFilesVisited or int(content.get("sourceFilesVisited", 0) or 0)
    target_environment = content.get("targetEnvironment") if isinstance(content.get("targetEnvironment"), dict) else None
    product_signals = list(content.get("productSignals", []))
    gaps = [str(item) for item in content.get("gaps", [])]
    provenance_status = str(
        content.get("provenanceTraceabilityStatus")
        or ("complete" if mode == "repository" else "partial")
    )
    runtime_requirements = _understanding_runtime_requirements(
        content.get("knownRuntimeRequirements"),
        context.get("knownRuntimeRequirements"),
        target_environment,
    )
    context.update(
        {
            "workspaceKind": content.get("workspaceKind") or ("engagement" if mode == "browser-first" else mode),
            "understandingMode": mode,
            "productSummary": content.get("productSummary") or content["repositorySummary"],
            "repositorySummary": content["repositorySummary"],
            "localStartInstructions": content["localStartInstructions"],
            "safeInspectionPaths": content.get("safeInspectionPaths", context.get("safeInspectionPaths", [])),
            "blockedSensitivePaths": content.get("blockedSensitivePaths", context.get("blockedSensitivePaths", [])),
            "validationGoals": content.get("validationGoals", context.get("validationGoals", [])),
            "knownRuntimeRequirements": runtime_requirements,
            "coverageInventory": inventory.to_dict(),
            "candidateUseCases": candidate_dicts(inventory),
            "understanding": {
                "generatedAt": generated_at,
                "generatedGitHash": generated_git_hash,
                "gitAvailable": git_available,
                "mode": mode,
                "staleReasons": [],
                "inventoryStatus": inventory.status,
                "inventoryScope": scope,
                "sourceFilesVisited": source_files_visited,
                "candidateCount": len(inventory.candidateUseCases),
                "trivialCandidateCount": trivial_candidate_count,
                "sourceTraceabilityStatus": source_traceability_status,
                "provenanceTraceabilityStatus": provenance_status,
                "partialInventoryReasons": partial_reasons,
                "gaps": gaps,
                "recommendedFollowUpScope": _recommended_follow_up_scope(inventory.status, scope),
            },
        }
    )
    if target_environment:
        context["targetEnvironment"] = target_environment
        context["explorationScope"] = content["explorationScope"]
        context["productSignals"] = product_signals
        context["understanding"]["observedAt"] = content.get("observedAt") or target_environment.get("observedAt")
    if mode != "browser-first" and not generated_git_hash and not content.get("gitUnavailableReason"):
        raise ValueError("Understanding payload requires generatedGitHash or gitUnavailableReason.")
    if content.get("gitUnavailableReason"):
        context["understanding"]["gitUnavailableReason"] = content.get("gitUnavailableReason")

    save_product_context(project, context)
    _persist_refresh_impacts(project, content, existing_inventory, content.get("coverageInventory"), generated_at)
    write_global_understanding(project, context)
    understanding_onboarding = UnderstandingOnboardingResult(
        status=inventory.status if inventory.status in {"complete", "partial", "stale"} else "partial",
        scope=scope,
        generatedGitHash=generated_git_hash,
        sourceFilesVisited=source_files_visited,
        candidateCount=len(inventory.candidateUseCases),
        trivialCandidateCount=trivial_candidate_count,
        sourceTraceabilityStatus=source_traceability_status,
        partialInventoryReasons=partial_reasons,
        understandingMode=mode,
        workspaceKind=context.get("workspaceKind"),
        targetEnvironment=target_environment,
        productSignalCount=len(product_signals),
        provenanceTraceabilityStatus=provenance_status,
        gaps=gaps,
        nextAction="/verifysignal-specify" if inventory.status == "complete" else "/verifysignal-understand --scope continue",
    ).to_dict()
    return StagePersistenceResult(
        stage="understand",
        status="persisted",
        writtenArtifacts=[
            _artifact(project, layout.product_context_path(project), "product-context"),
            _artifact(project, layout.workflow_global_understanding_path(project), "understanding"),
        ],
        updatedRecords=["product-context", "coverage-inventory"],
        warnings=_inventory_warnings(inventory.status, partial_reasons=partial_reasons),
        understandingOnboarding=understanding_onboarding,
        nextCommand="/verifysignal-specify",
    )


def _persist_refresh_impacts(
    project: Path,
    content: dict[str, Any],
    existing_inventory: dict[str, Any] | None,
    incoming_inventory: dict[str, Any] | None,
    generated_at: str,
) -> None:
    explicit = content.get("refreshImpacts")
    if isinstance(explicit, list):
        for item in explicit:
            if isinstance(item, dict):
                impact = RefreshImpactResult.from_dict(item)
                if not impact.generatedAt:
                    impact.generatedAt = generated_at
                save_refresh_impact(project, impact)
        return
    records = []
    registry = load_registry(project)
    for entry in registry.get("useCases", []):
        alias = entry.get("alias") if isinstance(entry, dict) else getattr(entry, "alias", None)
        if not alias:
            continue
        try:
            records.append(load_use_case(project, str(alias)))
        except FileNotFoundError:
            continue
    for impact in classify_refresh_impacts(existing_inventory, incoming_inventory, records, generated_at=generated_at):
        save_refresh_impact(project, impact)


def _persist_specification(project: Path, alias: str, content: dict[str, Any]) -> StagePersistenceResult:
    alias = _alias(alias)
    content = _normalize_specification_content(project, alias, content)
    _require_fields(content, ["surface", "behavior", "expectedOutcome"], stage="specify")
    if not (content.get("sourceInventoryItems") or content.get("customSourceReason")):
        raise ValueError("Specification payload requires sourceInventoryItems or customSourceReason.")
    validate_workflow_stage_position(project, alias, "specify")
    ensure_workflow_workspace(project, alias)
    goal = str(content["behavior"])
    record = create_or_load_use_case(project, alias, goal)
    record.title = content.get("title") or alias.replace("-", " ").title()
    record.description = goal
    record.targetSurface = str(content.get("surface") or "browser")
    record.status = "draft"
    target = _extract_target_environment(content, source_stage="specify")
    if target:
        _ensure_browser_target_question(
            record,
            locator=target["locator"],
            suggestion_source=target.get("suggestionSource") or "specification-artifact",
        )
    elif _is_browser_use_case(content):
        _ensure_browser_target_question(record)
    _apply_write_flow_fields(project, record, content)
    save_use_case(project, record)
    runtime = [str(item) for item in content.get("runtimeAssumptions", [])]
    write_specification(project, alias, goal, runtime_assumptions=runtime)
    transition_workflow(
        project,
        alias,
        stage="specify",
        outcome="completed",
        document_path=project_relative(
            project,
            layout.workflow_stage_document_path(project, alias, "specify"),
        ),
        handoff_summary="The use-case specification was persisted.",
    )
    return StagePersistenceResult(
        stage="specify",
        alias=alias,
        status="persisted",
        writtenArtifacts=[
            _artifact(project, layout.use_case_path(project, alias), "use-case"),
            _artifact(project, layout.workflow_stage_document_path(project, alias, "specify"), "specification"),
            _artifact(project, layout.workflow_state_path(project, alias), "workflow-state"),
            _artifact(project, layout.registry_path(project), "registry"),
        ],
        updatedRecords=[f"use-cases/{alias}", "registry"],
        nextCommand=f"/verifysignal-clarify {alias}",
    )


def _persist_clarifications(project: Path, alias: str, content: dict[str, Any]) -> StagePersistenceResult:
    alias = _alias(alias)
    record = load_use_case(project, alias)
    if "questions" not in content and not content.get("answers"):
        raise ValueError("Clarification payload requires questions or answers.")
    validate_workflow_stage_position(project, alias, "clarify")
    if "questions" in content:
        questions = [_question_from_dict(item) for item in content.get("questions", [])]
        existing_target = next(
            (
                item
                for item in record.authoringQuestions
                if item.id == "browser-target-environment"
            ),
            None,
        )
        incoming_target = next(
            (
                item
                for item in questions
                if item.id == "browser-target-environment"
            ),
            None,
        )
        if existing_target and not incoming_target:
            questions.append(existing_target)
        elif existing_target and incoming_target:
            incoming_target.suggestedAnswer = (
                incoming_target.suggestedAnswer or existing_target.suggestedAnswer
            )
            incoming_target.suggestionSource = (
                incoming_target.suggestionSource or existing_target.suggestionSource
            )
            incoming_target.requiresConfirmation = True
    else:
        questions = list(record.authoringQuestions)
    confirmed_target: dict[str, str] | None = None
    for answer in content.get("answers", []):
        answer_target = _apply_answer(questions, answer)
        if answer_target:
            confirmed_target = answer_target
    record.authoringQuestions = questions
    target_confirmation = None
    if confirmed_target:
        target = confirmed_target["locator"]
        _upsert_stage_handoff_decision(record, target, source_stage="clarify")
        target_confirmation = {
            "url": target,
            "source": confirmed_target["source"],
            "questionId": "browser-target-environment",
        }
    _apply_write_flow_fields(project, record, content)
    save_use_case(project, record)
    write_clarifications(project, alias, [question.to_dict() for question in questions])
    blockers = unresolved_blocking_questions(project, alias)
    warnings = ["Blocking environment-dependent questions remain unresolved."] if blockers else []
    transition_blockers = (
        [
            ReadinessBlocker(
                code="clarification.unresolved-blocking",
                message=(
                    "Runtime, data, credential, permission, or outcome "
                    "clarifications remain unresolved."
                ),
                recoveryCommand=f"/verifysignal-clarify {alias}",
            ).to_dict()
        ]
        if blockers
        else []
    )
    transition_workflow(
        project,
        alias,
        stage="clarify",
        outcome="blocked" if blockers else "completed",
        blockers=transition_blockers,
        document_path=project_relative(
            project,
            layout.workflow_stage_document_path(project, alias, "clarify"),
        ),
        target_confirmation=target_confirmation,
        handoff_summary=(
            "Clarifications remain blocked."
            if blockers
            else "Clarifications were persisted and blocking questions resolved."
        ),
    )
    return StagePersistenceResult(
        stage="clarify",
        alias=alias,
        status="persisted",
        writtenArtifacts=[
            _artifact(project, layout.use_case_path(project, alias), "use-case"),
            _artifact(project, layout.workflow_stage_document_path(project, alias, "clarify"), "clarifications"),
            _artifact(project, layout.workflow_state_path(project, alias), "workflow-state"),
            _artifact(project, layout.registry_path(project), "registry"),
        ],
        updatedRecords=[f"use-cases/{alias}", "registry"],
        warnings=warnings,
        nextCommand=(
            f"/verifysignal-clarify {alias}"
            if blockers
            else f"/verifysignal-plan {alias}"
        ),
    )


def _persist_plan(project: Path, alias: str, content: dict[str, Any]) -> StagePersistenceResult:
    alias = _alias(alias)
    content = _normalize_plan_content(alias, content)
    record = load_use_case(project, alias)
    validate_workflow_stage_position(project, alias, "plan")
    supplied_target = _extract_target_environment(content, source_stage="plan")
    if supplied_target:
        _ensure_browser_target_question(
            record,
            locator=supplied_target["locator"],
            suggestion_source="plan-artifact",
        )
        save_use_case(project, record)
    target_question = next(
        (
            item
            for item in record.authoringQuestions
            if item.id == "browser-target-environment" and item.status != "answered"
        ),
        None,
    )
    if target_question:
        return StagePersistenceResult(
            stage="plan",
            alias=alias,
            status="blocked",
            blockers=[
                ReadinessBlocker(
                    code="clarification.target-environment-confirmation-required",
                    message="Confirm the recommended browser target or provide another target for this workflow.",
                    recoveryCommand=(
                        f"verifysignal workflow persist clarify --alias {alias} "
                        "--payload <target-confirmation.json> --json"
                    ),
                )
            ],
            nextCommand=f"/verifysignal-clarify {alias}",
        )
    content["runtimeInputs"] = _merge_resolved_target_runtime_input(
        content.get("runtimeInputs", []),
        _stage_handoff_target(record),
    )
    _apply_write_flow_fields(project, record, content)
    save_use_case(project, record)
    blockers = content.get("unresolvedBlockingClarifications") or unresolved_blocking_questions(project, alias)
    if blockers:
        return StagePersistenceResult(
            stage="plan",
            alias=alias,
            status="blocked",
            blockers=[
                ReadinessBlocker(
                    code="clarification.unresolved-blocking",
                    message="Planning is blocked by unresolved runtime, data, credential, permission, or outcome clarifications.",
                    recoveryCommand=f"verifysignal workflow persist clarify --alias {alias} --payload <answers.json> --json",
                )
            ],
            nextCommand=f"/verifysignal-clarify {alias}",
        )
    _require_fields(content, ["runRequest", "reusableSkills", "runtimeInputs"], stage="plan")
    gate_intent_blockers = _gate_intent_requiredness_blockers(project, alias, content)
    if gate_intent_blockers:
        return StagePersistenceResult(
            stage="plan",
            alias=alias,
            status="blocked",
            blockers=gate_intent_blockers,
            nextCommand=f"/verifysignal-plan {alias}",
        )
    run_request = _artifact_path(content["runRequest"], default=f".verifysignal/run-requests/{alias}.yaml")
    skill_paths = [_skill_path(item) for item in content.get("reusableSkills", [])]
    main_skill = _artifact_path(content.get("mainSkill") or (skill_paths[0] if skill_paths else f".verifysignal/skills/{alias}.browser.md"))
    supporting = [path for path in skill_paths if path != main_skill]
    plan = ArtifactPlan(
        useCaseAlias=alias,
        runRequest=run_request,
        mainSkill=main_skill,
        supportingSkills=supporting,
        sourceOnlySkills=[_skill_path(item) for item in content.get("sourceOnlySkills", [])] or supporting,
        skillReuse=list(content.get("skillReuse", [])),
        skillComposition=content.get("skillComposition") if isinstance(content.get("skillComposition"), dict) else None,
        gateEvidenceMappings=[item for item in content.get("gateEvidenceMappings", []) if isinstance(item, dict)],
        runtimeInputs=list(content.get("runtimeInputs", [])),
        preconditions=[str(item) for item in content.get("preconditions", [])],
        validationGates=list(content.get("validationGates", ["authoring-check", "runtime-readiness"])),
        gateIntentChanges=[item for item in content.get("gateIntentChanges", []) if isinstance(item, dict)],
    )
    save_artifact_plan(project, plan)
    write_artifact_plan(project, plan)
    transition_workflow(
        project,
        alias,
        stage="plan",
        outcome="completed",
        document_path=project_relative(
            project,
            layout.workflow_stage_document_path(project, alias, "plan"),
        ),
        handoff_summary="The artifact plan was persisted.",
    )
    return StagePersistenceResult(
        stage="plan",
        alias=alias,
        status="persisted",
        writtenArtifacts=[
            _artifact(project, layout.workflow_stage_document_path(project, alias, "plan"), "plan"),
            _artifact(project, layout.workflow_stage_document_path(project, alias, "plan").with_suffix(".yaml"), "artifact-plan"),
            _artifact(project, layout.workflow_state_path(project, alias), "workflow-state"),
        ],
        updatedRecords=[f"artifact-plans/{alias}"],
        nextCommand=f"/verifysignal-tasks {alias}",
    )


def _persist_tasks(project: Path, alias: str, content: dict[str, Any]) -> StagePersistenceResult:
    alias = _alias(alias)
    _require_fields(content, ["tasks"], stage="tasks")
    tasks = [AuthoringTask.from_dict(item if isinstance(item, dict) else {"id": f"T{index + 1:03d}", "description": str(item)}) for index, item in enumerate(content.get("tasks", []))]
    task_set = AuthoringTaskSet(
        taskSetId=f"tasks.{alias}",
        useCaseAlias=alias,
        sourcePlanPath=project_relative(project, layout.workflow_stage_document_path(project, alias, "plan").with_suffix(".yaml")),
        planFingerprint=fingerprint_text(str(content.get("dependencies", "")) + str(content.get("parallelizableGroups", "")) + str([task.to_dict() for task in tasks])),
        generatedAt=now_iso(),
        tasks=tasks,
    )
    validate_workflow_stage_position(project, alias, "tasks")
    save_task_set(project, task_set)
    write_task_set(project, task_set)
    transition_workflow(
        project,
        alias,
        stage="tasks",
        outcome="completed",
        document_path=project_relative(
            project,
            layout.workflow_stage_document_path(project, alias, "tasks"),
        ),
        handoff_summary="The authoring task set was persisted.",
    )
    return StagePersistenceResult(
        stage="tasks",
        alias=alias,
        status="persisted",
        writtenArtifacts=[
            _artifact(project, layout.workflow_stage_document_path(project, alias, "tasks"), "tasks"),
            _artifact(project, layout.workflow_stage_document_path(project, alias, "tasks").with_suffix(".yaml"), "task-set"),
            _artifact(project, layout.workflow_state_path(project, alias), "workflow-state"),
        ],
        updatedRecords=[f"tasks/{alias}"],
        nextCommand=f"/verifysignal-implement {alias}",
    )


def _preserve_prior_runtime_input_values(incoming: list[dict[str, Any]], prior: list[Any]) -> list[dict[str, Any]]:
    """Backfill a runtime input's value from the prior record when a re-persist payload omits it.

    Bug 2 (dogfood): re-persisting `implement` with runtimeInputs that drop `value`
    (persistValue:false style) zeroed previously author-supplied parameter values. Only backfill
    when BOTH `value` and `default` keys are ABSENT (so an explicit clear to "" is honored); skip
    credential and generated inputs.
    """
    prior_values: dict[str, Any] = {}
    for item in prior or []:
        name = getattr(item, "name", None)
        value = getattr(item, "value", None)
        kind = getattr(item, "kind", None)
        if name and kind != "credential" and value not in (None, ""):
            prior_values[name] = value
    merged: list[dict[str, Any]] = []
    for item in incoming:
        if (
            isinstance(item, dict)
            and item.get("kind") != "credential"
            and item.get("source") != "generated"
            and "value" not in item
            and "default" not in item
            and item.get("name") in prior_values
        ):
            item = {**item, "value": prior_values[item["name"]]}
        merged.append(item)
    return merged


def _persist_implementation(project: Path, alias: str, content: dict[str, Any]) -> StagePersistenceResult:
    alias = _alias(alias)
    content = _normalize_implementation_content(alias, content)
    _require_fields(content, ["runRequest", "skills"], stage="implement")
    record = load_use_case(project, alias)
    core_contract = _core_contract_for_browser_authoring(project)
    content = _apply_skill_boundary_composition(project, alias, content, core_contract=core_contract)
    coherence = evaluate_implementation_coherence(project, alias, content, new_artifacts=True, core_contract=core_contract)
    if coherence.status == "blocked":
        return StagePersistenceResult(
            stage="implement",
            alias=alias,
            status="blocked",
            blockers=[
                ReadinessBlocker(
                    code="authoring.coherence-blocked",
                    message=message,
                    recoveryCommand=f"verifysignal workflow show --alias {alias} --json",
                )
                for message in coherence.blockers
            ],
            warnings=coherence.warnings,
            nextCommand=f"/verifysignal-plan {alias}",
        )
    run_request_path = _artifact_path(content["runRequest"], default=f".verifysignal/run-requests/{alias}.yaml")
    if not run_request_path.startswith(f"{layout.WORKSPACE_DIR}/{layout.RUN_REQUESTS_DIR}/"):
        raise ValueError("Generated run requests must be under .verifysignal/run-requests/.")
    skills = [_skill_reference(item) for item in content.get("skills", [])]
    if not skills:
        raise ValueError("Implementation requires at least one browser skill.")
    credential_refs = _credential_refs_from_payload(content)
    session_ref = _session_ref_from_payload(content)
    plan = None
    try:
        plan = load_artifact_plan(project, alias)
        planned_main = next((skill for skill in skills if skill.path == plan.mainSkill), None)
        if not planned_main:
            raise ValueError(f"Planned main validation skill is missing: {plan.mainSkill}.")
        supporting = [skill for skill in skills if skill.path != planned_main.path]
        skills = [planned_main, *supporting]
    except FileNotFoundError:
        pass
    record.runRequest = ArtifactReference(path=run_request_path, kind="run-request", generated=True, id=f"request.{alias}", version="1.0.0")
    record.mainSkill = skills[0]
    record.skills = skills
    source_only_paths = set(plan.sourceOnlySkills if plan else [])
    capability = multi_skill_capability(core_contract)
    if not capability.supported:
        source_only_paths.update(skill.path for skill in skills[1:])
    record.sourceOnlySkills = [skill for skill in skills if skill.path in source_only_paths and skill.path != record.mainSkill.path]
    composition = content.get("skillComposition") if isinstance(content.get("skillComposition"), dict) else None
    if not composition and plan and isinstance(plan.skillComposition, dict):
        composition = plan.skillComposition
    if composition:
        record.skillComposition = composition
    runtime_inputs = content.get("runtimeInputs") or _runtime_inputs_from_run_request_payload(content.get("runRequest")) or _planned_runtime_inputs(project, alias)
    runtime_inputs = _merge_resolved_target_runtime_input(runtime_inputs, _stage_handoff_target(record))
    runtime_inputs = _filter_runtime_credential_inputs(runtime_inputs, credential_refs)
    runtime_inputs = _preserve_prior_runtime_input_values(runtime_inputs, record.runtimeInputs)
    content["runtimeInputs"] = runtime_inputs
    record.runtimeInputs = [_runtime_input(item) for item in runtime_inputs]
    record.credentialRefs = credential_refs
    record.sessionRef = session_ref
    record.credentialGroups = _credential_groups_from_refs(credential_refs)
    _apply_write_flow_fields(project, record, content)
    _infer_resource_identity_if_possible(record)
    _require_resource_identity_for_new_write(record)
    profiles = _profiles_from_payload(content)
    if profiles:
        from verifysignal_spec.workspace.models import RunProfile

        record.profiles = [RunProfile.from_dict(item) for item in profiles]
    record.artifactCapabilities = content.get("artifactCapabilities") if isinstance(content.get("artifactCapabilities"), dict) else {
        "status": "current",
        "stamp": capability_stamp(
            [
                "readiness-snapshot",
                "credential-readiness-hints",
                "explicit-confirmation",
                "generated-runtime-inputs",
                "resource-identity",
                "side-effect-lifecycle",
                "write-activity-interpretation",
            ],
            contract_version="verifysignal-spec-use-case/v1",
        ),
    }
    record.validation = {"status": coherence.status, "authoringCoherence": coherence.to_dict()}
    record.status = "draft"

    validate_workflow_stage_position(project, alias, "implement")
    run_request_schema = _artifact_schema_from_core_contract(core_contract, "runRequest", "qa-run-request/v1")
    skill_schema = _artifact_schema_from_core_contract(core_contract, "skill", "qa-skill/v1")
    run_request_content = _ensure_core_run_request_document(_artifact_content(content["runRequest"]), record, content, core_contract=core_contract)
    _write_payload_artifact(
        project,
        run_request_path,
        run_request_content,
        lambda: artifacts.render_run_request(record, schema_version=run_request_schema, core_contract=core_contract),
    )
    # Pair each skill reference to its ORIGINAL payload item by stable path, not by
    # position: `skills` was reordered main-first above while content["skills"] keeps its
    # authored order, so a positional zip would write a helper's content into the main
    # skill's path. `_skill_reference` derives `.path` deterministically from the payload
    # item, so the reference path is the stable join key back to the authored content.
    payload_by_path = {_skill_path(item): item for item in content.get("skills", [])}
    for skill in skills:
        item = payload_by_path.get(skill.path)
        if item is None:
            raise ValueError(f"No authored skill payload matches persisted skill path: {skill.path}.")
        skill_content = _ensure_core_skill_document(_artifact_content(item), record, skill, item, credential_refs=credential_refs, core_contract=core_contract)
        _write_payload_artifact(
            project,
            skill.path,
            skill_content,
            lambda record=record, skill=skill: artifacts.render_skill(record, skill, schema_version=skill_schema),
        )

    save_use_case(project, record)
    write_handoff(project, alias, "implement", "Draft canonical artifacts were persisted by verifysignal workflow persist implement. Validation is still required.")
    transition_workflow(
        project,
        alias,
        stage="implement",
        outcome="completed",
        document_path=project_relative(
            project,
            layout.workflow_stage_document_path(project, alias, "implement"),
        ),
        handoff_summary=(
            "Draft canonical artifacts were persisted; validation is required."
        ),
    )
    return StagePersistenceResult(
        stage="implement",
        alias=alias,
        status="persisted",
        writtenArtifacts=[
            _artifact(project, layout.project_relative_path(project, run_request_path), "run-request"),
            *[_artifact(project, layout.project_relative_path(project, skill.path), "skill") for skill in skills],
            _artifact(project, layout.use_case_path(project, alias), "use-case"),
            _artifact(project, layout.registry_path(project), "registry"),
            _artifact(project, layout.workflow_stage_document_path(project, alias, "implement"), "handoff"),
            _artifact(project, layout.workflow_state_path(project, alias), "workflow-state"),
        ],
        updatedRecords=[f"use-cases/{alias}", "registry"],
        warnings=coherence.warnings,
        nextCommand=f"/verifysignal-validate {alias}",
    )


def _payload_content(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("payload") if isinstance(payload.get("payload"), dict) else payload
    return dict(data)


def _normalize_understanding_content(content: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(content)
    git = normalized.get("git") if isinstance(normalized.get("git"), dict) else {}
    if git:
        normalized.setdefault("generatedGitHash", git.get("hash") or git.get("sha") or git.get("commit"))
        normalized.setdefault("gitAvailable", bool(git.get("available", True)))
        if git.get("branch"):
            normalized.setdefault("gitBranch", git.get("branch"))
    if "localStartInstructions" not in normalized and "startInstructions" in normalized:
        start = normalized["startInstructions"]
        if isinstance(start, dict):
            normalized["localStartInstructions"] = "; ".join(f"{key}: {value}" for key, value in start.items())
        else:
            normalized["localStartInstructions"] = str(start)
    if "safeInspectionPaths" not in normalized and "safePaths" in normalized:
        normalized["safeInspectionPaths"] = normalized["safePaths"]
    if "generatedGitHash" not in normalized:
        normalized["generatedGitHash"] = normalized.get("gitHash") or normalized.get("commitHash") or normalized.get("generatedCommitHash")
    inventory = dict(normalized.get("coverageInventory") or {})
    if normalized.get("candidateUseCases") and not inventory.get("candidateUseCases"):
        inventory["candidateUseCases"] = normalized["candidateUseCases"]
    if normalized.get("generatedGitHash") and not inventory.get("generatedGitHash"):
        inventory["generatedGitHash"] = normalized["generatedGitHash"]
    if normalized.get("gitAvailable") is not None and "gitAvailable" not in inventory:
        inventory["gitAvailable"] = normalized["gitAvailable"]
    if normalized.get("sourceFilesVisited") and not inventory.get("sourceFilesVisited"):
        inventory["sourceFilesVisited"] = normalized["sourceFilesVisited"]
    if normalized.get("partialInventoryReasons") and not inventory.get("partialInventoryReasons"):
        inventory["partialInventoryReasons"] = normalized["partialInventoryReasons"]
    normalized["coverageInventory"] = inventory
    return normalize_browser_understanding_payload(normalized)


def _understanding_runtime_requirements(
    supplied: Any,
    existing: Any,
    target_environment: dict[str, Any] | None,
) -> list[Any]:
    source = supplied if isinstance(supplied, list) else existing
    requirements = list(source) if isinstance(source, list) else []
    if not target_environment:
        return requirements
    locator = str(target_environment.get("locator") or "")
    has_target = any(
        isinstance(item, dict)
        and str(item.get("name", "")).lower()
        in {"baseurl", "target", "targeturl"}
        for item in requirements
    )
    if locator and not has_target:
        requirements.append({"name": "baseUrl", "value": locator})
    return requirements


def _normalize_specification_content(project: Path, alias: str, content: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(content)
    normalized.setdefault("surface", normalized.get("targetSurface") or normalized.get("route"))
    normalized.setdefault("behavior", normalized.get("purpose") or normalized.get("description") or normalized.get("intent"))
    if "expectedOutcome" not in normalized and "expectedOutcomes" in normalized:
        normalized["expectedOutcome"] = normalized["expectedOutcomes"]
    if not (normalized.get("sourceInventoryItems") or normalized.get("customSourceReason")):
        candidate = _candidate_from_context(project, alias)
        if candidate and candidate.get("sourceInventoryItems"):
            normalized["sourceInventoryItems"] = candidate["sourceInventoryItems"]
        else:
            normalized["customSourceReason"] = "Custom use case selected by developer during workflow specification."
    return normalized


def _candidate_from_context(project: Path, alias: str) -> dict[str, Any] | None:
    for candidate in load_product_context(project).get("candidateUseCases", []):
        if isinstance(candidate, dict) and (candidate.get("alias") == alias or candidate.get("candidateAlias") == alias):
            return candidate
    return None


def _normalize_plan_content(alias: str, content: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(content)
    if "reusableSkills" not in normalized and "skills" in normalized:
        normalized["reusableSkills"] = normalized["skills"]
    if "reusableSkills" not in normalized and "supportingSkills" in normalized:
        skills = []
        if normalized.get("mainSkill"):
            skills.append(normalized["mainSkill"])
        skills.extend(normalized.get("supportingSkills") or [])
        normalized["reusableSkills"] = skills
    if "runtimeInputs" not in normalized:
        run_request = normalized.get("runRequest")
        if isinstance(run_request, dict):
            intent = run_request.get("intent") if isinstance(run_request.get("intent"), dict) else {}
            normalized["runtimeInputs"] = (
                run_request.get("runtimeInputs")
                or intent.get("runtimeInputs")
                or _runtime_inputs_from_parameters(run_request.get("parameters", {}))
            )
    normalized.setdefault("runtimeInputs", [])
    normalized.setdefault("runRequest", f".verifysignal/run-requests/{alias}.yaml")
    return normalized


def _normalize_implementation_content(alias: str, content: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_artifact_aliases(dict(content))
    artifacts_payload = normalized.get("artifacts")
    if isinstance(artifacts_payload, list):
        skills: list[dict[str, Any]] = []
        for artifact in artifacts_payload:
            if not isinstance(artifact, dict):
                continue
            kind = artifact.get("kind")
            path = str(artifact.get("path", ""))
            if kind == "run-request" or path.endswith(".yaml"):
                normalized.setdefault("runRequest", artifact)
            elif kind == "skill" or path.endswith(".browser.md"):
                skills.append(artifact)
        if skills and "skills" not in normalized:
            normalized["skills"] = skills
    normalized.setdefault("runRequest", {"path": f".verifysignal/run-requests/{alias}.yaml"})
    normalized.setdefault("skills", [])
    return normalized


def _alias(value: str) -> str:
    if not value:
        raise ValueError("Stage requires alias.")
    return layout.ensure_path_safe_alias(value)


def _require_fields(data: dict[str, Any], fields: list[str], *, stage: str | None = None) -> None:
    missing = []
    for field in fields:
        value = data.get(field)
        if field not in data or value is None or value == "":
            missing.append(field)
    if missing:
        if stage:
            raise missing_required_field_error(stage, missing[0])
        raise ValueError(f"Payload missing required fields: {', '.join(missing)}.")


def _gate_intent_requiredness_blockers(project: Path, alias: str, content: dict[str, Any]) -> list[ReadinessBlocker]:
    try:
        existing = load_artifact_plan(project, alias)
    except Exception:
        return []
    previous = {
        str(item.get("id") or item.get("gateId")): bool(item.get("required", True))
        for item in existing.validationGates
        if isinstance(item, dict) and (item.get("id") or item.get("gateId"))
    }
    if not previous:
        return []
    confirmed = {
        str(item.get("gateId") or item.get("id"))
        for item in content.get("gateIntentChanges", [])
        if isinstance(item, dict) and (item.get("gateId") or item.get("id")) and item.get("reason")
    }
    blockers: list[ReadinessBlocker] = []
    for item in content.get("validationGates", []) if isinstance(content.get("validationGates"), list) else []:
        if not isinstance(item, dict):
            continue
        gate_id = str(item.get("id") or item.get("gateId") or "")
        if not gate_id or gate_id not in previous:
            continue
        required = bool(item.get("required", True))
        if previous[gate_id] != required and gate_id not in confirmed:
            blockers.append(
                ReadinessBlocker(
                    code="gate-intent.requiredness-change-unconfirmed",
                    message=f"Gate '{gate_id}' changes requiredness. Record a clarify/plan gateIntentChanges entry with a non-secret reason before persisting.",
                    recoveryCommand=f"verifysignal workflow persist plan --alias {alias} --payload <payload-with-gateIntentChanges.json> --json",
                    documentationRef="stagePayloadContracts.plan.optionalFields.gateIntentChanges",
                )
            )
    return blockers


def _artifact_path(value: Any, *, default: str | None = None) -> str:
    if isinstance(value, dict):
        return str(value.get("path") or default or value.get("name") or "")
    return str(value or default or "")


def _skill_path(value: Any) -> str:
    path = _artifact_path(value)
    name = path
    if isinstance(value, dict):
        name = str(value.get("name") or value.get("id") or path)
    if not path or "/" not in path:
        safe = layout.ensure_path_safe_alias(name.replace("skill.", "").replace("_", "-").lower())
        path = f".verifysignal/skills/{safe}.browser.md"
    if not path.startswith(f"{layout.WORKSPACE_DIR}/{layout.SKILLS_DIR}/") or not path.endswith(".browser.md"):
        raise ValueError("Generated browser skills must use .verifysignal/skills/<name>.browser.md.")
    return path


def _skill_reference(value: Any) -> ArtifactReference:
    path = _skill_path(value)
    name = Path(path).stem.removesuffix(".browser")
    skill_id = f"skill.{name}"
    version = "1.0.0"
    if isinstance(value, dict):
        intent = value.get("intent") if isinstance(value.get("intent"), dict) else {}
        skill_id = str(value.get("id") or intent.get("id") or skill_id)
        version = str(value.get("version") or intent.get("version") or version)
    return ArtifactReference(path=path, kind="skill", generated=True, id=skill_id, version=version)


def _runtime_input(value: Any) -> RuntimeInputRequirement:
    if isinstance(value, dict):
        return RuntimeInputRequirement.from_dict(value)
    return RuntimeInputRequirement(name=str(value))


def _question_from_dict(data: dict[str, Any]) -> AuthoringQuestion:
    question = AuthoringQuestion.from_dict(data)
    if _is_environment_dependent(data) and question.status != "answered":
        question.status = data.get("status", "pending")
        question.affects = question.affects or str(data.get("affects") or "runtime")
    return question


def _apply_write_flow_fields(project: Path, record: Any, content: dict[str, Any]) -> None:
    if isinstance(content.get("sideEffects"), dict):
        from verifysignal_spec.workflows.write_safety import normalize_side_effect_policy

        side_effects, compatibility_findings = normalize_side_effect_policy(dict(content["sideEffects"]))
        blocking = [item for item in compatibility_findings if item.get("severity") == "blocking"]
        if blocking:
            first = blocking[0]
            raise ValueError(f"Conflicting side-effect policy at {first.get('path')}: {first.get('message')}")
        record.sideEffects = side_effects
    if isinstance(content.get("resourceIdentity"), dict):
        record.resourceIdentity = dict(content["resourceIdentity"])
    if isinstance(content.get("runtimeOutputs"), list):
        record.runtimeOutputs = [item for item in content["runtimeOutputs"] if isinstance(item, dict)]
    if isinstance(content.get("rerunPolicy"), dict):
        record.rerunPolicy = dict(content["rerunPolicy"])
    if isinstance(content.get("writeFlowSummary"), dict):
        record.writeFlowSummary = dict(content["writeFlowSummary"])
    lifecycle = content.get("sideEffectLifecycle")
    if isinstance(lifecycle, dict):
        record.sideEffectLifecycle = dict(lifecycle)
    hints = content.get("credentialReadinessHints")
    if isinstance(hints, list):
        for item in hints:
            if isinstance(item, dict):
                hint = CredentialReadinessHint.from_dict(item)
                findings = validate_credential_readiness_hint(hint)
                if findings:
                    first = findings[0]
                    raise ValueError(f"Invalid credential readiness hint at {first.get('path')}: {first.get('message')}")
                save_credential_readiness_hint(project, hint)


def _require_resource_identity_for_new_write(record: Any) -> None:
    side_effects = record.sideEffects if isinstance(record.sideEffects, dict) else {}
    side_effect_class = str(side_effects.get("class") or side_effects.get("sideEffectClass") or "none")
    if side_effect_class not in {"write", "external-notification"}:
        return
    if isinstance(getattr(record, "resourceIdentity", None), dict) and record.resourceIdentity:
        return
    raise ValueError(
        "Write and external-notification implementations require explicit resourceIdentity "
        "(resourceType, identityStrategy, identityInput or postCommitBinding, collisionPolicy, targetScope, confidence)."
    )


def _infer_resource_identity_if_possible(record: Any) -> None:
    if isinstance(getattr(record, "resourceIdentity", None), dict) and record.resourceIdentity:
        return
    side_effects = record.sideEffects if isinstance(record.sideEffects, dict) else {}
    side_effect_class = str(side_effects.get("class") or side_effects.get("sideEffectClass") or "none")
    if side_effect_class not in {"write", "external-notification"}:
        return
    candidates = [
        item
        for item in getattr(record, "runtimeInputs", [])
        if getattr(item, "source", "") == "generated" and bool(getattr(item, "refreshOnRerunAfterCommit", False))
    ]
    if len(candidates) != 1:
        return
    identity_input = candidates[0].name
    record.resourceIdentity = {
        "resourceType": _resource_type_from_alias(str(getattr(record, "alias", "resource"))),
        "identityStrategy": "generated-input",
        "identityInput": identity_input,
        "collisionPolicy": "avoid",
        "targetScope": _target_scope_from_runtime_inputs(getattr(record, "runtimeInputs", [])),
        "confidence": "high",
    }


def _resource_type_from_alias(alias: str) -> str:
    tokens = [item for item in re.split(r"[-_.]+", alias) if item]
    if len(tokens) > 1 and tokens[0] in {"add", "create", "publish", "send", "invite"}:
        tokens = tokens[1:]
    return "-".join(tokens) or "resource"


def _target_scope_from_runtime_inputs(runtime_inputs: list[Any]) -> str | None:
    for item in runtime_inputs:
        if getattr(item, "name", "") == "baseUrl" and getattr(item, "value", None):
            return str(item.value)
    return None


def _apply_answer(
    questions: list[AuthoringQuestion],
    answer: dict[str, Any],
) -> dict[str, str] | None:
    question_id = str(answer.get("questionId") or answer.get("id") or "")
    for question in questions:
        if question.id == question_id:
            if question.id == "browser-target-environment":
                source = str(answer.get("confirmationSource") or "")
                locator = _target_locator_from_text(
                    answer.get("answerSummary")
                    or answer.get("summary")
                    or answer.get("value")
                )
                if source not in {"direct-user", "explicit-command"} or not locator:
                    question.status = "pending"
                    return None
                question.status = "answered"
                question.answerSummary = locator
                question.confirmationSource = source  # type: ignore[assignment]
                return {"locator": locator, "source": source}
            question.status = "answered"
            question.answerSummary = str(answer.get("answerSummary") or answer.get("summary") or "")
            return None
    return None


TARGET_URL_RE = re.compile(r"https?://[^\s,;\"')]+", re.I)


def _is_browser_use_case(content: dict[str, Any]) -> bool:
    surface = str(content.get("surface") or content.get("targetSurface") or "").lower()
    target = str(content.get("target") or "").lower()
    return surface.startswith("/") or "browser" in surface or "browser" in target or bool(surface)


def _extract_target_environment(content: dict[str, Any], *, source_stage: str) -> dict[str, str] | None:
    candidates: list[Any] = [
        content.get("baseUrl"),
        content.get("targetUrl"),
        content.get("url"),
        content.get("stagingUrl"),
        content.get("environmentUrl"),
    ]
    target_environment = content.get("targetEnvironment")
    suggestion_source: str | None = None
    if isinstance(target_environment, dict):
        suggestion_source = str(
            target_environment.get("source")
            or target_environment.get("suggestionSource")
            or ""
        ) or None
        candidates.extend(
            [
                target_environment.get("locator"),
                target_environment.get("url"),
                target_environment.get("value"),
                target_environment.get("reference"),
            ]
        )
    elif target_environment:
        candidates.append(target_environment)
    for item in content.get("runtimeInputs", []) if isinstance(content.get("runtimeInputs"), list) else []:
        if isinstance(item, dict) and str(item.get("name", "")).lower() in {"baseurl", "targeturl", "url"}:
            candidates.extend([item.get("value"), item.get("default")])
    assumptions = content.get("runtimeAssumptions", [])
    if isinstance(assumptions, str):
        candidates.append(assumptions)
    elif isinstance(assumptions, list):
        candidates.extend(assumptions)
    for candidate in candidates:
        value = _target_locator_from_text(candidate)
        if value:
            result = {"locator": value, "sourceStage": source_stage}
            if suggestion_source:
                result["suggestionSource"] = suggestion_source
            return result
    return None


def _target_locator_from_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    match = TARGET_URL_RE.search(text)
    if match:
        return match.group(0).rstrip(".")
    if text.startswith("${") or text.startswith("<"):
        return text
    if text and any(token in text.lower() for token in ["staging", "local", "environment", "target"]):
        return text
    return None


def _ensure_browser_target_question(
    record: Any,
    *,
    locator: str | None = None,
    suggestion_source: str | None = None,
) -> None:
    existing = next(
        (
            question
            for question in record.authoringQuestions
            if question.id == "browser-target-environment"
        ),
        None,
    )
    if existing:
        if locator:
            existing.suggestedAnswer = {"baseUrl": locator}
            existing.suggestionSource = suggestion_source
        existing.requiresConfirmation = True
        if existing.confirmationSource is None:
            existing.status = "pending"
        return
    record.authoringQuestions.append(
        AuthoringQuestion(
            id="browser-target-environment",
            prompt="Which target application environment should this browser validation run against?",
            reason="Browser validation requires a resolved target environment before executable planning.",
            status="pending",
            affects="runtimeInputs.baseUrl",
            suggestedAnswer={"baseUrl": locator} if locator else None,
            suggestionSource=suggestion_source,
            requiresConfirmation=True,
        )
    )


def _resolve_browser_target_questions(record: Any, locator: str) -> None:
    for question in record.authoringQuestions:
        if question.id == "browser-target-environment":
            question.status = "answered"
            question.answerSummary = locator


def _upsert_stage_handoff_decision(record: Any, locator: str, *, source_stage: str) -> None:
    workflow = dict(record.workflow or {})
    decisions = [item for item in workflow.get("stageHandoffDecisions", []) if isinstance(item, dict)]
    decision = {
        "key": "browserTargetEnvironment",
        "valueSummary": locator,
        "sourceStage": source_stage,
        "appliesTo": record.alias,
        "status": "active",
    }
    updated = False
    for index, item in enumerate(decisions):
        if item.get("key") == "browserTargetEnvironment" and item.get("status", "active") == "active":
            decisions[index] = decision
            updated = True
            break
    if not updated:
        decisions.append(decision)
    workflow["stageHandoffDecisions"] = decisions
    record.workflow = workflow


def _target_from_questions(questions: list[AuthoringQuestion]) -> str | None:
    for question in questions:
        if question.status != "answered":
            continue
        text = f"{question.affects or ''} {question.answerSummary or ''}"
        if any(term in text.lower() for term in ["baseurl", "target", "environment", "runtime"]):
            locator = _target_locator_from_text(text)
            if locator:
                return locator
    return None


def _apply_skill_boundary_composition(
    project: Path,
    alias: str,
    content: dict[str, Any],
    *,
    core_contract: dict[str, Any] | None,
) -> dict[str, Any]:
    capability = multi_skill_capability(core_contract)
    if capability.supported:
        return content
    try:
        plan = load_artifact_plan(project, alias)
    except Exception:
        plan = None
    composition = content.get("skillComposition") if isinstance(content.get("skillComposition"), dict) else None
    if not composition and plan and isinstance(plan.skillComposition, dict):
        composition = plan.skillComposition
    if not isinstance(composition, dict):
        return content
    if str(composition.get("mode") or "") != "inline-into-main":
        return content
    skills = [item for item in content.get("skills", []) if isinstance(item, dict)]
    main_path = str(composition.get("mainSkillPath") or (plan.mainSkill if plan else ""))
    source_paths = [str(item) for item in composition.get("sourceSkillPaths", [])]
    if not source_paths and plan:
        source_paths = list(plan.sourceOnlySkills or plan.supportingSkills)
    main = next((item for item in skills if _artifact_path(item) == main_path), None)
    if main is None:
        return content
    main_browser = _browser_from_payload(main, credential_refs=_credential_refs_from_payload(content), core_contract=core_contract)
    source_browsers = [
        _browser_from_payload(item, credential_refs=_credential_refs_from_payload(content), core_contract=core_contract)
        for item in skills
        if _artifact_path(item) in set(source_paths)
    ]
    if not source_browsers:
        return content
    composed = _compose_browser(main_browser, source_browsers)
    updated_skills = []
    for item in skills:
        updated = dict(item)
        if _artifact_path(item) == main_path:
            updated["browser"] = composed
        updated_skills.append(updated)
    updated_content = dict(content)
    updated_content["skills"] = updated_skills
    updated_content["skillComposition"] = {
        **composition,
        "status": "ready",
        "mode": "inline-into-main",
    }
    return updated_content


def _compose_browser(main_browser: dict[str, Any], source_browsers: list[dict[str, Any]]) -> dict[str, Any]:
    targets: dict[str, Any] = {}
    steps: list[Any] = []
    assertions: list[Any] = []
    for browser in source_browsers:
        targets.update(browser.get("targets") if isinstance(browser.get("targets"), dict) else {})
        steps.extend(item for item in browser.get("steps", []) if isinstance(item, dict))
        assertions.extend(item for item in browser.get("assertions", []) if isinstance(item, dict))
    targets.update(main_browser.get("targets") if isinstance(main_browser.get("targets"), dict) else {})
    main_steps = [item for item in main_browser.get("steps", []) if isinstance(item, dict)]
    main_assertions = [item for item in main_browser.get("assertions", []) if isinstance(item, dict)]
    existing_step_ids = {str(item.get("id")) for item in main_steps}
    source_steps = [item for item in steps if str(item.get("id")) not in existing_step_ids]
    existing_assertion_ids = {str(item.get("id")) for item in main_assertions}
    source_assertions = [item for item in assertions if str(item.get("id")) not in existing_assertion_ids]
    return {
        **{key: value for key, value in main_browser.items() if key not in {"targets", "steps", "assertions"}},
        "targets": targets,
        "steps": [*source_steps, *main_steps],
        "assertions": [*source_assertions, *main_assertions],
    }


def _stage_handoff_target(record: Any) -> str | None:
    workflow = record.workflow if isinstance(record.workflow, dict) else {}
    for decision in workflow.get("stageHandoffDecisions", []):
        if not isinstance(decision, dict):
            continue
        if decision.get("key") == "browserTargetEnvironment" and decision.get("status", "active") == "active":
            value = str(decision.get("valueSummary") or "").strip()
            if value:
                return value
    return None


def _merge_resolved_target_runtime_input(runtime_inputs: Any, locator: str | None) -> list[dict[str, Any]]:
    inputs: list[dict[str, Any]] = []
    if isinstance(runtime_inputs, list):
        for item in runtime_inputs:
            if isinstance(item, dict):
                inputs.append(dict(item))
            elif item:
                inputs.append({"name": str(item), "kind": "parameter", "required": True})
    if not locator:
        return inputs
    for item in inputs:
        if str(item.get("name", "")).lower() == "baseurl":
            if not item.get("value") and not item.get("default"):
                item["value"] = locator
                item["source"] = "default"
            return inputs
    inputs.append(
        {
            "name": "baseUrl",
            "kind": "parameter",
            "required": True,
            "description": "Resolved browser target environment.",
            "source": "default",
            "value": locator,
        }
    )
    return inputs


def _is_environment_dependent(data: dict[str, Any]) -> bool:
    text = " ".join(str(data.get(key, "")) for key in ["prompt", "reason", "affects", "category"]).lower()
    return any(area.lower() in text for area in BLOCKING_CLARIFICATION_AREAS) or bool(data.get("environmentDependent"))


def _artifact_content(value: Any) -> str | None:
    if isinstance(value, dict):
        content = value.get("content")
        return str(content) if content is not None else None
    return None


def _ensure_core_run_request_document(
    content: str | None,
    record: Any,
    payload: dict[str, Any],
    *,
    core_contract: dict[str, Any] | None = None,
) -> str:
    expected_schema = _artifact_schema_from_core_contract(core_contract, "runRequest", "qa-run-request/v1")
    schema_version = _schema_version_from_content(content)
    if schema_version and schema_version != expected_schema:
        raise ValueError(f"Legacy executable artifact schemaVersion {schema_version!r}; expected {expected_schema!r} from the Core public contract.")
    if content and _looks_like_core_run_request(content, expected_schema):
        return _ensure_run_request_skill_order(content, record, core_contract=core_contract)
    return artifacts.render_run_request(record, parameters=_parameters_from_payload(payload), schema_version=expected_schema, core_contract=core_contract)


def _ensure_core_skill_document(
    content: str | None,
    record: Any,
    skill: ArtifactReference,
    payload: Any,
    *,
    credential_refs: dict[str, Any] | None = None,
    core_contract: dict[str, Any] | None = None,
) -> str:
    expected_schema = _artifact_schema_from_core_contract(core_contract, "skill", "qa-skill/v1")
    schema_version = _schema_version_from_content(content)
    if schema_version and schema_version != expected_schema:
        raise ValueError(f"Legacy executable artifact schemaVersion {schema_version!r}; expected {expected_schema!r} from the Core public contract.")
    if content and _looks_like_core_skill(content, expected_schema):
        return content
    return artifacts.render_skill(
        record,
        skill,
        draft_notes=_skill_notes_from_payload(content, payload),
        browser=_browser_from_payload(payload, credential_refs=credential_refs, core_contract=core_contract),
        schema_version=expected_schema,
    )


def _artifact_schema_from_core_contract(core_contract: dict[str, Any] | None, section: str, default: str) -> str:
    if isinstance(core_contract, dict):
        metadata = core_contract.get("sections", {}).get(section, {})
        if isinstance(metadata, dict):
            artifact_schema = metadata.get("artifactSchemaVersion")
            if isinstance(artifact_schema, str) and artifact_schema:
                return artifact_schema
            legacy_schema = metadata.get("schemaVersion")
            if isinstance(legacy_schema, str) and legacy_schema.startswith("qa-"):
                return legacy_schema
    return default


def _schema_version_from_content(content: str | None) -> str | None:
    if not content:
        return None
    try:
        import yaml  # type: ignore

        parsed = yaml.safe_load(content) or {}
    except Exception:
        return None
    if isinstance(parsed, dict) and parsed.get("schemaVersion"):
        return str(parsed["schemaVersion"])
    return None


def _looks_like_core_run_request(content: str, schema_version: str = "qa-run-request/v1") -> bool:
    schema_tokens = [f"schemaVersion: {schema_version}", f'"schemaVersion": "{schema_version}"', f'"schemaVersion":"{schema_version}"']
    return any(token in content for token in schema_tokens) and all(token in content for token in ["request", "id", "name", "target", "validationScope", "skills"])


def _looks_like_core_skill(content: str, schema_version: str = "qa-skill/v1") -> bool:
    schema_tokens = [f"schemaVersion: {schema_version}", f'"schemaVersion": "{schema_version}"', f'"schemaVersion":"{schema_version}"']
    return any(token in content for token in schema_tokens) and all(token in content for token in ["skill:", "kind: browser", "browser:"])


def _ensure_run_request_skill_order(content: str, record: Any, *, core_contract: dict[str, Any] | None = None) -> str:
    try:
        import yaml  # type: ignore

        parsed = yaml.safe_load(content) or {}
    except Exception:
        return content
    if not isinstance(parsed, dict):
        return content
    decision = resolve_execution_boundary(record, core_contract=core_contract, run_request=parsed)
    parsed["skills"] = [{"id": skill.id or f"skill.{record.alias}", "version": skill.version or "1.0.0"} for skill in decision.executableSkills]
    if record.credentialRefs:
        parsed["credentialRefs"] = record.credentialRefs
    if record.sessionRef:
        parsed["sessionRef"] = record.sessionRef
    try:
        import json

        return json.dumps(parsed, indent=2) + "\n"
    except Exception:
        return content


def _parameters_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    run_request = payload.get("runRequest") if isinstance(payload.get("runRequest"), dict) else {}
    run_request_intent = run_request.get("intent") if isinstance(run_request.get("intent"), dict) else {}
    parameters = run_request.get("parameters") if isinstance(run_request, dict) else {}
    if isinstance(parameters, dict) and parameters:
        return dict(parameters)
    intent_parameters = run_request_intent.get("parameters")
    if isinstance(intent_parameters, dict) and intent_parameters:
        return dict(intent_parameters)
    runtime_inputs = payload.get("runtimeInputs")
    if not runtime_inputs and isinstance(run_request, dict):
        runtime_inputs = run_request.get("runtimeInputs") or run_request_intent.get("runtimeInputs")
    return {
        item["name"]: item.get("value", item.get("default", ""))
        for item in runtime_inputs or []
        if isinstance(item, dict) and item.get("name") and item.get("kind") != "credential" and not item.get("credentialGroup")
    }


def _runtime_inputs_from_run_request_payload(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    runtime_inputs = payload.get("runtimeInputs")
    if isinstance(runtime_inputs, list):
        return [item for item in runtime_inputs if isinstance(item, dict)]
    intent = payload.get("intent")
    if isinstance(intent, dict) and isinstance(intent.get("runtimeInputs"), list):
        return [item for item in intent["runtimeInputs"] if isinstance(item, dict)]
    content = payload.get("content")
    if not isinstance(content, str):
        return []
    try:
        import yaml  # type: ignore

        parsed = yaml.safe_load(content) or {}
    except Exception:
        return []
    runtime_inputs = parsed.get("runtimeInputs") if isinstance(parsed, dict) else None
    if isinstance(runtime_inputs, list):
        return [item for item in runtime_inputs if isinstance(item, dict)]
    parameters = parsed.get("parameters") if isinstance(parsed, dict) else None
    return _runtime_inputs_from_parameters(parameters)


def _planned_runtime_inputs(project: Path, alias: str) -> list[dict[str, Any]]:
    try:
        return load_artifact_plan(project, alias).runtimeInputs
    except Exception:
        return []


def _runtime_inputs_from_parameters(parameters: Any) -> list[dict[str, Any]]:
    if not isinstance(parameters, dict):
        return []
    return [{"name": str(name), "value": value, "source": "default", "required": True} for name, value in parameters.items()]


def _credential_refs_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    run_request = payload.get("runRequest") if isinstance(payload.get("runRequest"), dict) else {}
    candidates: list[Any] = [
        payload.get("credentialRefs"),
        run_request.get("credentialRefs"),
    ]
    intent = run_request.get("intent") if isinstance(run_request.get("intent"), dict) else {}
    candidates.append(intent.get("credentialRefs"))
    content = _artifact_content(run_request)
    if content:
        try:
            import yaml  # type: ignore

            parsed = yaml.safe_load(content) or {}
        except Exception:
            parsed = {}
        if isinstance(parsed, dict):
            candidates.append(parsed.get("credentialRefs"))
    for candidate in candidates:
        refs = _normalize_credential_refs(candidate)
        if refs:
            return refs
    return {}


def _normalize_credential_refs(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    refs: dict[str, Any] = {}
    for group, config in value.items():
        group_name = str(group).strip()
        if not group_name or not isinstance(config, dict):
            continue
        keys = config.get("keys")
        if not isinstance(keys, dict):
            continue
        normalized_keys = {str(field).strip(): str(env_name).strip() for field, env_name in keys.items() if str(field).strip() and str(env_name).strip()}
        if not normalized_keys:
            continue
        refs[group_name] = {
            "source": str(config.get("source") or "environment"),
            "keys": normalized_keys,
        }
    return refs


def _session_ref_from_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    run_request = payload.get("runRequest") if isinstance(payload.get("runRequest"), dict) else {}
    intent = run_request.get("intent") if isinstance(run_request.get("intent"), dict) else {}
    candidates: list[Any] = [payload.get("sessionRef"), run_request.get("sessionRef"), intent.get("sessionRef")]
    content = _artifact_content(run_request)
    if content:
        try:
            import yaml  # type: ignore

            parsed = yaml.safe_load(content) or {}
        except Exception:
            parsed = {}
        if isinstance(parsed, dict):
            candidates.append(parsed.get("sessionRef"))
    for candidate in candidates:
        normalized = _normalize_session_ref(candidate)
        if normalized:
            return normalized
    return None


def _normalize_session_ref(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    source = str(value.get("source") or "environment").strip()
    key = str(value.get("key") or "").strip()
    if not key:
        return None
    return {"source": source, "key": key}


def _credential_groups_from_refs(credential_refs: dict[str, Any]) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    for group, config in credential_refs.items():
        keys = config.get("keys") if isinstance(config, dict) else {}
        groups.append(
            {
                "name": str(group),
                "source": str(config.get("source") or "environment") if isinstance(config, dict) else "environment",
                "fields": sorted(str(field) for field in keys) if isinstance(keys, dict) else [],
            }
        )
    return groups


def _filter_runtime_credential_inputs(runtime_inputs: list[dict[str, Any]], credential_refs: dict[str, Any]) -> list[dict[str, Any]]:
    if not credential_refs:
        return runtime_inputs
    filtered: list[dict[str, Any]] = []
    declared_env_names = {
        str(env_name)
        for config in credential_refs.values()
        if isinstance(config, dict)
        for env_name in (config.get("keys") or {}).values()
    }
    for item in runtime_inputs:
        if not isinstance(item, dict):
            continue
        if item.get("kind") == "credential" or item.get("credentialGroup"):
            continue
        if item.get("envVar") and str(item.get("envVar")) in declared_env_names:
            continue
        filtered.append(item)
    return filtered


def _profiles_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    profiles = payload.get("profiles")
    if isinstance(profiles, list):
        return [item for item in profiles if isinstance(item, dict)]
    run_request = payload.get("runRequest") if isinstance(payload.get("runRequest"), dict) else {}
    profiles = run_request.get("profiles")
    if isinstance(profiles, list):
        return [item for item in profiles if isinstance(item, dict)]
    intent = run_request.get("intent") if isinstance(run_request.get("intent"), dict) else {}
    profiles = intent.get("profiles")
    if isinstance(profiles, list):
        return [item for item in profiles if isinstance(item, dict)]
    return []


def _core_contract_for_browser_authoring(project: Path) -> dict[str, Any] | None:
    from verifysignal_spec.core.runtime_contract import (
        CoreRuntimeResolutionError,
        resolve_core_executable_contract,
    )

    configured_command = (
        get_core_command(project)
        or os.environ.get("VERIFYSIGNAL_CORE_CMD")
    )
    if not configured_command:
        from verifysignal_spec.runtime.cache import load_cache_entry
        from verifysignal_spec.runtime.distribution import normalize_platform

        platform = normalize_platform()
        api_base_url = get_entitlement_api_base_url(project)
        if (
            not platform
            or load_cache_entry(
                platform=platform,
                api_base_url=api_base_url,
            )
            is None
        ):
            # Preserve the established contract for source-only authoring
            # fixtures and workspaces that have not installed a Core yet.
            # Once a managed runtime exists, discovery below is mandatory.
            return None

    try:
        projection, _runtime = resolve_core_executable_contract(
            project,
            context="browser-authoring",
        )
    except CoreRuntimeResolutionError as exc:
        raise ValueError(f"Core executable contract unavailable for browser authoring validation: {exc}") from exc
    blockers = [item for item in projection.get("findings", []) if item.get("severity") == "blocking"]
    if blockers:
        message = blockers[0].get("message") or blockers[0].get("code") or "Core executable contract is incompatible."
        raise ValueError(f"Core executable contract unavailable for browser authoring validation: {message}")
    return projection


def _browser_from_payload(
    payload: Any,
    *,
    credential_refs: dict[str, Any] | None = None,
    core_contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    intent = payload.get("intent") if isinstance(payload.get("intent"), dict) else {}
    browser = payload.get("browser") if isinstance(payload.get("browser"), dict) else intent.get("browser")
    normalized = _normalize_browser_payload(browser if isinstance(browser, dict) else {})
    blockers = validate_browser_payload(normalized, credential_refs=credential_refs, core_contract=core_contract)
    if blockers:
        raise ValueError("Invalid executable browser skill intent: " + " ".join(blockers))
    if _has_detailed_skill_intent(payload) and not _has_executable_browser_intent(normalized, payload):
        raise ValueError(
            "Browser skill intent includes detailed validation instructions, but no executable browser.steps/assertions were provided. "
            "Provide Core browser actions under intent.browser.steps and final checks under intent.browser.assertions."
        )
    return normalized


def _skill_notes_from_payload(content: str | None, payload: Any) -> str | None:
    if content:
        return content
    if not isinstance(payload, dict):
        return None
    intent = payload.get("intent") if isinstance(payload.get("intent"), dict) else {}
    body = intent.get("body") or payload.get("body")
    if isinstance(body, str) and body.strip():
        return body
    steps = intent.get("steps") or payload.get("steps")
    if not isinstance(steps, list) or not steps:
        return None
    lines = ["## Execution Intent", ""]
    for index, step in enumerate(steps, start=1):
        if isinstance(step, dict):
            title = step.get("title") or step.get("id") or f"Step {index}"
            lines.extend([f"{index}. {title}", ""])
            instructions = step.get("instructions") or step.get("description")
            if instructions:
                lines.extend([str(instructions), ""])
            if step.get("gate"):
                lines.extend([f"Gate: {step['gate']}", ""])
        else:
            lines.extend([f"{index}. {step}", ""])
    success_gate = intent.get("successGate") or payload.get("successGate")
    if success_gate:
        lines.extend(["Success gate:", str(success_gate), ""])
    return "\n".join(lines).strip()


def _normalize_browser_payload(browser: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(browser)
    start_url = normalized.pop("startUrl", None)
    timeout_ms = normalized.pop("timeoutMs", None)
    steps = list(normalized.get("steps") or [])
    assertions = list(normalized.get("assertions") or [])
    if start_url and not steps:
        step: dict[str, Any] = {"id": "open", "action": "navigate", "value": start_url}
        if timeout_ms:
            step["timeoutMs"] = timeout_ms
        steps = [step]
    if steps or assertions or start_url:
        normalized["steps"] = steps
        normalized["assertions"] = assertions
    return normalized


def _has_detailed_skill_intent(payload: dict[str, Any]) -> bool:
    intent = payload.get("intent") if isinstance(payload.get("intent"), dict) else {}
    detailed = [
        intent.get("body"),
        intent.get("steps"),
        intent.get("successGate"),
        payload.get("body"),
        payload.get("steps"),
        payload.get("validationGates"),
    ]
    return any(bool(item) for item in detailed)


def _has_executable_browser_intent(browser: dict[str, Any], payload: dict[str, Any]) -> bool:
    steps = browser.get("steps") if isinstance(browser.get("steps"), list) else []
    assertions = browser.get("assertions") if isinstance(browser.get("assertions"), list) else []
    intent = payload.get("intent") if isinstance(payload.get("intent"), dict) else {}
    planned_steps = intent.get("steps") or payload.get("steps")
    planned_count = len(planned_steps) if isinstance(planned_steps, list) else 0
    executable_count = len(steps) + len(assertions)
    if planned_count:
        return executable_count >= planned_count and any(isinstance(step, dict) and step.get("action") for step in steps)
    return bool(assertions) or any(isinstance(step, dict) and step.get("action") and step.get("action") != "navigate" for step in steps)


def _write_payload_artifact(project: Path, rel_path: str, content: str | None, fallback) -> None:
    path = layout.project_relative_path(project, rel_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if content is None:
        content = fallback()
    path.write_text(content if content.endswith("\n") else content + "\n", encoding="utf-8")


def _artifact(project: Path, path: Path, kind: str) -> ManagedWorkspaceArtifact:
    return ManagedWorkspaceArtifact(path=project_relative(project, path), kind=kind)


def _blocked(
    stage: str,
    alias: str | None,
    *,
    code: str,
    message: str,
    invalid: bool = False,
    recovery_command: str | None = None,
    documentation_ref: str | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    return StagePersistenceResult(
        stage=stage,
        alias=alias,
        status="invalid" if invalid else "blocked",
        blockers=[ReadinessBlocker(code=code, message=message, recoveryCommand=recovery_command, documentationRef=documentation_ref)],
        warnings=warnings or [],
    ).to_dict()


def _inventory_warnings(status: str, *, partial_reasons: list[str] | None = None) -> list[str]:
    if status == "partial":
        reasons = f" Reasons: {'; '.join(partial_reasons)}." if partial_reasons else ""
        return [f"Partial inventory: candidate scenarios are not exhaustive.{reasons}"]
    if status == "stale":
        return ["Coverage inventory is stale; refresh affected areas before relying on candidates."]
    return []


def _recommended_follow_up_scope(status: str, current_scope: str) -> str | None:
    if status == "partial":
        return "continue"
    if status == "stale":
        return "changed" if current_scope != "all" else "all"
    return None


def _trivial_candidate_count(inventory: Any) -> int:
    from verifysignal_spec.workflows.first_run import evaluate_first_run_ideal_criteria
    from verifysignal_spec.workflows.models import FirstRunCandidate

    count = 0
    for candidate in inventory.candidateUseCases:
        if evaluate_first_run_ideal_criteria(FirstRunCandidate.from_candidate_use_case(candidate)).all_met():
            count += 1
    return count
