from __future__ import annotations

from tests.fixtures.workflows.guardrails import stage_payload
from tests.fixtures.workflows.prerequisites import create_current_understanding_workspace
from verifysignal_spec.workspace.repository import init_workspace, load_use_case
from verifysignal_spec.workflows.engine import create_workflow_run
from verifysignal_spec.workflows.repository import load_workflow_run
from verifysignal_spec.workflows.prerequisites import check_prerequisites
from verifysignal_spec.workflows.stage_persistence import persist_stage
from verifysignal_spec.workflows.transitions import transition_workflow
from verifysignal_spec.commands import probe as probe_command
from verifysignal_spec.commands import run as run_command
from verifysignal_spec.workspace.models import ArtifactReference
from verifysignal_spec.workspace.repository import save_use_case


def _specification(base_url: str) -> dict:
    return stage_payload(
        "specify",
        payload={
            "alias": "create-project",
            "surface": "/projects/new",
            "behavior": "Create a project.",
            "expectedOutcome": "Project page.",
            "customSourceReason": "Structural fixture.",
            "targetEnvironment": {
                "locator": base_url,
                "source": "repository-start-instructions",
            },
        },
    )


def test_inferred_target_is_a_pending_recommendation_not_a_confirmation(tmp_path) -> None:
    init_workspace(tmp_path)
    create_current_understanding_workspace(tmp_path)
    run = create_workflow_run(
        tmp_path,
        "Create a project.",
        alias="create-project",
        integration="codex",
    )

    result = persist_stage(
        tmp_path,
        "specify",
        alias="create-project",
        payload=_specification("http://127.0.0.1:4100"),
    )

    assert result["status"] == "persisted"
    record = load_use_case(tmp_path, "create-project")
    question = next(
        item for item in record.authoringQuestions
        if item.id == "browser-target-environment"
    )
    assert question.status == "pending"
    assert question.requiresConfirmation is True
    assert question.suggestedAnswer == {"baseUrl": "http://127.0.0.1:4100"}
    assert question.suggestionSource == "repository-start-instructions"
    assert load_workflow_run(tmp_path, run.runId).targetEnvironmentConfirmation is None
    assert not record.workflow.get("stageHandoffDecisions")
    readiness = check_prerequisites(tmp_path, "plan", "create-project")
    assert readiness["status"] == "blocked"
    assert readiness["blockers"][0]["code"] == (
        "clarification.target-environment-confirmation-required"
    )


def test_plan_cannot_self_confirm_an_inferred_target(tmp_path) -> None:
    init_workspace(tmp_path)
    create_current_understanding_workspace(tmp_path)
    create_workflow_run(tmp_path, "Create a project.", alias="create-project")
    persist_stage(
        tmp_path,
        "specify",
        alias="create-project",
        payload=_specification("http://127.0.0.1:4100"),
    )
    transition_workflow(
        tmp_path,
        "create-project",
        stage="clarify",
        outcome="completed",
    )

    result = persist_stage(
        tmp_path,
        "plan",
        alias="create-project",
        payload=stage_payload(
            "plan",
            payload={
                "alias": "create-project",
                "targetEnvironment": {"locator": "http://127.0.0.1:4100"},
                "runRequest": ".verifysignal/run-requests/create-project.yaml",
                "reusableSkills": [".verifysignal/skills/create-project.browser.md"],
                "runtimeInputs": [],
            },
        ),
    )

    assert result["status"] == "blocked"
    assert result["blockers"][0]["code"] == (
        "clarification.target-environment-confirmation-required"
    )
    assert load_use_case(tmp_path, "create-project").authoringQuestions[0].status == "pending"


def test_direct_user_confirmation_is_scoped_to_the_current_workflow_run(tmp_path) -> None:
    init_workspace(tmp_path)
    create_current_understanding_workspace(tmp_path)
    first = create_workflow_run(tmp_path, "Create a project.", alias="create-project")
    persist_stage(
        tmp_path,
        "specify",
        alias="create-project",
        payload=_specification("http://127.0.0.1:4100"),
    )

    result = persist_stage(
        tmp_path,
        "clarify",
        alias="create-project",
        payload=stage_payload(
            "clarify",
            payload={
                "alias": "create-project",
                "answers": [
                    {
                        "questionId": "browser-target-environment",
                        "answerSummary": "http://127.0.0.1:4200",
                        "confirmationSource": "direct-user",
                    }
                ],
                "blockingQuestionsResolved": True,
            },
        ),
    )

    assert result["status"] == "persisted"
    first_saved = load_workflow_run(tmp_path, first.runId)
    assert first_saved.targetEnvironmentConfirmation["url"] == "http://127.0.0.1:4200"
    assert first_saved.targetEnvironmentConfirmation["source"] == "direct-user"
    record = load_use_case(tmp_path, "create-project")
    assert record.authoringQuestions[0].status == "answered"
    assert record.workflow["stageHandoffDecisions"][0]["valueSummary"] == (
        "http://127.0.0.1:4200"
    )

    second = create_workflow_run(tmp_path, "Create a project.", alias="create-project")

    second_saved = load_workflow_run(tmp_path, second.runId)
    assert second_saved.targetEnvironmentConfirmation is None
    record = load_use_case(tmp_path, "create-project")
    question = next(
        item for item in record.authoringQuestions
        if item.id == "browser-target-environment"
    )
    assert question.status == "pending"
    assert question.suggestedAnswer == {"baseUrl": "http://127.0.0.1:4200"}


def test_probe_and_run_block_before_core_when_current_workflow_target_is_unconfirmed(
    tmp_path,
    monkeypatch,
) -> None:
    init_workspace(tmp_path)
    create_current_understanding_workspace(tmp_path)
    create_workflow_run(tmp_path, "Create a project.", alias="create-project")
    persist_stage(
        tmp_path,
        "specify",
        alias="create-project",
        payload=_specification("http://127.0.0.1:4100"),
    )
    for stage in ("clarify", "plan", "tasks", "implement", "validate"):
        transition_workflow(
            tmp_path,
            "create-project",
            stage=stage,
            outcome="completed",
            handoff_summary="Canonical unconfirmed-target fixture setup.",
        )
    record = load_use_case(tmp_path, "create-project")
    record.runRequest = ArtifactReference(
        path=".verifysignal/run-requests/create-project.yaml",
        kind="run-request",
    )
    record.mainSkill = ArtifactReference(
        path=".verifysignal/skills/create-project.browser.md",
        kind="skill",
    )
    save_use_case(tmp_path, record)
    request = tmp_path / record.runRequest.path
    skill = tmp_path / record.mainSkill.path

    def forbidden(*_args, **_kwargs):
        raise AssertionError("Core must not resolve before target confirmation")

    monkeypatch.setattr(probe_command, "ensure_core_runtime", forbidden)
    monkeypatch.setattr(run_command, "ensure_core_runtime", forbidden)

    probed = probe_command.run(tmp_path, request, [skill])
    executed = run_command.run(tmp_path, "create-project")

    assert probed["blockers"][0]["code"] == (
        "clarification.target-environment-confirmation-required"
    )
    assert executed["blockers"][0]["code"] == (
        "clarification.target-environment-confirmation-required"
    )
