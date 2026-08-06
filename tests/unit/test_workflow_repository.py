from __future__ import annotations

from pathlib import Path
import time

import pytest

from tests.fixtures.workflows.entitlement_preflight_recovery import (
    save_protected_ready_snapshot,
)
from tests.fixtures.workflows.guardrails import stage_payload
from verifysignal_spec.workspace import layout
from verifysignal_spec.workspace.models import ArtifactReference, AuthoringQuestion
from verifysignal_spec.workspace.repository import (
    create_default_use_case,
    init_workspace,
    load_document,
    load_use_case,
    now_iso,
    save_document,
    save_use_case,
)
from verifysignal_spec.workflows.models import WorkflowRun
from verifysignal_spec.workflows import repository as workflow_repository
from verifysignal_spec.workflows.repository import (
    create_stage_states,
    link_workflow_reference,
    list_workflow_runs,
    load_active_workflow_run,
    load_workflow_run,
    load_workflow_state,
    save_workflow_run,
    save_workflow_state,
    state_document,
    workflow_dir_rel,
)
from verifysignal_spec.workflows.stage_persistence import persist_stage
from verifysignal_spec.workflows.stages import initialize_understanding
from verifysignal_spec.workflows.transitions import (
    managed_workflow_stage_decision,
    transition_workflow,
)


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

    assert first["status"] == "persisted"
    assert second["status"] == "invalid"
    assert second["blockers"][0]["code"] == "payload.invalid"
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


def test_fresh_specification_persistence_bootstraps_one_authoritative_run(
    tmp_path: Path,
) -> None:
    init_workspace(tmp_path)

    result = _persist_legacy_specification(tmp_path)

    assert result["status"] == "persisted"
    runs = list_workflow_runs(tmp_path)
    assert len(runs) == 1
    assert runs[0].currentStage == "clarify"
    _assert_projections_match_run(tmp_path, runs[0])


def test_legacy_executable_references_infer_implement_before_one_lazy_migration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.fixtures.workflows.real_run_guardrails import (
        coherent_profile_skill,
        create_real_run_guardrail_workspace,
        run_request_payload,
    )
    from tests.helpers import FAKE_CORE

    monkeypatch.setenv("VERIFYSIGNAL_CORE_CMD", str(FAKE_CORE))
    create_real_run_guardrail_workspace(tmp_path)
    init_workspace(tmp_path, core_cmd=str(FAKE_CORE))

    result = persist_stage(
        tmp_path,
        "implement",
        alias="profile-view-unauth",
        payload={
            "runRequest": run_request_payload(),
            "skills": [coherent_profile_skill()],
            "runtimeInputs": [
                {"name": "baseUrl", "default": "https://app.example.test"}
            ],
        },
    )

    assert result["status"] == "persisted"
    runs = list_workflow_runs(tmp_path)
    assert len(runs) == 1
    assert runs[0].currentStage == "validate"
    for stage in ("understand", "specify", "clarify", "plan", "tasks", "implement"):
        assert _stage_status(runs[0], stage) == "completed"


def test_dangling_legacy_executable_reference_does_not_infer_implement(
    tmp_path: Path,
) -> None:
    _create_reference_only_legacy_use_case(
        tmp_path,
        ".verifysignal/run-requests/login.yaml",
    )

    result = transition_workflow(
        tmp_path,
        ALIAS,
        stage="understand",
        outcome="completed",
    )

    assert result.migrated is True
    assert result.run.currentStage == "specify"
    assert _stage_status(result.run, "understand") == "completed"
    for stage in ("specify", "clarify", "plan", "tasks", "implement"):
        assert _stage_status(result.run, stage) == "pending"


def test_noncanonical_authored_stage_document_does_not_advance_migration(
    tmp_path: Path,
) -> None:
    _create_reference_only_legacy_use_case(
        tmp_path,
        ".verifysignal/run-requests/login.yaml",
    )
    noncanonical = layout.workflow_stage_document_path(tmp_path, ALIAS, "tasks")
    noncanonical.parent.mkdir(parents=True, exist_ok=True)
    noncanonical.write_text(
        "# Unrelated Notes\n\nThis is not an authored task-set document.\n",
        encoding="utf-8",
    )

    result = transition_workflow(
        tmp_path,
        ALIAS,
        stage="understand",
        outcome="completed",
    )

    assert result.migrated is True
    assert result.run.currentStage == "specify"
    assert _stage_status(result.run, "understand") == "completed"
    for stage in ("specify", "clarify", "plan", "tasks", "implement"):
        assert _stage_status(result.run, stage) == "pending"


