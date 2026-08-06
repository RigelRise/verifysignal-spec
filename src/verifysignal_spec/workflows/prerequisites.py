from __future__ import annotations

import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from verifysignal_spec.process import run_text
from verifysignal_spec.workspace import layout
from verifysignal_spec.workspace.product_context import (
    load_product_context,
    record_understanding_refresh_decision,
    update_understanding_stale_reasons,
)
from verifysignal_spec.workspace.repository import (
    calculate_run_confirmation_requirements,
    confirmation_requirement,
    load_readiness_snapshot,
    load_refresh_impact,
    load_registry,
    load_use_case,
    load_supersede_reviews,
    reconcile_active_confirmation,
    side_effect_class,
    snapshot_invalidation_reasons,
)
from verifysignal_spec.workspace.models import UnderstandingFreshnessState
from verifysignal_spec.workflows.run_preflight import (
    build_run_preflight,
    local_run_policy_blockers,
)

from .first_run import build_understanding_onboarding_preparation
from .models import (
    COMMAND_STAGES,
    WORKFLOW_CAPABILITY_SCHEMA,
    WORKFLOW_GUARDRAILS_CAPABILITY,
    WORKFLOW_PREREQUISITE_CHECK_SCHEMA,
    WORKFLOW_UNDERSTANDING_COMMIT_THRESHOLD,
    WORKFLOW_UNDERSTANDING_MAX_AGE_DAYS,
    native_invocation,
)
from .repository import load_workflow_run
from .transitions import managed_workflow_stage_decision


@dataclass(frozen=True, slots=True)
class StagePrerequisiteRule:
    stage: str
    requires_global_understanding: bool
    requires_alias: bool
    missing_next_stage: str | None = None


STAGE_PREREQUISITE_RULES: dict[str, StagePrerequisiteRule] = {
    "understand": StagePrerequisiteRule("understand", requires_global_understanding=False, requires_alias=False),
    "specify": StagePrerequisiteRule("specify", requires_global_understanding=True, requires_alias=False, missing_next_stage="understand"),
    "clarify": StagePrerequisiteRule("clarify", requires_global_understanding=True, requires_alias=True, missing_next_stage="specify"),
    "plan": StagePrerequisiteRule("plan", requires_global_understanding=True, requires_alias=True, missing_next_stage="specify"),
    "tasks": StagePrerequisiteRule("tasks", requires_global_understanding=True, requires_alias=True, missing_next_stage="plan"),
    "implement": StagePrerequisiteRule("implement", requires_global_understanding=True, requires_alias=True, missing_next_stage="tasks"),
    "validate": StagePrerequisiteRule("validate", requires_global_understanding=True, requires_alias=True, missing_next_stage="implement"),
    "run": StagePrerequisiteRule("run", requires_global_understanding=True, requires_alias=True, missing_next_stage="validate"),
    "repair": StagePrerequisiteRule("repair", requires_global_understanding=True, requires_alias=True, missing_next_stage="validate"),
    "list": StagePrerequisiteRule("list", requires_global_understanding=False, requires_alias=False),
}


