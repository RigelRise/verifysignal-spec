from __future__ import annotations

from .gate_coverage import missing_required_gate_contradictions
from .models import GateCoverageResult, PlannedValidationGate, RepairRecommendation, RuntimeContradiction
from .repair_classification import classify_runtime_feedback


# SINGLE SOURCE OF TRUTH for "can this category actually be applied automatically?".
# `commands.repair._apply_safe_artifact_repair` dispatches its real on-disk mutator off this SAME set,
# so a category can never be LABELED `auto-applied` without a mutator existing, and adding a future
# mutator flips its label automatically — the label and the mechanism cannot drift apart.
# (Bug this closes: selector-ambiguity/wait-strategy/run-profile-defaults were labeled `auto-applied`
# while their mutator returns None — claiming an automation that does not exist.)
MUTABLE_SAFE_CATEGORIES = frozenset({"main-skill-ordering"})


def safe_repair_autonomy(safe_category: str) -> str:
    """Autonomy describes the available MECHANISM, not an aspiration."""
    return "auto-applied" if safe_category in MUTABLE_SAFE_CATEGORIES else "propose-only"


_RERUN_RESTRICTIVENESS = {
    "allowed": 0,
    "allowed-with-new-inputs": 1,
    "requires-confirmation": 2,
    "blocked": 3,
}


def combine_rerun_decision(core_risk: str | None, spec_decision: str | None) -> str:
    core_decision = _core_risk_to_spec_decision(core_risk)
    spec_decision = spec_decision or "blocked"
    if _RERUN_RESTRICTIVENESS.get(core_decision, 3) >= _RERUN_RESTRICTIVENESS.get(spec_decision, 3):
        return core_decision
    return spec_decision


def _core_risk_to_spec_decision(core_risk: str | None) -> str:
    mapping = {
        "safe": "allowed",
        "safe-with-new-inputs": "allowed-with-new-inputs",
        "requires-confirmation": "requires-confirmation",
        "blocked": "blocked",
    }
    return mapping.get(str(core_risk or "blocked"), "blocked")


def recommend_repairs_for_gate_coverage(
    gate_coverage: list[GateCoverageResult],
    planned_gates: list[PlannedValidationGate],
    *,
    source_run_id: str | None = None,
) -> list[RuntimeContradiction]:
    return missing_required_gate_contradictions(gate_coverage, planned_gates, source_run_id=source_run_id)


def proposals_from_contradictions(contradictions: list[RuntimeContradiction]) -> list[dict[str, str]]:
    proposals: list[dict[str, str]] = []
    for contradiction in contradictions:
        proposals.append(
            {
                "artifact": "planned validation gates",
                "field": contradiction.gateId,
                "reason": contradiction.observedEvidence,
                "expectedEffect": _expected_effect(contradiction.recommendation),
            }
        )
    return proposals