def test_symlinked_legacy_executable_reference_does_not_infer_implement(
    tmp_path: Path,
) -> None:
    reference = ".verifysignal/run-requests/login.yaml"
    _create_reference_only_legacy_use_case(tmp_path, reference)
    target = tmp_path / "legacy-request-target.yaml"
    target.write_text("schemaVersion: qa-run-request/v1\n", encoding="utf-8")
    linked_request = tmp_path / reference
    linked_request.symlink_to(target)

    result = transition_workflow(
        tmp_path,
        ALIAS,
        stage="understand",
        outcome="completed",
    )

    assert result.migrated is True
    assert result.run.currentStage == "specify"
    assert _stage_status(result.run, "understand") == "completed"
    for stage in ("specify", "clarify", "plan", "tasks", "implement"):
        assert _stage_status(result.run, stage) == "pending"
    assert linked_request.is_symlink()


def test_lazy_workflow_migration_does_not_synthesize_execution_artifacts(
    tmp_path: Path,
) -> None:
    _create_legacy_use_case_without_run(tmp_path)

    result = _persist_legacy_specification(tmp_path)

    assert result["status"] == "persisted"
    runs = list_workflow_runs(tmp_path)
    assert len(runs) == 1
    migrated = runs[0]
    record = load_use_case(tmp_path, ALIAS)
    assert record.lastRun is None
    assert record.lastCoreAttempt is None
    assert record.repair is None
    assert record.validation == {"status": "unknown"}
    assert migrated.gateDecisions == []
    for stage in ("clarify", "plan", "tasks", "implement", "validate", "run", "repair"):
        assert _stage_status(migrated, stage) == "pending"

    workspace = layout.workspace_root(tmp_path)
    for directory_name in (layout.RUNS_DIR, layout.REPAIRS_DIR):
        assert [
            path.relative_to(workspace).as_posix()
            for path in (workspace / directory_name).rglob("*")
            if path.is_file()
        ] == []
    assert not any(
        part in {"discover", "evidence", "gate-coverage", "gates"}
        for path in workspace.rglob("*")
        if path.is_file()
        for part in path.relative_to(workspace).parts
    )


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


def test_next_transition_recovers_unreferenced_matching_workflow_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    init_workspace(tmp_path)
    save_use_case(
        tmp_path,
        create_default_use_case(tmp_path, ALIAS, "Validate login."),
    )
    monkeypatch.setattr(
        workflow_repository,
        "now_iso",
        lambda: "2026-08-05T00:00:00Z",
    )
    authoritative = _authoritative_run_at_tasks(
        tmp_path,
        run_id="wf-unreferenced-login",
    )
    monkeypatch.setattr(
        workflow_repository,
        "now_iso",
        lambda: "2026-08-05T00:01:00Z",
    )
    save_workflow_run(
        tmp_path,
        WorkflowRun(
            runId="wf-newer-other-alias",
            useCaseAlias="other-alias",
            status="paused",
            currentStage="repair",
            stageStates=create_stage_states(tmp_path, "other-alias"),
        ),
    )

    result = _persist_tasks(tmp_path)

    assert result["status"] == "persisted"
    matching_runs = [
        run for run in list_workflow_runs(tmp_path) if run.useCaseAlias == ALIAS
    ]
    assert [run.runId for run in matching_runs] == [authoritative.runId]
    recovered = load_workflow_run(tmp_path, authoritative.runId)
    assert recovered.currentStage == "implement"
    assert recovered.targetEnvironmentConfirmation == (
        authoritative.targetEnvironmentConfirmation
    )
    _assert_projections_match_run(tmp_path, recovered)


