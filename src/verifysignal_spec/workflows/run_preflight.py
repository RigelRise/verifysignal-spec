from __future__ import annotations

from typing import Any

from verifysignal_spec.workspace.models import ConfirmationRequirement
from verifysignal_spec.workspace.validation import validate_side_effect_declaration
from verifysignal_spec.workflows.write_safety import evaluate_rerun_decision


def local_run_policy_blockers(
    use_case: Any,
    *,
    supersede_reviews: list[Any] | None = None,
) -> list[dict[str, Any]]:
    """Collect local-only policy blockers identically for both run entry points."""

    findings = validate_side_effect_declaration(
        use_case.sideEffects,
        use_case.rerunPolicy,
        use_case.runtimeOutputs,
        [item.to_dict() for item in use_case.runtimeInputs],
        runtime_outcomes=[use_case.lastRun] if isinstance(use_case.lastRun, dict) else [],
    )
    blockers: list[dict[str, Any]] = []
    rerun = evaluate_rerun_decision(
        use_case,
        supersede_reviews=supersede_reviews or [],
    )
    for item in findings:
        if item.get("severity") != "blocking":
            continue
        if (
            item.get("code") == "side-effect-observation-review-required"
            and rerun.get("supersededBy")
        ):
            continue
        code = f"runtime.{item.get('code')}"
        observation_review = code == "runtime.side-effect-observation-review-required"
        blockers.append(
            {
                "code": code,
                "severity": "blocker",
                "category": "write-flow-safety",
                "message": item.get("message"),
                "documentationRef": item.get("path"),
                "recommendedAction": (
                    "review-or-supersede-write-outcome"
                    if observation_review
                    else "resolve-run-preflight"
                ),
                "recoveryCommand": (
                    f"verifysignal workflow supersede-write-outcome --alias {use_case.alias} --json"
                    if observation_review
                    else f"verifysignal workflow check run --alias {use_case.alias} --json"
                ),
            }
        )
    return blockers


def build_run_preflight(
    project_metadata: dict[str, Any] | None,
    use_case: Any,
    readiness: Any | None,
    workflow_state: dict[str, Any] | None,
    supersede_reviews: list[Any] | None,
) -> dict[str, Any]:
    """Return the pure, authoritative decision for every run entry point.

    All inputs are already-loaded metadata. This function deliberately performs
    no filesystem, environment, runtime, Core, or confirmation writes.
    """

    metadata = project_metadata or {}
    state = workflow_state or {}
    rerun = evaluate_rerun_decision(
        use_case,
        supersede_reviews=supersede_reviews or [],
    )
    confirmed = {str(item) for item in metadata.get("confirmedRisks", [])}
    requirements = [
        _confirmation_dict(item)
        for item in metadata.get("confirmationRequirements", [])
    ]
    pending = [item for item in requirements if str(item.get("id") or "") not in confirmed]
    active_confirmation = (
        pending[0]
        if pending
        else _rerun_confirmation(use_case, rerun)
        if rerun["decision"] == "requires-confirmation"
        else None
    )

    target_blocker = metadata.get("targetBlocker")
    if isinstance(target_blocker, dict):
        return _blocked(target_blocker, rerun, confirmation=active_confirmation)

    missing = list(state.get("missingArtifacts") or metadata.get("missingArtifacts") or [])
    if missing or str(getattr(use_case, "status", "")) != "ready":
        if not missing:
            missing = [f"use-cases/{getattr(use_case, 'alias', '')}.yaml:status=ready"]
        next_action = str(
            state.get("missingArtifactsNextAction")
            or f"verifysignal validate {getattr(use_case, 'alias', '')} --json"
        )
        return _blocked(
            {
                "code": "workflow.prerequisite-missing",
                "severity": "blocker",
                "category": "workflow",
                "message": "The run stage cannot proceed because required workflow artifacts are missing or not ready.",
                "missingArtifacts": missing,
                "recoveryCommand": next_action,
            },
            rerun,
            confirmation=active_confirmation,
        )

    invalidation_reasons = [
        item
        for item in metadata.get("readinessInvalidationReasons", [])
        if isinstance(item, dict)
        and str(item.get("code") or "")
        not in {"environment-bound", "write-post-commit-risk"}
    ]
    if readiness is None or not _protected_readiness_passed(readiness) or invalidation_reasons:
        next_action = f"verifysignal validate {getattr(use_case, 'alias', '')} --runtime-readiness --json"
        return _blocked(
            {
                "code": "runtime.protected-readiness-required",
                "severity": "blocker",
                "category": "runtime-readiness",
                "message": "Protected runtime validation has not passed.",
                "recoveryCommand": next_action,
            },
            rerun,
            confirmation=active_confirmation,
        )

    policy_blockers = [
        dict(item)
        for item in metadata.get("policyBlockers", [])
        if isinstance(item, dict)
    ]
    if policy_blockers:
        return _blocked(policy_blockers[0], rerun, confirmation=active_confirmation)

    if pending:
        confirmation = active_confirmation or pending[0]
        blocker = {
            "code": "runtime.confirmation-required",
            "severity": "blocker",
            "category": "write-flow-safety",
            "message": str(confirmation.get("reason") or "Run risk requires explicit confirmation."),
            "recoveryCommand": str(
                confirmation.get("recommendedAction")
                or f"verifysignal run {getattr(use_case, 'alias', '')} --confirm-risk {confirmation.get('id')} --json"
            ),
        }
        result = _blocked(blocker, rerun, confirmation=confirmation)
        result["requiresConfirmation"] = True
        return result

    if rerun["decision"] in {"blocked", "requires-confirmation"}:
        requires_confirmation = rerun["decision"] == "requires-confirmation"
        confirmation = active_confirmation if requires_confirmation else None
        blocker = {
            "code": (
                "runtime.rerun-confirmation-required"
                if requires_confirmation
                else "runtime.rerun-policy-blocked"
            ),
            "severity": "blocker",
            "category": "write-flow-safety",
            "message": str(rerun["reason"]),
            "recoveryCommand": str(rerun["nextAction"]),
        }
        result = _blocked(blocker, rerun, confirmation=confirmation)
        result["requiresConfirmation"] = requires_confirmation
        return result

    return {
        "status": "ready",
        "canProceed": True,
        "blockers": [],
        "requiresConfirmation": False,
        "confirmation": None,
        "rerunDecision": rerun,
        "nextAction": "Proceed with run.",
    }