def classify_repair_findings(findings: list[dict[str, object]]) -> list[RepairRecommendation]:
    recommendations: list[RepairRecommendation] = []
    for index, finding in enumerate(findings, start=1):
        code = str(finding.get("code") or "")
        message = str(finding.get("message") or finding.get("reason") or "")
        text = f"{code} {message}".lower()
        artifact = str(finding.get("artifact") or "").strip()
        path = str(finding.get("path") or "").strip()
        affected = [item for item in [artifact] if item]
        source_feedback = [item for item in [code or f"finding-{index}", path] if item]

        blocked_category = _blocked_category(text)
        if blocked_category:
            category, reason = blocked_category
            recommendations.append(
                RepairRecommendation(
                    id=f"repair-{index}-{category}",
                    category=category,  # type: ignore[arg-type]
                    summary=message or "Repair would change the approved validation intent.",
                    action="Return to clarification or planning before changing this behavior.",
                    affectedArtifacts=affected,
                    blockedReason=reason,
                    requiresUserDecision=True,
                    sourceFeedback=source_feedback,
                    autonomy="blocked" if category == "replan-required" else "confirmation-required",
                    safeMechanical=False,
                    intentPreserved=False,
                )
            )
            continue

        write_risk = _write_rerun_risk(finding, text)
        if write_risk:
            recommendations.append(
                RepairRecommendation(
                    id=f"repair-{index}-write-rerun-risk",
                    category="runtime-setup",
                    runtimeCategory="write-flow-safety",
                    summary=message or "The run may have crossed the write commit boundary.",
                    action="Review the created or affected resource before repair, cleanup, or rerun. Follow the explicit rerun policy and Core rerunRisk.",
                    affectedArtifacts=affected,
                    blockedReason=write_risk,
                    requiresUserDecision=True,
                    sourceFeedback=source_feedback,
                    autonomy="blocked",
                    safeMechanical=False,
                    intentPreserved=False,
                )
            )
            continue

        classified = classify_runtime_feedback(finding)
        if classified.category == "side-effect-policy-issue":
            recommendations.append(
                RepairRecommendation(
                    id=f"repair-{index}-side-effect-policy-review",
                    category="runtime-setup",
                    runtimeCategory=classified.category,
                    summary=classified.summary,
                    action=(
                        "Review the observed requests and update the declared policy explicitly when justified; "
                        "VerifySignal will not modify policy automatically. Revalidate, then rerun to collect clean evidence."
                    ),
                    affectedArtifacts=affected,
                    blockedReason="Observed network activity requires an owner policy decision before rerun.",
                    requiresUserDecision=True,
                    sourceFeedback=[*source_feedback, *classified.evidence],
                    autonomy="blocked",
                    safeMechanical=False,
                    intentPreserved=False,
                )
            )
            continue
        if classified.category == "wait-flow-issue":
            # One local for both the prose and the field: they are rendered from the same value, so
            # they cannot drift the way the old hand-written sentence did.
            autonomy = safe_repair_autonomy("wait-strategy")
            recommendations.append(
                RepairRecommendation(
                    id=f"repair-{index}-wait-strategy",
                    category="safe-artifact-repair",
                    runtimeCategory=classified.category,
                    safeCategory="wait-strategy",
                    summary=classified.summary,
                    action=_safe_action("wait-strategy", autonomy),
                    affectedArtifacts=affected,
                    requiresUserDecision=False,
                    sourceFeedback=[*source_feedback, *classified.evidence],
                    autonomy=autonomy,
                    safeMechanical=True,
                    intentPreserved=True,
                )
            )
            continue
        if classified.category == "selector-issue":
            autonomy = safe_repair_autonomy("selector-ambiguity")
            recommendations.append(
                RepairRecommendation(
                    id=f"repair-{index}-selector-ambiguity",
                    category="safe-artifact-repair",
                    runtimeCategory=classified.category,
                    safeCategory="selector-ambiguity",
                    summary=classified.summary,
                    action=_safe_action("selector-ambiguity", autonomy),
                    affectedArtifacts=affected,
                    requiresUserDecision=False,
                    sourceFeedback=[*source_feedback, *classified.evidence],
                    autonomy=autonomy,
                    safeMechanical=True,
                    intentPreserved=True,
                )
            )
            continue
        if classified.category == "coverage-mapping-issue":
            recommendations.append(
                RepairRecommendation(
                    id=f"repair-{index}-gateid-mapping",
                    category="safe-artifact-repair",
                    runtimeCategory=classified.category,
                    safeCategory="gateid-mapping",
                    summary=classified.summary,
                    # Not derived from safe_repair_autonomy: coverage mapping can alter validation
                    # intent, so it is confirmation-gated regardless of any mutator.
                    action=_safe_action("gateid-mapping", "confirmation-required"),
                    affectedArtifacts=affected,
                    blockedReason=_confirmation_reason("gateid-mapping"),
                    requiresUserDecision=True,
                    sourceFeedback=[*source_feedback, *classified.evidence],
                    autonomy="confirmation-required",
                    safeMechanical=False,
                    intentPreserved=False,
                )
            )
            continue
        if classified.category == "execution-boundary-issue":
            autonomy = safe_repair_autonomy("main-skill-ordering")
            recommendations.append(
                RepairRecommendation(
                    id=f"repair-{index}-skill-execution-boundary",
                    category="safe-artifact-repair",
                    runtimeCategory=classified.category,
                    safeCategory="main-skill-ordering",
                    summary=classified.summary,
                    # This used to be a literal, divergent from _safe_action's own main-skill-ordering
                    # entry — one category, two different sentences, the dict's one unreachable.
                    action=_safe_action("main-skill-ordering", autonomy),
                    affectedArtifacts=affected,
                    requiresUserDecision=False,
                    sourceFeedback=[*source_feedback, *classified.evidence],
                    autonomy=autonomy,
                    safeMechanical=True,
                    intentPreserved=True,
                )
            )
            continue
        if classified.category in {"missing-prerequisite", "environment-recovery"}:
            recommendations.append(
                RepairRecommendation(
                    id=f"repair-{index}-{classified.category}",
                    category="runtime-setup",
                    runtimeCategory=classified.category,
                    summary=classified.summary,
                    action="Resolve the runtime environment or prerequisite, then rerun validation.",
                    affectedArtifacts=affected,
                    blockedReason=classified.summary,
                    requiresUserDecision=True,
                    sourceFeedback=[*source_feedback, *classified.evidence],
                    autonomy="confirmation-required",
                    safeMechanical=False,
                    intentPreserved=False,
                )
            )
            continue
        if classified.category == "data-product-state-issue":
            recommendations.append(
                RepairRecommendation(
                    id=f"repair-{index}-data-product-state",
                    category="clarification-required",
                    runtimeCategory=classified.category,
                    summary=classified.summary,
                    action="Return to clarification or planning before changing data assumptions or gate intent.",
                    affectedArtifacts=affected,
                    blockedReason="Data or product-state changes affect validation intent.",
                    requiresUserDecision=True,
                    sourceFeedback=[*source_feedback, *classified.evidence],
                    autonomy="confirmation-required",
                    safeMechanical=False,
                    intentPreserved=False,
                )
            )
            continue

        safe_category = _safe_category(text)
        if safe_category:
            requires_confirmation = safe_category in {"gateid-mapping"}
            autonomy = "confirmation-required" if requires_confirmation else safe_repair_autonomy(safe_category)
            recommendations.append(
                RepairRecommendation(
                    id=f"repair-{index}-{safe_category}",
                    category="safe-artifact-repair",
                    runtimeCategory=classified.category if classified.category != "unsupported-feedback" else None,
                    safeCategory=safe_category,  # type: ignore[arg-type]
                    summary=message or f"Runtime feedback indicates {safe_category}.",
                    action=_safe_action(safe_category, autonomy),
                    affectedArtifacts=affected,
                    blockedReason=_confirmation_reason(safe_category) if requires_confirmation else None,
                    requiresUserDecision=requires_confirmation,
                    sourceFeedback=source_feedback,
                    autonomy=autonomy,
                    safeMechanical=not requires_confirmation,
                    intentPreserved=not requires_confirmation,
                )
            )
            continue

        recommendations.append(
            RepairRecommendation(
                id=f"repair-{index}-unsupported",
                category="unsupported",
                summary=message or "Runtime feedback is not in a supported safe repair category.",
                action="Inspect manually and replan if this changes the use case.",
                affectedArtifacts=affected,
                blockedReason="Unsupported runtime feedback cannot be auto-applied.",
                requiresUserDecision=True,
                sourceFeedback=source_feedback,
                autonomy="blocked",
                safeMechanical=False,
                intentPreserved=False,
            )
        )
    return recommendations


