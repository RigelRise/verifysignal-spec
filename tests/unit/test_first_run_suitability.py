from __future__ import annotations

from verifysignal_spec.workflows.first_run import evaluate_first_run_ideal_criteria, score_first_run_candidates
from verifysignal_spec.workflows.models import CandidateValidationUseCase, FirstRunCandidate


def test_public_read_only_rendered_candidate_beats_credential_write_candidate() -> None:
    public = CandidateValidationUseCase(
        alias="home-page-unauth",
        surface="/",
        behavior="Public unauthenticated page renders stable hero content.",
        sourceInventoryItems=["route-home"],
        rationale="Simple public page.",
        priority="medium",
        confidence="high",
        requiresEnvironment=True,
        knownRuntimeRequirements=["baseUrl"],
        sideEffectClass="none",
        groundingStatus="observed",
    )
    branch = CandidateValidationUseCase(
        alias="project-multi-actor-add-people",
        surface="/project/[path]",
        behavior="Active branch flow writes contributors after login.",
        sourceInventoryItems=["route-project"],
        rationale="Active branch work.",
        priority="critical",
        confidence="high",
        requiresEnvironment=True,
        knownRuntimeRequirements=["baseUrl", "credential:ba-user", "write operation", "active branch"],
        sideEffectClass="write",
        groundingStatus="observed",
    )

    scores = score_first_run_candidates([branch, public], target_status="resolved", inventory_status="complete")

    assert scores[0].candidateAlias == "home-page-unauth"
    assert scores[0].idealCriteriaMissing == []
    assert scores[1].branchRelevant is True
    assert "readOnly" in scores[1].idealCriteriaMissing
    assert "noCredentials" in scores[1].idealCriteriaMissing


def test_no_ideal_candidate_is_marked_for_explicit_acceptance() -> None:
    auth_read_only = FirstRunCandidate(
        alias="settings-auth",
        surface="/settings",
        behavior="Authenticated settings page renders visible account data.",
        sourceInventoryItems=["route-settings"],
        priority="medium",
        confidence="high",
        requiresEnvironment=True,
        knownRuntimeRequirements=["baseUrl", "credential:user"],
        sideEffectClass="none",
        groundingStatus="authentication-required",
    )

    score = score_first_run_candidates([auth_read_only], target_status="resolved", inventory_status="complete")[0]

    assert score.requiresExplicitAcceptance is True
    assert "publicOrUnauthenticated" in score.idealCriteriaMissing
    assert "noCredentials" in score.idealCriteriaMissing


def test_ideal_criteria_flags_external_and_data_dependencies() -> None:
    candidate = FirstRunCandidate(
        alias="activity-data",
        surface="/",
        behavior="Activity slider renders only when seeded activity data exists.",
        sourceInventoryItems=["route-home"],
        knownRuntimeRequirements=["baseUrl", "seeded activity data"],
        sideEffectClass="none",
        groundingStatus="observed",
    )

    criteria = evaluate_first_run_ideal_criteria(candidate)

    assert criteria.publicOrUnauthenticated is True
    assert criteria.lowExternalDependency is False
    assert criteria.safeToAutoGuide is False


def test_declared_write_is_never_inferred_as_read_only_from_copy() -> None:
    candidate = CandidateValidationUseCase(
        alias="quiet-write",
        surface="/profile",
        behavior="Profile details render.",
        sourceInventoryItems=["route-profile"],
        rationale="Stable rendered evidence.",
        confidence="high",
        priority="critical",
        requiresEnvironment=True,
        knownRuntimeRequirements=["baseUrl"],
        sideEffectClass="write",
        groundingStatus="observed",
    )

    score = score_first_run_candidates(
        [candidate],
        target_status="resolved",
        inventory_status="complete",
    )[0]

    assert "readOnly" in score.idealCriteriaMissing
    assert score.requiresExplicitAcceptance is True
    assert score.idealCriteriaMet.count("safeToAutoGuide") == 0


def test_unknown_grounding_cannot_be_safe_to_auto_guide() -> None:
    candidate = FirstRunCandidate(
        alias="legacy-public",
        surface="/",
        behavior="Public page renders stable content.",
        sourceInventoryItems=["route-home"],
        knownRuntimeRequirements=["baseUrl"],
        sideEffectClass="none",
        groundingStatus="unknown",
    )

    criteria = evaluate_first_run_ideal_criteria(candidate)

    assert criteria.readOnly is True
    assert criteria.safeToAutoGuide is False


def test_exact_score_ties_preserve_inventory_order() -> None:
    candidates = [
        CandidateValidationUseCase(
            alias=alias,
            surface="/same",
            behavior="Public page renders stable content.",
            sourceInventoryItems=[f"route-{alias}"],
            rationale="Equivalent observed evidence.",
            confidence="high",
            priority="high",
            requiresEnvironment=True,
            knownRuntimeRequirements=["baseUrl"],
            sideEffectClass="none",
            groundingStatus="observed",
        )
        for alias in ["z-first", "a-second"]
    ]

    ranked = score_first_run_candidates(
        candidates,
        target_status="resolved",
        inventory_status="complete",
    )

    assert [item.candidateAlias for item in ranked] == ["z-first", "a-second"]
