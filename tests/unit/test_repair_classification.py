from __future__ import annotations

from verifysignal_spec.workflows.repair_classification import classify_runtime_feedback
from verifysignal_spec.workflows.repair_recommendations import classify_repair_findings


def test_wait_flow_timeout_is_classified_with_high_confidence() -> None:
    finding = classify_runtime_feedback(
        {
            "code": "wait-timeout",
            "message": "Step scroll-to-activity timed out waiting for .swiper-slide while activity skeletons were visible.",
            "gateId": "home-activity-slider",
        }
    )

    assert finding.category == "wait-flow-issue"
    assert finding.recommendedAction == "implement-repair"
    assert finding.confidence == "high"
    assert finding.affectedGates == ["home-activity-slider"]


def test_selector_failure_is_classified_separately_from_wait_flow() -> None:
    finding = classify_runtime_feedback({"code": "strict-mode-violation", "message": "Locator matched multiple elements."})

    assert finding.category == "selector-issue"
    assert finding.recommendedAction == "implement-repair"


def test_aborted_run_missing_coverage_is_diagnostic_mapping_issue() -> None:
    finding = classify_runtime_feedback({"code": "missing-gate-coverage", "message": "No mapped evidence was found because Core/browser execution failed."})

    assert finding.category == "coverage-mapping-issue"
    assert finding.severity == "warning"
    assert finding.recommendedAction == "implement-repair"


def test_side_effect_policy_violation_requires_owner_policy_review_and_is_never_auto_allowed() -> None:
    source = {
        "code": "side-effect-class-none-violation",
        "message": "A side effect was observed although the policy class is none. Review the policy before rerun.",
    }
    finding = classify_runtime_feedback(source)
    recommendations = classify_repair_findings([source])

    assert finding.category == "side-effect-policy-issue"
    assert finding.recommendedAction == "blocked"
    assert recommendations[0].runtimeCategory == "side-effect-policy-issue"
    assert recommendations[0].requiresUserDecision is True
    assert recommendations[0].autonomy == "blocked"
    assert recommendations[0].safeMechanical is False
    assert "allow" not in recommendations[0].action.lower()