def check_prerequisites(
    project: Path,
    stage: str,
    alias: str | None = None,
    refresh_decision: str | None = None,
) -> dict[str, Any]:
    if stage not in COMMAND_STAGES:
        supported = ", ".join(COMMAND_STAGES)
        raise ValueError(f"Unsupported workflow stage: {stage}. Supported stages: {supported}")
    if refresh_decision not in {None, "accepted", "declined"}:
        raise ValueError("Refresh decision must be accepted or declined.")
    rule = STAGE_PREREQUISITE_RULES[stage]
    project = project.resolve()
    resolved_alias = _resolve_alias(project, stage, alias, rule)
    if isinstance(resolved_alias, str) and stage in {"validate", "run"}:
        stage_decision = managed_workflow_stage_decision(
            project,
            resolved_alias,
            stage,
        )
        stage_blocker = stage_decision.get("blocker")
        if isinstance(stage_blocker, dict):
            return stage_position_blocked_check_result(
                stage,
                resolved_alias,
                stage_blocker,
            )
    authoritative_run_preflight: dict[str, Any] | None = None
    if stage == "run" and isinstance(resolved_alias, str):
        try:
            authoritative_run_preflight = _loaded_run_preflight(project, resolved_alias)
        except FileNotFoundError:
            authoritative_run_preflight = None
        if authoritative_run_preflight is not None:
            reconcile_active_confirmation(
                project,
                resolved_alias,
                authoritative_run_preflight.get("confirmation"),
            )

    stale_warnings: list[str] = []
    recorded_decision: dict[str, Any] | None = None
    understanding_payload: dict[str, Any] = {}
    rerun_decision_for_result: dict[str, Any] | None = None
    if rule.requires_global_understanding:
        understanding = _evaluate_understanding(project)
        understanding_payload = _understanding_payload(understanding.context)
        if understanding.status in {"missing", "blocked"}:
            preparation = build_understanding_onboarding_preparation(stage=stage) if understanding.status == "missing" and stage == "specify" else None
            return _result(
                stage,
                resolved_alias,
                understanding.status,
                can_proceed=False,
                missing_artifacts=understanding.missing_artifacts,
                warnings=understanding.warnings,
                recommended_action="auto-prepare-understanding" if preparation else ("run-understand" if understanding.status == "missing" else "upgrade-workspace"),
                next_command=native_invocation("understand"),
                onboardingPreparation=preparation,
                resumeCommand=preparation.get("resumeCommand") if preparation else None,
                stageCards=preparation.get("stageCards", []) if preparation else [],
                **understanding_payload,
            )
        if understanding.stale_reasons:
            update_understanding_stale_reasons(project, [item["code"] for item in understanding.stale_reasons])
            alias_scoped = stage in {"validate", "run", "repair"} and isinstance(resolved_alias, str)
            if alias_scoped and refresh_decision is None:
                alias_stale = _alias_scoped_stale_result(project, stage, resolved_alias, understanding, understanding_payload)
                if alias_stale is not None:
                    return alias_stale
            if refresh_decision == "accepted":
                recorded_decision = record_understanding_refresh_decision(
                    project, "accepted", understanding.stale_reasons, stage=stage
                )
                return _result(
                    stage,
                    resolved_alias,
                    "stale",
                    can_proceed=False,
                    stale_reasons=understanding.stale_reasons,
                    warnings=_stale_warnings(stage),
                    recommended_action="refresh-understanding",
                    next_command=native_invocation("understand"),
                    recorded_decision=recorded_decision,
                    **understanding_payload,
                )
            if refresh_decision == "declined":
                recorded_decision = record_understanding_refresh_decision(
                    project, "declined", understanding.stale_reasons, stage=stage
                )
                stale_warnings = _stale_declined_warnings(stage)
                if stage == "specify":
                    return _result(
                        stage,
                        resolved_alias,
                        "stale",
                        can_proceed=True,
                        stale_reasons=understanding.stale_reasons,
                        warnings=stale_warnings,
                        recommended_action="continue-with-warning",
                        next_command=native_invocation("specify"),
                        recorded_decision=recorded_decision,
                        **understanding_payload,
                    )
            else:
                return _result(
                    stage,
                    resolved_alias,
                    "stale",
                    can_proceed=True,
                    requires_confirmation=True,
                    stale_reasons=understanding.stale_reasons,
                    warnings=_stale_warnings(stage),
                    recommended_action="refresh-understanding",
                    next_command=native_invocation("understand"),
                    **understanding_payload,
                )
        else:
            update_understanding_stale_reasons(project, [])

    if isinstance(resolved_alias, dict):
        return _result(
            stage,
            None,
            "ambiguous",
            can_proceed=False,
            requires_confirmation=True,
            warnings=["Select a use case alias before running this stage."],
            recommended_action="choose-alias",
            next_command=native_invocation("list"),
            available_aliases=resolved_alias["availableAliases"],
            recorded_decision=recorded_decision,
            **understanding_payload,
        )

    target_confirmation = (
        _target_environment_confirmation_blocker(project, stage, resolved_alias)
        if isinstance(resolved_alias, str)
        else None
    )
    if target_confirmation:
        return _result(
            stage,
            resolved_alias,
            "blocked",
            can_proceed=False,
            requires_confirmation=True,
            warnings=[target_confirmation["message"]],
            recommended_action="confirm-target-environment",
            next_command=_native_next("clarify", resolved_alias),
            blockers=[target_confirmation],
            **understanding_payload,
        )

    missing = _missing_stage_artifacts(project, stage, resolved_alias)
    if missing:
        next_stage = missing[0]["nextStage"]
        return _result(
            stage,
            resolved_alias,
            "missing",
            can_proceed=False,
            missing_artifacts=[item["path"] for item in missing],
            warnings=stale_warnings,
            recommended_action=f"run-{next_stage}",
            next_command=_native_next(next_stage, resolved_alias),
            recorded_decision=recorded_decision,
            **understanding_payload,
        )

    if stage == "run" and isinstance(resolved_alias, str):
        preflight = authoritative_run_preflight or _loaded_run_preflight(project, resolved_alias)
        confirmation = preflight.get("confirmation")
        rerun_decision = preflight["rerunDecision"]
        if not preflight["canProceed"]:
            blocker = preflight["blockers"][0]
            code = str(blocker.get("code") or "")
            requires_rerun_confirmation = code == "runtime.rerun-confirmation-required"
            if requires_rerun_confirmation:
                recommended_action = "approve-rerun"
            elif code == "runtime.rerun-policy-blocked":
                recommended_action = "review-or-supersede-write-outcome"
            elif code == "runtime.confirmation-required":
                recommended_action = "confirm-risk"
            elif code == "runtime.protected-readiness-required":
                recommended_action = "run-validate"
            elif code == "runtime.side-effect-observation-review-required":
                recommended_action = "review-or-supersede-write-outcome"
            else:
                recommended_action = str(
                    preflight.get("recommendedAction") or "resolve-run-preflight"
                )
            return _result(
                stage,
                resolved_alias,
                "blocked",
                can_proceed=False,
                requires_confirmation=bool(preflight["requiresConfirmation"]),
                warnings=[str(blocker.get("message") or "")],
                recommended_action=recommended_action,
                next_command=str(preflight["nextAction"]),
                confirmation=confirmation,
                rerunDecision=rerun_decision,
                blockers=preflight["blockers"],
                **understanding_payload,
            )
        rerun_decision_for_result = rerun_decision

    return _result(
        stage,
        resolved_alias,
        "ready",
        can_proceed=True,
        warnings=stale_warnings,
        recommended_action="continue-with-warning" if stale_warnings else "continue",
        next_command=_native_next(stage, resolved_alias),
        recorded_decision=recorded_decision,
        rerunDecision=rerun_decision_for_result,
        **understanding_payload,
    )


