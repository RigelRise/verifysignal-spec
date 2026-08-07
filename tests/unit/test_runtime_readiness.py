from __future__ import annotations

from verifysignal_spec.workflows.runtime_readiness import evaluate_runtime_readiness
from verifysignal_spec.workspace.models import ArtifactReference, RuntimeInputRequirement, UseCaseRecord
from verifysignal_spec.workspace.repository import init_workspace, save_document, save_use_case


def _workspace_with_run_request(
    tmp_path,
    parameters: dict[str, str],
    *,
    workflow=None,
    side_effects=None,
    last_run=None,
) -> None:
    init_workspace(tmp_path)
    run_request = ".verifysignal/run-requests/profile.yaml"
    skill = ".verifysignal/skills/profile.browser.md"
    (tmp_path / ".verifysignal/run-requests").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".verifysignal/skills").mkdir(parents=True, exist_ok=True)
    save_document(
        tmp_path / run_request,
        {
            "schemaVersion": "qa-run-request/v1",
            "parameters": parameters,
            "skills": [{"id": "skill.profile", "version": "1.0.0"}],
        },
    )
    (tmp_path / skill).write_text("# Profile\n", encoding="utf-8")
    save_use_case(
        tmp_path,
        UseCaseRecord(
            alias="profile",
            title="Profile",
            description="Validate profile.",
            runRequest=ArtifactReference(path=run_request, kind="run-request", id="request.profile"),
            mainSkill=ArtifactReference(path=skill, kind="skill", id="skill.profile"),
            skills=[ArtifactReference(path=skill, kind="skill", id="skill.profile")],
            runtimeInputs=[RuntimeInputRequirement(name="baseUrl", required=True)],
            workflow=workflow,
            sideEffects=side_effects,
            lastRun=last_run,
        ),
    )


def test_runtime_readiness_blocks_missing_resolved_target(tmp_path) -> None:
    _workspace_with_run_request(tmp_path, {"baseUrl": ""})

    readiness = evaluate_runtime_readiness(tmp_path, "profile", authoring_result={"status": "passed"})

    assert readiness.status == "blocked"
    assert readiness.targetResolutionStatus == "unresolved"
    assert readiness.requiredPrerequisiteStatus == "missing"
    assert readiness.fullBrowserFlowExecuted is False
    assert "runtime.target-unresolved" in readiness.findingIds


def test_runtime_readiness_classifies_unreachable_target_as_environment_recovery(tmp_path) -> None:
    _workspace_with_run_request(tmp_path, {"baseUrl": "https://app.example.test"})

    readiness = evaluate_runtime_readiness(
        tmp_path,
        "profile",
        authoring_result={"status": "passed"},
        reachability_checker=lambda _locator: False,
    )

    assert readiness.status == "blocked"
    assert readiness.targetResolutionStatus == "resolved"
    assert readiness.targetReachabilityStatus == "unreachable"
    assert "runtime.target-unreachable" in readiness.findingIds


def test_runtime_readiness_passes_without_full_browser_execution(tmp_path) -> None:
    _workspace_with_run_request(tmp_path, {"baseUrl": "https://app.example.test"})

    readiness = evaluate_runtime_readiness(
        tmp_path,
        "profile",
        authoring_result={"status": "passed"},
        reachability_checker=lambda _locator: True,
    )

    assert readiness.status == "passed"
    assert readiness.targetResolutionStatus == "resolved"
    assert readiness.targetReachabilityStatus == "reachable"
    assert readiness.authoringReadinessStatus == "passed"
    assert readiness.fullBrowserFlowExecuted is False


def test_runtime_readiness_reconciles_the_last_read_only_side_effect_outcome(tmp_path) -> None:
    policy = {
        "class": "none",
        "mode": "observe",
        "allowed": [],
        "forbidden": [],
    }
    _workspace_with_run_request(
        tmp_path,
        {"baseUrl": "https://app.example.test"},
        side_effects=policy,
        last_run={
            "runId": "run-policy-violation",
            "status": "failed",
            "sideEffectPolicy": policy,
            "sideEffects": {
                "violations": [
                    {
                        "code": "side-effect-class-none-violation",
                        "severity": "warning",
                        "message": "Unexpected POST",
                    }
                ]
            },
            "postCommitInterpretation": {
                "sideEffectStatus": "violated",
                "rerunRisk": "blocked",
            },
        },
    )

    readiness = evaluate_runtime_readiness(
        tmp_path,
        "profile",
        authoring_result={"status": "passed"},
        reachability_checker=lambda _locator: True,
    )

    assert readiness.status == "blocked"
    assert "runtime.side-effect-observation-review-required" in readiness.findingIds


def test_runtime_readiness_flags_empty_target_after_stage_handoff_resolution(tmp_path) -> None:
    _workspace_with_run_request(
        tmp_path,
        {"baseUrl": ""},
        workflow={
            "stageHandoffDecisions": [
                {
                    "key": "browserTargetEnvironment",
                    "valueSummary": "https://app.example.test",
                    "sourceStage": "clarify",
                    "status": "active",
                }
            ]
        },
    )

    readiness = evaluate_runtime_readiness(tmp_path, "profile", authoring_result={"status": "passed"})

    assert readiness.status == "blocked"
    assert readiness.targetResolutionStatus == "resolved"
    assert "runtime.stage-handoff-defect.baseUrl-empty-after-resolution" in readiness.findingIds
