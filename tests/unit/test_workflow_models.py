from __future__ import annotations

from verifysignal_spec.workflows.models import (
    ArtifactPlan,
    BrowserTargetEnvironment,
    CorePublicContract,
    RuntimePrerequisite,
    RuntimeReadinessCheck,
    StageHandoffDecision,
    ValidationFinding,
    WorkflowRun,
    WorkflowStageState,
    native_invocation,
)


def test_workflow_run_round_trips_structured_state() -> None:
    run = WorkflowRun(runId="wf-1", useCaseAlias="login", stageStates=[WorkflowStageState(stage="understand", status="completed")])
    data = run.to_dict()
    assert data["schemaVersion"] == "verifysignal-spec-workflow-run/v1"
    assert WorkflowRun.from_dict(data).stageStates[0].status == "completed"


def test_artifact_plan_requires_single_run_request_reference() -> None:
    plan = ArtifactPlan(useCaseAlias="login", runRequest=".verifysignal/run-requests/login.yaml", mainSkill=".verifysignal/skills/login.browser.md")
    assert plan.to_dict()["runRequest"] == ".verifysignal/run-requests/login.yaml"
    assert native_invocation("plan") == "/verifysignal-plan"
    assert native_invocation("plan", integration="codex") == "$verifysignal-plan"
    assert native_invocation("plan", integration="claude") == "/verifysignal-plan"


def test_browser_runtime_readiness_models_round_trip_without_secret_values() -> None:
    target = BrowserTargetEnvironment(kind="staging-url", locator="https://app.example.test", sourceStage="clarify", resolutionStatus="resolved")
    prerequisite = RuntimePrerequisite(id="target", type="target-environment", required=True, status="resolved", valueRef=target.locator)
    finding = ValidationFinding(
        id="finding-target",
        category="missing-prerequisite",
        severity="blocked",
        sourceStage="validate",
        evidence=["baseUrl was empty"],
        recommendedAction="clarify",
        autoRepairAllowed=False,
    )
    readiness = RuntimeReadinessCheck(
        useCaseAlias="profile-view-unauth",
        targetResolutionStatus="resolved",
        targetReachabilityStatus="reachable",
        requiredPrerequisiteStatus="complete",
        authoringReadinessStatus="passed",
        status="passed",
        findingIds=[finding.id],
    )
    decision = StageHandoffDecision(
        key="browserTargetEnvironment",
        valueSummary=target.locator,
        sourceStage="clarify",
        appliesTo="profile-view-unauth",
    )
    contract = CorePublicContract.compatible(verifysignalVersion="0.1.0")

    assert target.to_dict()["locator"] == "https://app.example.test"
    assert prerequisite.to_dict()["status"] == "resolved"
    assert readiness.to_dict()["fullBrowserFlowExecuted"] is False
    assert decision.to_dict()["status"] == "active"
    assert contract.to_dict()["requiredOperations"][0]["operationName"] == "version"
