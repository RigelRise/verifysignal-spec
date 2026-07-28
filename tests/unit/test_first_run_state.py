from __future__ import annotations

from verifysignal_spec.workflows.first_run import classify_first_run_status
from verifysignal_spec.workflows.models import (
    FirstRunCandidate,
    FirstRunCandidateScore,
    FirstRunRecommendation,
    GoldenPathRunState,
)


def test_first_run_candidate_and_score_round_trip() -> None:
    candidate = FirstRunCandidate(
        alias="home-page-unauth",
        surface="/",
        behavior="Home page renders public content.",
        sourceInventoryItems=["route-home"],
        priority="critical",
        confidence="high",
        requiresEnvironment=True,
        knownRuntimeRequirements=["baseUrl"],
        sideEffectClass="none",
        groundingStatus="observed",
    )
    score = FirstRunCandidateScore(
        candidateAlias=candidate.alias,
        rank=1,
        score=95,
        lowSetupRisk=25,
        reachableRealTarget=20,
        credentialRisk=0,
        renderedEvidenceSimplicity=20,
        dataDependencyRisk=0,
        inventoryFreshness=10,
        rationale="Public page, real target, no credentials.",
    )

    assert candidate.to_dict()["alias"] == "home-page-unauth"
    assert candidate.to_dict()["sideEffectClass"] == "none"
    assert candidate.to_dict()["groundingStatus"] == "observed"
    assert score.to_dict()["scoringSignals"]["lowSetupRisk"] == 25


def test_first_run_recommendation_schema_and_stage_cards() -> None:
    recommendation = FirstRunRecommendation(
        status="ready",
        targetStatus="resolved",
        recommendedCandidate={"alias": "home-page-unauth"},
        rankedCandidates=[{"alias": "home-page-unauth", "rank": 1, "score": 95}],
        recommendationText="I strongly recommend starting with home-page-unauth.",
        acceptancePrompt="Accept this recommended first run to see the product end to end.",
        skipMeaning="Skipping records that the golden path was declined, not passed or failed.",
        stageCards=[
            {
                "stageId": "recommendation",
                "title": "Recommended First Run",
                "statusMarker": "[RECOMMENDED]",
                "summary": "home-page-unauth is recommended.",
                "whyItMatters": "It shows the product on a stable real target.",
                "primaryEvidence": "No credentials and simple rendered evidence.",
                "nextAction": "Accept or skip.",
            }
        ],
        nextAction="verifysignal workflow accept-first-run home-page-unauth --json",
    )

    data = recommendation.to_dict()

    assert data["schemaVersion"] == "verifysignal-spec-first-run-recommendation/v1"
    assert data["status"] == "ready"
    assert data["stageCards"][0]["statusMarker"] == "[RECOMMENDED]"


def test_golden_path_run_state_classifies_strict_pass_and_repaired_pass() -> None:
    assert classify_first_run_status("passed", "complete", []) == ("passed", True)
    assert classify_first_run_status("passed", "complete", [], repaired=True) == ("repaired-passed", True)
    assert classify_first_run_status("passed", "incomplete", ["home-activity-slider"]) == ("incomplete", False)
    assert classify_first_run_status("failed", "diagnostic", []) == ("failed", False)
    assert classify_first_run_status(
        "passed",
        "complete",
        [],
        side_effect_status="violated",
        side_effect_violations=[{"code": "side-effect-class-none-violation"}],
    ) == ("failed", False)
    assert classify_first_run_status(
        "passed",
        "complete",
        [],
        side_effect_status="not-observed",
        side_effect_violations=[],
    ) == ("passed", True)

    state = GoldenPathRunState.from_run_result(
        use_case_alias="home-page-unauth",
        target="https://app.example.test",
        core_browser_status="passed",
        spec_coverage_status="complete",
        missing_required_gates=[],
    )

    assert state.firstRunStatus == "passed"
    assert state.strictPass is True
    assert state.to_dict()["target"] == "https://app.example.test"