def test_next_transition_prefers_newer_matching_run_over_stale_reference(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    init_workspace(tmp_path)
    save_use_case(
        tmp_path,
        create_default_use_case(tmp_path, ALIAS, "Validate login."),
    )
    monkeypatch.setattr(
        workflow_repository,
        "now_iso",
        lambda: "2026-08-05T00:00:00Z",
    )
    older = _authoritative_run_at_tasks(tmp_path, run_id="wf-older-login")
    link_workflow_reference(tmp_path, ALIAS, older, older.status)
    save_workflow_state(
        tmp_path,
        ALIAS,
        state_document(tmp_path, ALIAS, older),
    )
    monkeypatch.setattr(
        workflow_repository,
        "now_iso",
        lambda: "2026-08-05T00:01:00Z",
    )
    newer = _authoritative_run_at_tasks(tmp_path, run_id="wf-newer-login")

    result = _persist_tasks(tmp_path)

    assert result["status"] == "persisted"
    assert load_workflow_run(tmp_path, older.runId).currentStage == "tasks"
    recovered = load_workflow_run(tmp_path, newer.runId)
    assert recovered.currentStage == "implement"
    assert recovered.targetEnvironmentConfirmation == newer.targetEnvironmentConfirmation
    _assert_projections_match_run(tmp_path, recovered)


def test_out_of_order_transition_fails_without_mutating_workflow_documents(
    tmp_path: Path,
) -> None:
    init_workspace(tmp_path)
    save_use_case(
        tmp_path,
        create_default_use_case(tmp_path, ALIAS, "Validate login."),
    )
    run = _authoritative_run_at_tasks(tmp_path)
    link_workflow_reference(tmp_path, ALIAS, run, run.status)
    save_workflow_state(tmp_path, ALIAS, state_document(tmp_path, ALIAS, run))
    paths = _authoritative_document_paths(tmp_path, run)
    before = {name: path.read_bytes() for name, path in paths.items()}

    with pytest.raises(ValueError, match="current stage"):
        transition_workflow(
            tmp_path,
            ALIAS,
            stage="implement",
            outcome="completed",
        )

    assert {name: path.read_bytes() for name, path in paths.items()} == before


def test_public_out_of_order_persistence_leaves_project_bytes_unchanged(
    tmp_path: Path,
) -> None:
    init_workspace(tmp_path)
    save_use_case(
        tmp_path,
        create_default_use_case(tmp_path, ALIAS, "Validate login."),
    )
    run = _authoritative_run_at_tasks(tmp_path)
    link_workflow_reference(tmp_path, ALIAS, run, run.status)
    save_workflow_state(tmp_path, ALIAS, state_document(tmp_path, ALIAS, run))
    before = _project_file_bytes(tmp_path)

    result = persist_stage(
        tmp_path,
        "specify",
        alias=ALIAS,
        payload=stage_payload(
            "specify",
            payload={
                "alias": ALIAS,
                "surface": "/login",
                "behavior": "Validate login.",
                "expectedOutcome": "Dashboard is visible.",
                "customSourceReason": "Out-of-order fixture.",
            },
        ),
    )

    assert result["status"] == "invalid"
    assert "current stage" in result["blockers"][0]["message"]
    assert _project_file_bytes(tmp_path) == before


def test_workflow_run_writes_use_strict_high_resolution_ordering(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    init_workspace(tmp_path)
    monkeypatch.setattr(
        workflow_repository,
        "now_iso",
        lambda: "2026-08-05T00:00:00Z",
    )
    nanoseconds = iter(
        [
            1_754_352_000_000_000_001,
            1_754_352_000_000_000_002,
        ]
    )
    monkeypatch.setattr(time, "time_ns", lambda: next(nanoseconds))
    first = WorkflowRun(runId="wf-high-resolution-a", useCaseAlias=ALIAS)
    second = WorkflowRun(runId="wf-high-resolution-b", useCaseAlias=ALIAS)

    save_workflow_run(tmp_path, first)
    save_workflow_run(tmp_path, second)

    assert first.updatedAt is not None
    assert second.updatedAt is not None
    assert first.updatedAt < second.updatedAt


def test_equal_timestamp_without_reference_is_rejected_as_ambiguous(
    tmp_path: Path,
) -> None:
    init_workspace(tmp_path)
    save_use_case(
        tmp_path,
        create_default_use_case(tmp_path, ALIAS, "Validate login."),
    )
    save_workflow_run(
        tmp_path,
        WorkflowRun(runId="wf-equal-a", useCaseAlias=ALIAS),
    )
    save_workflow_run(
        tmp_path,
        WorkflowRun(runId="wf-equal-z", useCaseAlias=ALIAS),
    )
    for run_id in ["wf-equal-a", "wf-equal-z"]:
        path = (
            tmp_path
            / ".verifysignal"
            / "workflows"
            / "runs"
            / f"{run_id}.yaml"
        )
        data = load_document(path)
        data["updatedAt"] = "2026-08-05T00:00:00Z"
        save_document(path, data)

    with pytest.raises(ValueError, match="ambiguous"):
        load_active_workflow_run(tmp_path, ALIAS)


def test_unreadable_referenced_workflow_run_fails_closed_before_execution(
    tmp_path: Path,
) -> None:
    init_workspace(tmp_path)
    record = create_default_use_case(tmp_path, ALIAS, "Validate login.")
    record.workflow = {
        "lastWorkflowRunId": "wf-future-login",
        "currentStage": "run",
        "workflowStatus": "paused",
    }
    save_use_case(tmp_path, record)
    save_document(
        layout.workflow_run_path(tmp_path, "wf-future-login"),
        {
            "schemaVersion": "verifysignal-spec-workflow-run/v2",
            "runId": "wf-future-login",
            "useCaseAlias": ALIAS,
            "status": "paused",
            "currentStage": "validate",
        },
    )
    save_protected_ready_snapshot(tmp_path, ALIAS)

    decision = managed_workflow_stage_decision(tmp_path, ALIAS, "run")

    assert decision["managed"] is True
    assert decision["currentStage"] == "unknown"
    assert decision["requestedStage"] == "run"
    assert decision["blocker"]["code"] == "workflow.authority-invalid"
    assert decision["blocker"]["recoveryCommand"] == (
        "verifysignal workflow status wf-future-login --json"
    )


def test_blocked_current_stage_can_be_retried_successfully(tmp_path: Path) -> None:
    init_workspace(tmp_path)
    save_use_case(
        tmp_path,
        create_default_use_case(tmp_path, ALIAS, "Validate login."),
    )
    run = _authoritative_run_at_tasks(tmp_path)
    current_index = next(
        index
        for index, state in enumerate(run.stageStates)
        if state.stage == "clarify"
    )
    for index, state in enumerate(run.stageStates):
        state.status = "completed" if index < current_index else "pending"
        state.completedAt = "2026-08-05T00:00:00Z" if index < current_index else None
        state.blockers = []
    clarify = next(state for state in run.stageStates if state.stage == "clarify")
    clarify.status = "blocked"
    clarify.blockers = [{"code": "clarification.unresolved-blocking"}]
    run.currentStage = "clarify"
    run.nextCommand = f"/verifysignal-clarify {ALIAS}"
    save_workflow_run(tmp_path, run)
    link_workflow_reference(tmp_path, ALIAS, run, run.status)
    save_workflow_state(tmp_path, ALIAS, state_document(tmp_path, ALIAS, run))

    result = transition_workflow(
        tmp_path,
        ALIAS,
        stage="clarify",
        outcome="completed",
    )

    assert result.run.currentStage == "plan"
    assert next(
        state for state in result.run.stageStates if state.stage == "clarify"
    ).blockers == []


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


def _create_reference_only_legacy_use_case(
    project: Path,
    reference_path: str,
) -> None:
    init_workspace(project)
    record = create_default_use_case(project, ALIAS, "Validate login.")
    record.runRequest = ArtifactReference(
        path=reference_path,
        kind="run-request",
        id="request.login",
        version="1.0.0",
    )
    save_use_case(project, record)


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


def _persist_tasks(project: Path) -> dict:
    return persist_stage(
        project,
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


def _authoritative_run_at_tasks(
    project: Path,
    *,
    run_id: str = "wf-interrupted-login",
) -> WorkflowRun:
    run = WorkflowRun(
        runId=run_id,
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


def _authoritative_document_paths(
    project: Path,
    run: WorkflowRun,
) -> dict[str, Path]:
    return {
        "run": (
            project
            / ".verifysignal"
            / "workflows"
            / "runs"
            / f"{run.runId}.yaml"
        ),
        "useCase": project / ".verifysignal" / "use-cases" / f"{ALIAS}.yaml",
        "state": (
            project
            / ".verifysignal"
            / "workflows"
            / "use-cases"
            / ALIAS
            / "state.yaml"
        ),
    }


def _project_file_bytes(project: Path) -> dict[str, bytes]:
    return {
        path.relative_to(project).as_posix(): path.read_bytes()
        for path in sorted(project.rglob("*"))
        if path.is_file()
    }


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
