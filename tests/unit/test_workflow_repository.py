from __future__ import annotations

from pathlib import Path

from tests.fixtures.workflows.guardrails import stage_payload
from verifysignal_spec.workspace.models import AuthoringQuestion
from verifysignal_spec.workspace.repository import (
    create_default_use_case,
    init_workspace,
    load_use_case,
    now_iso,
    save_use_case,
)
from verifysignal_spec.workflows.models import WorkflowRun
from verifysignal_spec.workflows.repository import (
    create_stage_states,
    link_workflow_reference,
    list_workflow_runs,
    load_workflow_run,
    load_workflow_state,
    save_workflow_run,
    save_workflow_state,
    state_document,
    workflow_dir_rel,
)
from verifysignal_spec.workflows.stage_documents import write_specification
from verifysignal_spec.workflows.stage_persistence import persist_stage
from verifysignal_spec.workflows.stages import initialize_understanding


ALIAS = "login"
TARGET_URL = "https://app.example.test/login"


def test_workflow_run_persists_under_workspace(tmp_path) -> None:
    init_workspace(tmp_path)
    run = WorkflowRun(runId="wf-test", useCaseAlias="login", workflowDir=workflow_dir_rel(tmp_path, "login"))
    save_workflow_run(tmp_path, run)
    loaded = load_workflow_run(tmp_path, "wf-test")
    assert loaded.runId == "wf-test"
    assert loaded.workflowDir == ".verifysignal/workflows/use-cases/login"


def test_next_legacy_workflow_write_lazily_migrates_durable_stage_documents(
    tmp_path: Path,
) -> None:
    _create_legacy_use_case_without_run(tmp_path)
    assert load_workflow_state(tmp_path, ALIAS) == {}
    assert list_workflow_runs(tmp_path) == []

    result = _persist_legacy_specification(tmp_path)

    assert result["status"] == "persisted"
    runs = list_workflow_runs(tmp_path)
    assert len(runs) == 1, (
        "the first mutating write must create exactly one migration WorkflowRun"
    )
    run = runs[0]
    assert run.currentStage == "clarify"
    assert run.status == "paused"
    assert _stage_status(run, "understand") == "completed"
    assert _stage_status(run, "specify") == "completed"
    assert _stage_status(run, "clarify") == "pending"
    _assert_projections_match_run(tmp_path, run)


def test_lazy_workflow_migration_is_idempotent_across_repeated_writes(
    tmp_path: Path,
) -> None:
    _create_legacy_use_case_without_run(tmp_path)

    first = _persist_legacy_specification(tmp_path)
    first_run_id = load_use_case(tmp_path, ALIAS).workflow.get("lastWorkflowRunId")
    second = _persist_legacy_specification(tmp_path)

    assert first["status"] == second["status"] == "persisted"
    assert len(list_workflow_runs(tmp_path)) == 1, (
        "repeated writes must reuse one migration run"
    )
    assert first_run_id is not None
    assert load_use_case(tmp_path, ALIAS).workflow["lastWorkflowRunId"] == first_run_id


def test_lazy_workflow_migration_preserves_direct_target_confirmation(
    tmp_path: Path,
) -> None:
    _create_legacy_use_case_without_run(tmp_path)

    _persist_legacy_specification(tmp_path)

    runs = list_workflow_runs(tmp_path)
    assert len(runs) == 1, (
        "target confirmation must migrate with a real WorkflowRun"
    )
    run = runs[0]
    assert run.targetEnvironmentConfirmation is not None
    assert run.targetEnvironmentConfirmation["url"] == TARGET_URL
    assert run.targetEnvironmentConfirmation["source"] == "direct-user"
    assert run.targetEnvironmentConfirmation["questionId"] == (
        "browser-target-environment"
    )
    workflow = load_use_case(tmp_path, ALIAS).workflow
    assert workflow["stageHandoffDecisions"][0]["valueSummary"] == TARGET_URL


