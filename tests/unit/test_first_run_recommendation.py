from __future__ import annotations

from verifysignal_spec.workflows.first_run import build_first_run_recommendation, score_first_run_candidates
from verifysignal_spec.workflows.models import CandidateValidationUseCase
from tests.fixtures.workflows.golden_path_productization import AUTH_ALIAS, PUBLIC_ALIAS, create_golden_path_workspace


def test_first_run_ranking_prefers_real_public_no_credential_candidate() -> None:
    candidates = [
        CandidateValidationUseCase(
            alias=AUTH_ALIAS,
            surface="/settings/account",
            behavior="Authenticated settings render.",
            sourceInventoryItems=["route-settings"],
            rationale="Needs credentials.",
            confidence="high",
            priority="high",
            requiresEnvironment=True,
            knownRuntimeRequirements=["baseUrl", "credential:qa-user"],
            sideEffectClass="none",
            groundingStatus="authentication-required",
        ),
        CandidateValidationUseCase(
            alias=PUBLIC_ALIAS,
            surface="/",
            behavior="Public home page renders.",
            sourceInventoryItems=["route-home"],
            rationale="No auth.",
            confidence="high",
            priority="critical",
            requiresEnvironment=True,
            knownRuntimeRequirements=["baseUrl"],
            sideEffectClass="none",
            groundingStatus="observed",
        ),
    ]

    ranked = score_first_run_candidates(candidates, target_status="resolved", inventory_status="complete")

    assert ranked[0].candidateAlias == PUBLIC_ALIAS
    assert ranked[0].blockers == []
    assert ranked[1].blockers == []
    assert ranked[1].requiresExplicitAcceptance is True
    assert "noCredentials" in ranked[1].idealCriteriaMissing


def test_recommendation_blocks_fake_or_demo_target(tmp_path) -> None:
    create_golden_path_workspace(tmp_path, target="https://demo.example.com")

    recommendation = build_first_run_recommendation(tmp_path).to_dict()

    assert recommendation["status"] == "blocked"
    assert recommendation["recommendedCandidate"] is None
    assert "fake" not in recommendation["recommendationText"].lower()