def _protected_readiness_passed(readiness: Any) -> bool:
    def value(name: str, default: Any = None) -> Any:
        return readiness.get(name, default) if isinstance(readiness, dict) else getattr(readiness, name, default)

    return bool(
        value("status") == "ready"
        and value("readinessScope") == "protected-operation"
        and value("commandCompatibilityStatus") == "passed"
        and value("trustMaterialStatus") == "ready"
        and value("protectedOperationStatus") == "passed"
    )


def _rerun_confirmation(use_case: Any, rerun: dict[str, Any]) -> dict[str, Any]:
    outcome = str(rerun.get("outcomeClass") or "")
    side_effects = use_case.sideEffects if isinstance(use_case.sideEffects, dict) else {}
    risk_class = (
        "unknown-write-risk"
        if outcome == "unknown-write"
        else str(side_effects.get("class") or side_effects.get("sideEffectClass") or "write")
    )
    return ConfirmationRequirement(
        id=str(rerun["confirmationId"]),
        alias=str(use_case.alias),
        riskClass=risk_class,
        scope=str(rerun["confirmationScope"]),
        sourceRunId=(str(rerun["sourceRunId"]) if rerun.get("sourceRunId") else None),
        reason=str(rerun["reason"]),
        recommendedAction=str(rerun["nextAction"]),
        blocksExecution=True,
        expiresWhen=["latest run or protected Core attempt changes"],
    ).to_dict()


def _confirmation_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, ConfirmationRequirement):
        return value.to_dict()
    return dict(value) if isinstance(value, dict) else {}


def _blocked(
    blocker: dict[str, Any],
    rerun: dict[str, Any],
    *,
    confirmation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "status": "blocked",
        "canProceed": False,
        "blockers": [blocker],
        "requiresConfirmation": confirmation is not None,
        "confirmation": confirmation,
        "rerunDecision": rerun,
        "recommendedAction": str(
            blocker.get("recommendedAction") or "resolve-run-preflight"
        ),
        "nextAction": str(blocker.get("recoveryCommand") or rerun.get("nextAction") or "Review blockers."),
    }