def _loaded_run_preflight(project: Path, alias: str) -> dict[str, Any]:
    record = load_use_case(project, alias)
    readiness = load_readiness_snapshot(project, alias)
    reviews = load_supersede_reviews(project, alias)
    missing = [item["path"] for item in _missing_stage_artifacts(project, "run", alias)]
    return build_run_preflight(
        {
            "targetBlocker": _target_environment_confirmation_blocker(project, "run", alias),
            "missingArtifacts": missing,
            "policyBlockers": local_run_policy_blockers(
                record,
                supersede_reviews=reviews,
            ),
            "confirmationRequirements": calculate_run_confirmation_requirements(project, record),
            "readinessInvalidationReasons": (
                snapshot_invalidation_reasons(project, record, readiness)
                if readiness is not None
                else []
            ),
        },
        record,
        readiness,
        {},
        reviews,
    )


def stage_position_blocked_check_result(
    stage: str,
    alias: str,
    blocker: dict[str, Any],
) -> dict[str, Any]:
    return _result(
        stage,
        alias,
        "blocked",
        can_proceed=False,
        recommended_action="resume-current-stage",
        next_command=str(blocker["recoveryCommand"]),
        blockers=[blocker],
    )


def _alias_scoped_stale_result(
    project: Path,
    stage: str,
    alias: str,
    understanding: "UnderstandingEvaluation",
    understanding_payload: dict[str, Any],
) -> dict[str, Any] | None:
    try:
        record = load_use_case(project, alias)
    except FileNotFoundError:
        return None
    impact = load_refresh_impact(project, alias)
    impact_status = impact.status if impact else "unknown"
    side_effect = side_effect_class(record)
    freshness = UnderstandingFreshnessState.from_context(
        stale=True,
        workflow_context=stage,
        use_case_impact=impact_status,
        side_effect_class=side_effect,
        reasons=[item.get("message", item.get("code", "")) for item in understanding.stale_reasons],
    )
    requires_confirmation = freshness.policy == "requires-confirmation"
    confirmation = None
    if requires_confirmation:
        confirmation = confirmation_requirement(
            alias=alias,
            risk_class=side_effect,
            scope="unknown-refresh-impact",
            reason=(impact.reason if impact else "Product understanding is stale and impact on this write-capable use case is unknown."),
            recommended_action="Run validation or refresh understanding before executing, or explicitly confirm the write risk.",
        )
    can_proceed = not (stage == "run" and freshness.policy == "block")
    recommended_action = {
        "confirm": "confirm-risk",
        "validate": "run-validate",
        "continue": "continue-with-warning",
        "refresh-understanding": "refresh-understanding",
    }.get(freshness.recommendedAction, freshness.recommendedAction)
    next_command = _native_next("validate" if stage == "run" and freshness.recommendedAction == "validate" else stage, alias)
    return _result(
        stage,
        alias,
        "stale",
        can_proceed=can_proceed,
        requires_confirmation=requires_confirmation,
        stale_reasons=understanding.stale_reasons,
        warnings=_alias_scoped_stale_warnings(stage, alias, impact_status),
        recommended_action=recommended_action,
        next_command=next_command,
        refreshImpact={
            "status": impact_status,
            "reason": impact.reason if impact else "Impact has not been determined.",
            "recommendedAction": impact.recommendedAction if impact else freshness.recommendedAction,
        },
        understandingFreshness=freshness.to_dict(),
        confirmation=confirmation.to_dict() if confirmation else None,
        **understanding_payload,
    )