def test_next_mutating_transition_heals_interrupted_projections_from_workflow_run(
    tmp_path: Path,
) -> None:
    init_workspace(tmp_path)
    save_use_case(
        tmp_path,
        create_default_use_case(tmp_path, ALIAS, "Validate login."),
    )
    run = _authoritative_run_at_tasks(tmp_path)
    link_workflow_reference(tmp_path, ALIAS, run, run.status)

    record = load_use_case(tmp_path, ALIAS)
    record.workflow["currentStage"] = "specify"
    record.workflow["workflowStatus"] = "failed"
    save_use_case(tmp_path, record)
    save_workflow_state(
        tmp_path,
        ALIAS,
        state_document(
            tmp_path,
            ALIAS,
            current_stage="understand",
            status="paused",
        ),
    )

    result = persist_stage(
        tmp_path,
        "tasks",
        alias=ALIAS,
        payload=stage_payload(
            "tasks",
            payload={
                "alias": ALIAS,
                "tasks": [
                    {
                        "id": "T001",
                        "description": "Persist the login artifacts.",
                        "artifact": "run-request",
                    }
                ],
                "dependencies": [],
                "parallelizableGroups": [],
            },
        ),
    )

    assert result["status"] == "persisted"
    healed = load_workflow_run(tmp_path, run.runId)
    assert healed.currentStage == "implement"
    assert healed.status == "paused"
    assert _stage_status(healed, "plan") == "completed"
    assert _stage_status(healed, "tasks") == "completed"
    assert healed.targetEnvironmentConfirmation == run.targetEnvironmentConfirmation
    assert len(list_workflow_runs(tmp_path)) == 1
    _assert_projections_match_run(tmp_path, healed)


def _create_legacy_use_case_without_run(project: Path) -> None:
    init_workspace(project)
    record = create_default_use_case(project, ALIAS, "Validate login.")
    record.authoringQuestions = [
        AuthoringQuestion(
            id="browser-target-environment",
            prompt="Which target should this workflow validate?",
            reason="A browser workflow needs an explicit target.",
            status="answered",
            answerSummary=TARGET_URL,
            affects="runtimeInputs.baseUrl",
            requiresConfirmation=True,
            confirmationSource="direct-user",
        )
    ]
    record.workflow = {
        "workflowDir": workflow_dir_rel(project, ALIAS),
        "currentStage": "clarify",
        "workflowStatus": "paused",
        "stageHandoffDecisions": [
            {
                "key": "browserTargetEnvironment",
                "valueSummary": TARGET_URL,
                "sourceStage": "clarify",
                "appliesTo": ALIAS,
                "status": "active",
            }
        ],
    }
    save_use_case(project, record)
    initialize_understanding(project, alias=ALIAS, goal="Validate login.")
    write_specification(project, ALIAS, "Validate login.")


def _persist_legacy_specification(project: Path) -> dict:
    return persist_stage(
        project,
        "specify",
        alias=ALIAS,
        payload=stage_payload(
            "specify",
            payload={
                "alias": ALIAS,
                "surface": "/login",
                "behavior": "Validate login.",
                "expectedOutcome": "Dashboard is visible.",
                "customSourceReason": "Legacy migration fixture.",
            },
        ),
    )


def _authoritative_run_at_tasks(project: Path) -> WorkflowRun:
    run = WorkflowRun(
        runId="wf-interrupted-login",
        useCaseAlias=ALIAS,
        status="paused",
        currentStage="tasks",
        startedAt=now_iso(),
        workflowDir=workflow_dir_rel(project, ALIAS),
        stageStates=create_stage_states(project, ALIAS),
        nextCommand=f"/verifysignal-tasks {ALIAS}",
        targetEnvironmentConfirmation={
            "url": TARGET_URL,
            "source": "direct-user",
            "confirmedAt": "2026-08-05T00:00:00Z",
            "questionId": "browser-target-environment",
        },
    )
    for stage in run.stageStates:
        if stage.stage in {"understand", "specify", "clarify", "plan"}:
            stage.status = "completed"
            stage.completedAt = "2026-08-05T00:00:00Z"
    save_workflow_run(project, run)
    return run


def _stage_status(run: WorkflowRun, name: str) -> str:
    return next(stage.status for stage in run.stageStates if stage.stage == name)


def _assert_projections_match_run(project: Path, run: WorkflowRun) -> None:
    workflow = load_use_case(project, ALIAS).workflow
    state = load_workflow_state(project, ALIAS)
    assert workflow["lastWorkflowRunId"] == run.runId
    assert workflow["currentStage"] == run.currentStage
    assert workflow["workflowStatus"] == run.status
    assert state["currentStage"] == run.currentStage
    assert state["status"] == run.status
    assert state["stageStates"] == [item.to_dict() for item in run.stageStates]