def _expected_effect(recommendation: str) -> str:
    if recommendation == "mark-conditional":
        return "Mark the gate conditional with an explicit condition and condition evaluation."
    if recommendation == "update-target-data":
        return "Update the target data or runtime assumptions so the planned gate exists."
    return "Replan the use case before weakening the browser validation skill."


def _safe_category(text: str) -> str | None:
    if any(term in text for term in ["skill-execution.", "execution-boundary", "source-only", "helper-skill"]):
        return "main-skill-ordering"
    if any(term in text for term in ["strict-mode", "strict mode", "multiple elements", "selector ambiguity", "locator matched", "resolved to", "selector did not match", "did not match"]):
        return "selector-ambiguity"
    if any(term in text for term in ["wait-timeout", "timeout", "timed out", "wait strategy", "client-side graphql", "ssr"]):
        return "wait-strategy"
    if any(term in text for term in ["main-skill", "main skill", "helper before main", "helper skill executed"]):
        return "main-skill-ordering"
    if any(term in text for term in ["slowmo", "slow-mo", "slow motion", "run-profile", "debug run"]):
        return "run-profile-defaults"
    if any(term in text for term in ["gateid", "gate id", "gate mapping", "missing gate", "lacks gate"]):
        return "gateid-mapping"
    return None