@dataclass(slots=True)
class UnderstandingEvaluation:
    status: str
    context: dict[str, Any]
    missing_artifacts: list[str]
    stale_reasons: list[dict[str, str]]
    warnings: list[str]


def _evaluate_understanding(project: Path) -> UnderstandingEvaluation:
    missing: list[str] = []
    if not layout.workflow_global_understanding_path(project).exists():
        missing.append(f"{layout.WORKSPACE_DIR}/{layout.WORKFLOWS_DIR}/{layout.WORKFLOW_GLOBAL_UNDERSTANDING}")
    if not layout.product_context_path(project).exists():
        missing.append(f"{layout.WORKSPACE_DIR}/{layout.PRODUCT_CONTEXT_FILE}")
    if missing:
        return UnderstandingEvaluation("missing", {}, missing, [], ["Product understanding is required before this stage."])

    context = load_product_context(project)
    schema = context.get("schemaVersion")
    if schema and schema != "verifysignal-spec-product-context/v1":
        return UnderstandingEvaluation(
            "blocked",
            context,
            [],
            [],
            [f"Unsupported product context schema: {schema}. Reinitialize or upgrade the workspace."],
        )

    metadata = context.get("understanding")
    if not isinstance(metadata, dict):
        return UnderstandingEvaluation("missing", context, ["understanding"], [], ["Product understanding metadata is missing."])
    mode = str(metadata.get("mode") or context.get("understandingMode") or "repository")
    generated_at = metadata.get("generatedAt")
    if not generated_at:
        return UnderstandingEvaluation(
            "missing",
            context,
            ["understanding.generatedAt"],
            [],
            ["Product understanding metadata is incomplete."],
        )
    generated = _parse_iso_datetime(str(generated_at))
    if generated is None:
        return UnderstandingEvaluation(
            "missing",
            context,
            ["understanding.generatedAt"],
            [],
            ["Product understanding generatedAt is invalid."],
        )
    if mode in {"repository", "hybrid"} and metadata.get("gitAvailable") and not metadata.get("generatedGitHash"):
        return UnderstandingEvaluation(
            "missing",
            context,
            ["understanding.generatedGitHash"],
            [],
            ["Product understanding Git metadata is incomplete."],
        )

    stale_reasons: list[dict[str, str]] = []
    age = datetime.now(UTC) - generated
    if age >= timedelta(days=WORKFLOW_UNDERSTANDING_MAX_AGE_DAYS):
        stale_reasons.append(
            {
                "code": "age",
                "message": f"Product understanding is at least {WORKFLOW_UNDERSTANDING_MAX_AGE_DAYS} days old.",
            }
        )
    current_hash = current_git_hash(project) if mode in {"repository", "hybrid"} else None
    generated_hash = metadata.get("generatedGitHash")
    if current_hash and generated_hash:
        distance = commit_distance(project, str(generated_hash))
        if distance is not None and distance > WORKFLOW_UNDERSTANDING_COMMIT_THRESHOLD:
            stale_reasons.append(
                {
                    "code": "commit-distance",
                    "message": f"Product understanding is more than {WORKFLOW_UNDERSTANDING_COMMIT_THRESHOLD} commits behind HEAD.",
                }
            )
    return UnderstandingEvaluation("stale" if stale_reasons else "ready", context, [], stale_reasons, [])


