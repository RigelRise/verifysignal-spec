from __future__ import annotations

from verifysignal_spec.workspace.repository import init_workspace
from verifysignal_spec.workspace.repository import load_use_case
from verifysignal_spec.workflows.engine import create_workflow_run, generate_tasks, plan_artifacts, specify
from verifysignal_spec.workflows.prerequisites import check_prerequisites
from verifysignal_spec.workflows.stage_persistence import persist_stage
from tests.fixtures.workflows.prerequisites import create_current_understanding_workspace


def test_clarify_missing_spec_points_to_specify(tmp_path) -> None:
    init_workspace(tmp_path)
    create_workflow_run(tmp_path, "Validate login.", alias="login", integration="codex")
    result = check_prerequisites(tmp_path, "clarify", alias="login")
    assert result["status"] == "missing"
    assert result["nextCommand"] == "/verifysignal-specify login"


def test_plan_missing_spec_points_to_specify(tmp_path) -> None:
    init_workspace(tmp_path)
    create_workflow_run(tmp_path, "Validate login.", alias="login", integration="codex")
    result = check_prerequisites(tmp_path, "plan", alias="login")
    assert result["status"] == "missing"
    assert result["nextCommand"] == "/verifysignal-specify login"


def test_tasks_missing_plan_points_to_plan(tmp_path) -> None:
    init_workspace(tmp_path)
    create_workflow_run(tmp_path, "Validate login.", alias="login", integration="codex")
    specify(tmp_path, "login", "Validate login.")
    result = check_prerequisites(tmp_path, "tasks", alias="login")
    assert result["status"] == "missing"
    assert result["nextCommand"] == "/verifysignal-plan login"


def test_implement_missing_tasks_points_to_tasks(tmp_path) -> None:
    init_workspace(tmp_path)
    create_workflow_run(tmp_path, "Validate login.", alias="login", integration="codex")
    specify(tmp_path, "login", "Validate login.")
    plan_artifacts(tmp_path, "login")
    result = check_prerequisites(tmp_path, "implement", alias="login")
    assert result["status"] == "missing"
    assert result["nextCommand"] == "/verifysignal-tasks login"


def test_validate_missing_generated_artifacts_points_to_implement(tmp_path) -> None:
    init_workspace(tmp_path)
    create_workflow_run(tmp_path, "Validate login.", alias="login", integration="codex")
    specify(tmp_path, "login", "Validate login.")
    plan_artifacts(tmp_path, "login")
    generate_tasks(tmp_path, "login")
    result = check_prerequisites(tmp_path, "validate", alias="login")
    assert result["status"] == "missing"
    assert result["nextCommand"] == "/verifysignal-implement login"


def test_run_missing_plan_is_an_explicit_blocker_with_recovery(
    tmp_path,
) -> None:
    create_current_understanding_workspace(tmp_path)
    create_workflow_run(
        tmp_path,
        "Validate a public project.",
        alias="public-project-discovery",
        integration="codex",
    )
    specify(
        tmp_path,
        "public-project-discovery",
        "Validate a public project.",
    )

    result = check_prerequisites(
        tmp_path,
        "run",
        alias="public-project-discovery",
    )

    assert result["status"] == "missing"
    assert result["canProceed"] is False
    assert result["missingArtifacts"] == [
        (
            ".verifysignal/workflows/use-cases/"
            "public-project-discovery/plan.md"
        ),
        (
            ".verifysignal/workflows/use-cases/"
            "public-project-discovery/plan.yaml"
        ),
    ]
    assert result["blockers"] == [
        {
            "code": "workflow.prerequisite-missing",
            "severity": "blocker",
            "category": "workflow",
            "message": (
                "The run stage cannot proceed because required workflow "
                "artifacts are missing."
            ),
            "missingArtifacts": result["missingArtifacts"],
            "recoveryCommand": "/verifysignal-plan public-project-discovery",
        }
    ]


def test_browser_target_question_blocks_planning_before_executable_artifacts(tmp_path) -> None:
    create_current_understanding_workspace(tmp_path)
    result = persist_stage(
        tmp_path,
        "specify",
        alias="profile-view-unauth",
        payload={
            "alias": "profile-view-unauth",
            "surface": "/profile/:id/overview",
            "behavior": "Validate public profile rendering.",
            "expectedOutcome": "Profile renders.",
            "customSourceReason": "Browser target prerequisite fixture.",
        },
    )
    assert result["status"] == "persisted"

    record = load_use_case(tmp_path, "profile-view-unauth")
    assert any(question.affects == "runtimeInputs.baseUrl" for question in record.authoringQuestions)

    blocked = check_prerequisites(tmp_path, "plan", alias="profile-view-unauth")
    assert blocked["status"] == "blocked"
    assert blocked["nextCommand"] == "/verifysignal-clarify profile-view-unauth"
    assert blocked["blockers"][0]["code"] == (
        "clarification.target-environment-confirmation-required"
    )