def _blocked_category(text: str) -> tuple[str, str] | None:
    if any(term in text for term in ["expected-behavior", "expected behavior", "product behavior"]):
        return ("clarification-required", "Repair changes expected product behavior and must be confirmed.")
    if any(term in text for term in ["credential", "password", "secret", "auth requirement"]):
        return ("clarification-required", "Repair changes credential requirements and must be confirmed.")
    if any(term in text for term in ["seeded-data", "data assumption", "data assumptions", "seeded state"]):
        return ("clarification-required", "Repair changes data assumptions and must be confirmed.")
    if any(term in text for term in ["hardcoded-profile", "fixed profile", "dynamic discovery", "replace dynamic"]):
        return ("clarification-required", "Repair changes a clarified runtime/data decision and must be re-clarified.")
    if any(term in text for term in ["weakened-gate", "tab-label-only", "navigation-only", "weaken required", "replace rendered"]):
        return ("replan-required", "Repair weakens required gate evidence and must be replanned.")
    return None


def _write_rerun_risk(finding: dict[str, object], text: str) -> str | None:
    classification = finding.get("resultClassification") if isinstance(finding.get("resultClassification"), dict) else {}
    side_effects = finding.get("sideEffects") if isinstance(finding.get("sideEffects"), dict) else {}
    side_effect_status = str(
        classification.get("sideEffectStatus")
        or finding.get("sideEffectStatus")
        or side_effects.get("status")
        or ""
    )
    failure_phase = str(classification.get("failurePhase") or finding.get("failurePhase") or side_effects.get("failurePhase") or "")
    rerun_risk = str(classification.get("rerunRisk") or finding.get("rerunRisk") or "")
    risky_statuses = {"possible", "likely-committed", "committed-confirmed", "violated", "unknown"}
    if side_effect_status in risky_statuses or failure_phase in {"post-commit", "post-verification"} or rerun_risk in {"requires-confirmation", "blocked"}:
        return "Public Core result indicates post-commit or uncertain mutating activity; blind repair-and-rerun is blocked."
    if any(term in text for term in ["post-commit", "committed-confirmed", "likely-committed", "side effect may", "mutating activity", "rerunrisk blocked"]):
        return "Runtime feedback indicates write-side-effect risk; blind repair-and-rerun is blocked."
    return None


# WHAT each repair changes — the noun phrase only. The VERB ("auto-apply" vs "propose") is derived
# from the autonomy the recommendation actually ships with, never written here. This split is the fix:
# these two used to be one hand-written sentence per category, and selector-ambiguity/wait-strategy
# opened with "Auto-apply" while their autonomy said `propose-only` — set on the ADJACENT line at the
# call site. main-skill-ordering, the only category with a mutator, promised nothing at all.
_SAFE_REPAIR_BODY = {
    "selector-ambiguity": "a stable selector specificity fix that preserves the same product behavior",
    "wait-strategy": "a wait strategy adjustment that waits for rendered evidence",
    "main-skill-ordering": (
        "composition of required helper behavior into the main skill (or reclassification of helper "
        "skills as source-only metadata) that does not weaken required gates"
    ),
    "run-profile-defaults": "observable debug/browser profile defaults that do not override user-specified pacing",
    "gateid-mapping": "a mapping from existing rendered-result evidence to the planned gateId",
}


def _safe_action(safe_category: str, autonomy: str) -> str:
    """Render the action prose FROM the autonomy the caller is about to ship, so the sentence and the
    field cannot contradict each other. Callers must pass the same value they set on ``autonomy``."""
    body = _SAFE_REPAIR_BODY.get(safe_category, "the safe mechanical repair")
    if autonomy == "auto-applied":
        return f"Auto-apply {body}, then revalidate and rerun."
    if autonomy == "confirmation-required":
        return f"Ask for confirmation before applying {body}; apply it only if confirmed, then revalidate and rerun."
    if autonomy == "blocked":
        return f"Do not apply {body} until the blocking condition is resolved."
    # propose-only: there is no mutator, so say so plainly rather than implying the fix lands itself.
    return f"Propose {body} for the developer to apply — VerifySignal will not edit the artifact — then revalidate and rerun."


def _confirmation_reason(safe_category: str) -> str:
    reasons = {
        "selector-ambiguity": "Selector changes can alter validation intent and require confirmation.",
        "wait-strategy": "Flow or wait-strategy changes can alter validation intent and require confirmation.",
        "gateid-mapping": "Coverage mapping changes can alter validation intent and require confirmation.",
    }
    return reasons.get(safe_category, "Repair requires confirmation.")