def current_git_hash(project: Path) -> str | None:
    result = run_text(
        ["git", "-C", str(project), "rev-parse", "HEAD"],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value or None


def commit_distance(project: Path, generated_hash: str) -> int | None:
    result = run_text(
        ["git", "-C", str(project), "rev-list", "--count", f"{generated_hash}..HEAD"],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    try:
        return int(result.stdout.strip())
    except ValueError:
        return None


def _parse_iso_datetime(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _resolve_alias(project: Path, stage: str, alias: str | None, rule: StagePrerequisiteRule) -> str | dict[str, list[str]] | None:
    if alias:
        return layout.ensure_path_safe_alias(alias)
    if not rule.requires_alias:
        return None
    aliases = sorted(
        str(item.get("alias"))
        for item in load_registry(project).get("useCases", [])
        if item.get("alias")
    )
    if len(aliases) == 1:
        return aliases[0]
    return {"availableAliases": aliases}


def _missing_stage_artifacts(project: Path, stage: str, alias: str | None) -> list[dict[str, str]]:
    if stage in {"understand", "specify", "list"}:
        return []
    if not alias:
        return []
    use_case_record = f"{layout.WORKSPACE_DIR}/{layout.USE_CASES_DIR}/{alias}.yaml"
    try:
        record = load_use_case(project, alias)
    except FileNotFoundError:
        return [{"path": use_case_record, "nextStage": "specify"}]
    if stage in {"plan", "tasks", "implement", "validate", "run", "repair"} and _has_unresolved_blocking_clarifications(record):
        return [{"path": f"{use_case_record}:authoringQuestions", "nextStage": "clarify"}]

    spec_md = _stage_rel(project, alias, "specify")
    if stage in {"clarify", "plan"} and not _exists(project, spec_md):
        return [{"path": spec_md, "nextStage": "specify"}]
    if stage in {"tasks", "implement", "validate", "run", "repair"}:
        if not _exists(project, spec_md):
            return [{"path": spec_md, "nextStage": "specify"}]

    plan_md = _stage_rel(project, alias, "plan")
    plan_yaml = plan_md.removesuffix(".md") + ".yaml"
    if stage in {"tasks", "implement", "validate", "run", "repair"} and (
        not _exists(project, plan_md) or not _exists(project, plan_yaml)
    ):
        return [
            {"path": path, "nextStage": "plan"}
            for path in [plan_md, plan_yaml]
            if not _exists(project, path)
        ]

    tasks_md = _stage_rel(project, alias, "tasks")
    tasks_yaml = tasks_md.removesuffix(".md") + ".yaml"
    if stage in {"implement", "validate", "run", "repair"} and (
        not _exists(project, tasks_md) or not _exists(project, tasks_yaml)
    ):
        return [
            {"path": path, "nextStage": "tasks"}
            for path in [tasks_md, tasks_yaml]
            if not _exists(project, path)
        ]

    if stage in {"validate", "run", "repair"}:
        artifact_missing = _missing_generated_artifacts(project, record)
        if artifact_missing:
            return [{"path": path, "nextStage": "implement"} for path in artifact_missing]

    if stage == "run" and record.status != "ready":
        return [{"path": f"{use_case_record}:status=ready", "nextStage": "validate"}]

    if stage == "repair" and not _has_repair_context(record):
        return [{"path": f"{use_case_record}:validation-or-run-finding", "nextStage": "validate"}]

    return []


def _missing_generated_artifacts(project: Path, record: Any) -> list[str]:
    missing: list[str] = []
    if not record.runRequest:
        missing.append(f"{layout.WORKSPACE_DIR}/{layout.RUN_REQUESTS_DIR}/{record.alias}.yaml")
    elif not _exists(project, record.runRequest.path):
        missing.append(record.runRequest.path)
    if not record.mainSkill:
        missing.append(f"{layout.WORKSPACE_DIR}/{layout.SKILLS_DIR}/{record.alias}.browser.md")
    elif not _exists(project, record.mainSkill.path):
        missing.append(record.mainSkill.path)
    for skill in [*record.skills, *record.sourceOnlySkills]:
        if not _exists(project, skill.path):
            missing.append(skill.path)
    return sorted(set(missing))


def _has_repair_context(record: Any) -> bool:
    validation = record.validation or {}
    validation_status = validation.get("status") or validation.get("data", {}).get("status")
    validation_findings = validation.get("findings") or validation.get("data", {}).get("findings")
    if validation_status in {"failed", "blocked", "error"} or validation_findings:
        return True
    last_run = record.lastRun or {}
    return bool(last_run and last_run.get("status") not in {None, "passed"})


def _has_unresolved_blocking_clarifications(record: Any) -> bool:
    blocking_terms = {"runtime", "data", "credential", "credentials", "permission", "permissions", "outcome", "expectedoutcome"}
    for question in getattr(record, "authoringQuestions", []):
        if question.status == "answered":
            continue
        text = f"{question.affects or ''} {question.reason or ''} {question.prompt or ''}".lower()
        if any(term in text for term in blocking_terms):
            return True
    return False


def _target_environment_confirmation_blocker(
    project: Path,
    stage: str,
    alias: str,
) -> dict[str, Any] | None:
    if stage not in {"plan", "tasks", "implement", "validate", "run", "repair"}:
        return None
    try:
        record = load_use_case(project, alias)
    except FileNotFoundError:
        return None
    question = next(
        (
            item
            for item in getattr(record, "authoringQuestions", [])
            if item.id == "browser-target-environment"
            and item.requiresConfirmation
        ),
        None,
    )
    if not question:
        return None
    workflow = record.workflow if isinstance(record.workflow, dict) else {}
    run_id = workflow.get("lastWorkflowRunId")
    confirmed = False
    if run_id:
        try:
            run = load_workflow_run(project, str(run_id))
            confirmation = run.targetEnvironmentConfirmation or {}
            confirmed = bool(
                confirmation.get("url")
                and confirmation.get("source") in {"direct-user", "explicit-command"}
            )
        except FileNotFoundError:
            confirmed = False
    if confirmed and question.status == "answered":
        return None
    suggested = (question.suggestedAnswer or {}).get("baseUrl")
    return {
        "code": "clarification.target-environment-confirmation-required",
        "severity": "blocker",
        "category": "target-environment",
        "message": (
            "Confirm the recommended browser target or provide another target "
            "for this workflow before browser authoring or execution."
        ),
        "questionId": question.id,
        "recommendedTarget": suggested,
        "recoveryCommand": _native_next("clarify", alias),
    }


def _stage_rel(project: Path, alias: str, stage: str) -> str:
    return layout.to_project_relative(project, layout.workflow_stage_document_path(project, alias, stage))


def _exists(project: Path, rel_path: str) -> bool:
    try:
        return layout.project_relative_path(project, rel_path).exists()
    except ValueError:
        return False


def _understanding_payload(context: dict[str, Any]) -> dict[str, Any]:
    if not context:
        return {
            "projectOverview": "",
            "candidateUseCases": [],
            "recommendedCandidate": None,
            "candidateSelectionSource": "workflow.recommend-first-run",
            "firstRunRecommendationCommand": "verifysignal workflow recommend-first-run --json",
            "understanding": {},
        }
    candidates = list(context.get("candidateUseCases", []))
    return {
        "projectOverview": context.get("productSummary") or context.get("repositorySummary") or context.get("productName", ""),
        "candidateUseCases": candidates,
        "recommendedCandidate": _recommended_candidate(candidates),
        "candidateSelectionSource": "workflow.recommend-first-run",
        "firstRunRecommendationCommand": "verifysignal workflow recommend-first-run --json",
        "understanding": context.get("understanding", {}),
    }


def _recommended_candidate(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not candidates:
        return None
    confidence_order = {"high": 0, "medium": 1, "low": 2}
    return sorted(candidates, key=lambda item: confidence_order.get(str(item.get("confidence", "medium")), 1))[0]


def _native_next(stage: str, alias: str | None) -> str:
    command = native_invocation(stage)
    return f"{command} {alias}".strip() if alias else command


def _stale_warnings(stage: str) -> list[str]:
    return [
        f"Product understanding may be stale. Refresh is recommended before running /verifysignal-{stage}.",
    ]


def _stale_declined_warnings(stage: str) -> list[str]:
    return [
        f"Continuing /verifysignal-{stage} with stale product understanding because refresh was declined.",
    ]


def _alias_scoped_stale_warnings(stage: str, alias: str, impact_status: str) -> list[str]:
    return [
        (
            f"Product understanding is stale, but /verifysignal-{stage} {alias} is alias-scoped. "
            f"Use-case impact is {impact_status}; refresh is not the only recovery path."
        )
    ]


def _result(
    stage: str,
    alias: str | None,
    status: str,
    *,
    can_proceed: bool,
    requires_confirmation: bool = False,
    missing_artifacts: list[str] | None = None,
    stale_reasons: list[dict[str, str]] | None = None,
    warnings: list[str] | None = None,
    recommended_action: str = "continue",
    next_command: str | None = None,
    recorded_decision: dict[str, Any] | None = None,
    available_aliases: list[str] | None = None,
    projectOverview: str = "",
    candidateUseCases: list[dict[str, Any]] | None = None,
    recommendedCandidate: dict[str, Any] | None = None,
    candidateSelectionSource: str = "",
    firstRunRecommendationCommand: str = "",
    understanding: dict[str, Any] | None = None,
    onboardingPreparation: dict[str, Any] | None = None,
    resumeCommand: str | None = None,
    stageCards: list[dict[str, Any]] | None = None,
    refreshImpact: dict[str, Any] | None = None,
    understandingFreshness: dict[str, Any] | None = None,
    confirmation: dict[str, Any] | None = None,
    rerunDecision: dict[str, Any] | None = None,
    blockers: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    resolved_missing_artifacts = missing_artifacts or []
    resolved_next_command = next_command or _native_next(stage, alias)
    resolved_blockers = list(blockers or [])
    if (
        not can_proceed
        and resolved_missing_artifacts
        and not resolved_blockers
    ):
        resolved_blockers.append(
            {
                "code": "workflow.prerequisite-missing",
                "severity": "blocker",
                "category": "workflow",
                "message": (
                    f"The {stage} stage cannot proceed because required "
                    "workflow artifacts are missing."
                ),
                "missingArtifacts": resolved_missing_artifacts,
                "recoveryCommand": resolved_next_command,
            }
        )
    result: dict[str, Any] = {
        "schemaVersion": WORKFLOW_CAPABILITY_SCHEMA,
        "prerequisiteSchemaVersion": WORKFLOW_PREREQUISITE_CHECK_SCHEMA,
        "requiredCapability": WORKFLOW_GUARDRAILS_CAPABILITY,
        "supported": True,
        "stage": stage,
        "useCaseAlias": alias,
        "status": status,
        "canProceed": can_proceed,
        "requiresConfirmation": requires_confirmation,
        "missingArtifacts": resolved_missing_artifacts,
        "staleReasons": stale_reasons or [],
        "warnings": warnings or [],
        "recommendedAction": recommended_action,
        "nextCommand": resolved_next_command,
        "recordedDecision": recorded_decision,
        "projectOverview": projectOverview,
        "candidateUseCases": candidateUseCases or [],
        "recommendedCandidate": recommendedCandidate,
        "candidateSelectionSource": candidateSelectionSource,
        "firstRunRecommendationCommand": firstRunRecommendationCommand,
        "understanding": understanding or {},
        "onboardingPreparation": onboardingPreparation,
        "resumeCommand": resumeCommand,
        "stageCards": stageCards or [],
        "blockers": resolved_blockers,
    }
    if refreshImpact is not None:
        result["refreshImpact"] = refreshImpact
    if understandingFreshness is not None:
        result["understandingFreshness"] = understandingFreshness
    if confirmation is not None:
        result["confirmation"] = confirmation
    if rerunDecision is not None:
        result["rerunDecision"] = rerunDecision
    if available_aliases is not None:
        result["availableAliases"] = available_aliases
    return result
