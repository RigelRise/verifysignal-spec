from __future__ import annotations

from verifysignal_spec.workflows.stage_persistence import persist_stage, unresolved_blocking_questions
from verifysignal_spec.workflows.engine import create_workflow_run
from verifysignal_spec.workspace.repository import init_workspace


def test_environment_dependent_clarification_remains_blocking_until_answered(tmp_path) -> None:
    project = tmp_path / "repo"
    project.mkdir()
    init_workspace(project)
    create_workflow_run(
        project,
        "Validate login.",
        alias="login",
        integration="codex",
    )
    persist_stage(
        project,
        "specify",
        alias="login",
        payload={
            "alias": "login",
            "surface": "/login",
            "behavior": "Validate login.",
            "expectedOutcome": "Dashboard.",
            "customSourceReason": "Fixture.",
        },
    )
    persist_stage(
        project,
        "clarify",
        alias="login",
        payload={
            "alias": "login",
            "questions": [
                {
                    "id": "q1",
                    "prompt": "Which seeded user role should be used?",
                    "reason": "Data and permission state change expected behavior.",
                    "affects": "data permissions",
                    "environmentDependent": True,
                }
            ],
            "answers": [
                {
                    "questionId": "browser-target-environment",
                    "answerSummary": "Use https://app.example.test for this workflow.",
                    "confirmationSource": "direct-user",
                }
            ],
            "blockingQuestionsResolved": False,
        },
    )
    assert unresolved_blocking_questions(project, "login")[0]["id"] == "q1"

    persist_stage(
        project,
        "clarify",
        alias="login",
        payload={
            "alias": "login",
            "questions": [
                {
                    "id": "q1",
                    "prompt": "Which seeded user role should be used?",
                    "reason": "Data and permission state change expected behavior.",
                    "affects": "data permissions",
                    "environmentDependent": True,
                }
            ],
            "answers": [{"questionId": "q1", "answerSummary": "Use QA admin credential group."}],
            "blockingQuestionsResolved": True,
        },
    )
    assert unresolved_blocking_questions(project, "login") == []
