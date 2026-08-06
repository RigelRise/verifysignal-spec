from __future__ import annotations

from pathlib import Path

import pytest

from tests.fixtures.workflows.guardrails import stage_payload
from tests.fixtures.workflows.main_skill_run_coverage import (
    ALIAS,
    create_main_skill_coverage_workspace,
)
from tests.fixtures.workflows.prerequisites import (
    create_current_understanding_workspace,
)
from tests.helpers import FAKE_CORE
from verifysignal_spec.commands import repair as repair_command
from verifysignal_spec.commands import run as run_command
from verifysignal_spec.commands import validate as validate_command
from verifysignal_spec.workspace.repository import (
    load_use_case,
    now_iso,
    save_use_case,
)
from verifysignal_spec.workflows.engine import (
    create_workflow_run,
    workflow_show,
    workflow_status_for_alias,
)
from verifysignal_spec.workflows.models import WORKFLOW_STAGES, WorkflowRun
from verifysignal_spec.workflows.repository import (
    link_workflow_reference,
    load_workflow_run,
    load_workflow_state,
    save_workflow_run,
    save_workflow_state,
    state_document,
)
from verifysignal_spec.workflows.stage_persistence import persist_stage


def test_authored_stage_transition_updates_run_and_both_projections(
    tmp_path: Path,
) -> None:
    create_current_understanding_workspace(tmp_path)
    run = create_workflow_run(
        tmp_path,
        "Validate login.",
        alias="login",
        integration="codex",
    )
    _place_run_at_stage(tmp_path, run, "specify")

    result = persist_stage(
        tmp_path,
        "specify",
        alias="login",
        payload=stage_payload(
            "specify",
            payload={
                "alias": "login",
                "surface": "/login",
                "behavior": "Validate login.",
                "expectedOutcome": "Dashboard is visible.",
                "customSourceReason": "Workflow authority fixture.",
            },
        ),
    )

    assert result["status"] == "persisted"
    updated = _assert_authoritative_projections(tmp_path, "login", run.runId)
    assert updated.currentStage == "clarify"
    assert updated.status == "paused"
    assert _stage(updated, "understand").status == "completed"
    assert _stage(updated, "specify").status == "completed"
    assert _stage(updated, "specify").documentPath.endswith("/spec.md")
    assert _stage(updated, "clarify").status == "pending"


@pytest.mark.parametrize(
    ("core_mode", "expected_result", "expected_stage_status", "expected_current"),
    [
        ("full-coverage", "passed", "completed", "run"),
        ("current-entitlement-error", "blocked", "blocked", "validate"),
    ],
)
def test_protected_validation_transitions_the_authoritative_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    core_mode: str,
    expected_result: str,
    expected_stage_status: str,
    expected_current: str,
) -> None:
    run = _create_executable_workflow(tmp_path, current_stage="validate")
    monkeypatch.setenv("FAKE_VERIFYSIGNAL_MODE", core_mode)

    result = validate_command.run(
        tmp_path,
        ALIAS,
        runtime_readiness=True,
        core_cmd=str(FAKE_CORE),
    )

    assert result["status"] == expected_result
    updated = _assert_authoritative_projections(tmp_path, ALIAS, run.runId)
    assert updated.currentStage == expected_current
    assert updated.status == "paused"
    assert _stage(updated, "implement").status == "completed"
    assert _stage(updated, "validate").status == expected_stage_status
    if expected_result == "blocked":
        blocker_codes = {
            blocker["code"] for blocker in _stage(updated, "validate").blockers
        }
        assert "entitlement.unverifiable" in blocker_codes


def test_authoring_only_validation_does_not_advance_the_protected_stage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = _create_executable_workflow(tmp_path, current_stage="validate")
    monkeypatch.setenv("FAKE_VERIFYSIGNAL_MODE", "full-coverage")

    result = validate_command.run(
        tmp_path,
        ALIAS,
        runtime_readiness=False,
        core_cmd=str(FAKE_CORE),
    )

    assert result["status"] == "passed"
    assert result["runtimeReadinessStatus"] == "not-run"
    unchanged = load_workflow_run(tmp_path, run.runId)
    assert unchanged.currentStage == "validate"
    assert unchanged.status == "paused"
    assert _stage(unchanged, "validate").status == "pending"


@pytest.mark.parametrize("source_stage", ["run", "repair"])
def test_protected_revalidation_can_recover_from_documented_later_stages(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    source_stage: str,
) -> None:
    run = _create_executable_workflow(tmp_path, current_stage=source_stage)
    run = _seed_stale_later_stage_state(tmp_path, run)
    monkeypatch.setenv("FAKE_VERIFYSIGNAL_MODE", "full-coverage")

    result = validate_command.run(
        tmp_path,
        ALIAS,
        runtime_readiness=True,
        core_cmd=str(FAKE_CORE),
    )

    assert result["status"] == "passed"
    recovered = _assert_authoritative_projections(tmp_path, ALIAS, run.runId)
    assert recovered.currentStage == "run"
    assert recovered.status == "paused"
    assert _stage(recovered, "validate").status == "completed"
    for stage_name in ("run", "repair"):
        stage = _stage(recovered, stage_name)
        assert stage.status == "pending"
        assert stage.startedAt is None
        assert stage.completedAt is None
        assert stage.blockers == []
        assert stage.nextCommand is None


@pytest.mark.parametrize("source_stage", ["run", "repair"])
def test_blocked_protected_revalidation_resets_stale_later_stage_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    source_stage: str,
) -> None:
    run = _create_executable_workflow(tmp_path, current_stage=source_stage)
    run = _seed_stale_later_stage_state(tmp_path, run)
    monkeypatch.setenv("FAKE_VERIFYSIGNAL_MODE", "current-entitlement-error")

    result = validate_command.run(
        tmp_path,
        ALIAS,
        runtime_readiness=True,
        core_cmd=str(FAKE_CORE),
    )

    assert result["status"] == "blocked"
    recovered = _assert_authoritative_projections(tmp_path, ALIAS, run.runId)
    assert recovered.currentStage == "validate"
    assert recovered.status == "paused"
    validate_stage = _stage(recovered, "validate")
    assert validate_stage.status == "blocked"
    assert validate_stage.completedAt is None
    assert {blocker["code"] for blocker in validate_stage.blockers} == {
        "entitlement.unverifiable"
    }
    for stage_name in ("run", "repair"):
        stage = _stage(recovered, stage_name)
        assert stage.status == "pending"
        assert stage.startedAt is None
        assert stage.completedAt is None
        assert stage.blockers == []
        assert stage.nextCommand is None


@pytest.mark.parametrize(
    (
        "core_mode",
        "expected_result",
        "expected_stage_status",
        "expected_current",
        "expected_workflow_status",
    ),
    [
        ("full-coverage", "passed", "completed", "run", "completed"),
        ("failed-with-partial", "failed", "failed", "repair", "paused"),
    ],
)
def test_valid_run_result_transitions_pass_and_fail_as_real_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    core_mode: str,
    expected_result: str,
    expected_stage_status: str,
    expected_current: str,
    expected_workflow_status: str,
) -> None:
    run = _create_executable_workflow(tmp_path, current_stage="validate")
    monkeypatch.setenv("FAKE_VERIFYSIGNAL_MODE", "full-coverage")
    validation = validate_command.run(
        tmp_path,
        ALIAS,
        runtime_readiness=True,
        core_cmd=str(FAKE_CORE),
    )
    assert validation["status"] == "passed"
    run = _place_run_at_stage(
        tmp_path,
        load_workflow_run(tmp_path, run.runId),
        "run",
    )
    monkeypatch.setenv("FAKE_VERIFYSIGNAL_MODE", core_mode)

    result = run_command.run(
        tmp_path,
        ALIAS,
        interactive=False,
        core_cmd=str(FAKE_CORE),
    )

    assert result["status"] == expected_result
    updated = _assert_authoritative_projections(tmp_path, ALIAS, run.runId)
    assert updated.currentStage == expected_current
    assert updated.status == expected_workflow_status
    assert _stage(updated, "validate").status == "completed"
    assert _stage(updated, "run").status == expected_stage_status
    if expected_workflow_status == "completed":
        assert updated.completedAt is not None
    else:
        assert updated.completedAt is None


def test_core_error_keeps_run_blocked_without_claiming_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = _create_executable_workflow(tmp_path, current_stage="validate")
    monkeypatch.setenv("FAKE_VERIFYSIGNAL_MODE", "full-coverage")
    validation = validate_command.run(
        tmp_path,
        ALIAS,
        runtime_readiness=True,
        core_cmd=str(FAKE_CORE),
    )
    assert validation["status"] == "passed"
    run = _place_run_at_stage(
        tmp_path,
        load_workflow_run(tmp_path, run.runId),
        "run",
    )
    monkeypatch.setenv("FAKE_VERIFYSIGNAL_MODE", "current-entitlement-error")

    result = run_command.run(
        tmp_path,
        ALIAS,
        interactive=False,
        core_cmd=str(FAKE_CORE),
    )

    assert result["status"] == "blocked"
    assert result["blockers"][0]["code"] == "entitlement.unverifiable"
    updated = _assert_authoritative_projections(tmp_path, ALIAS, run.runId)
    run_stage = _stage(updated, "run")
    assert updated.currentStage == "run"
    assert updated.status == "paused"
    assert updated.completedAt is None
    assert run_stage.status == "blocked"
    assert run_stage.completedAt is None
    assert {blocker["code"] for blocker in run_stage.blockers} == {
        "entitlement.unverifiable"
    }


def test_applied_repair_advances_the_authoritative_run_to_protected_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = _create_executable_workflow(tmp_path, current_stage="repair")
    record = load_use_case(tmp_path, ALIAS)
    record.validation = {
        "findings": [
            {
                "code": "main-skill-ordering",
                "message": "The planned main skill must lead execution.",
                "artifact": record.runRequest.path,
                "path": "skills",
            }
        ]
    }
    save_use_case(tmp_path, record)
    monkeypatch.setattr(
        repair_command,
        "_apply_safe_artifact_repair",
        lambda *_args, **_kwargs: {
            "changed": [record.runRequest.path],
            "before": {record.runRequest.path: "a" * 64},
            "after": {record.runRequest.path: "b" * 64},
        },
    )
    monkeypatch.setattr(
        repair_command,
        "_revalidate_after_mutation",
        lambda *_args, **_kwargs: {"status": "passed"},
    )

    result = repair_command.run(tmp_path, ALIAS, approve=True)

    assert result["repair"]["approvalStatus"] == "applied"
    updated = _assert_authoritative_projections(tmp_path, ALIAS, run.runId)
    assert updated.currentStage == "validate"
    assert updated.status == "paused"
    assert _stage(updated, "repair").status == "completed"
    for stage_name in ("validate", "run"):
        stage = _stage(updated, stage_name)
        assert stage.status == "pending"
        assert stage.startedAt is None
        assert stage.completedAt is None
        assert stage.blockers == []
        assert stage.nextCommand is None


def test_read_only_status_and_show_render_from_run_without_healing_disk(
    tmp_path: Path,
) -> None:
    run = _create_executable_workflow(tmp_path, current_stage="tasks")
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
            status="failed",
        ),
    )
    use_case_path = tmp_path / ".verifysignal" / "use-cases" / f"{ALIAS}.yaml"
    state_path = (
        tmp_path
        / ".verifysignal"
        / "workflows"
        / "use-cases"
        / ALIAS
        / "state.yaml"
    )
    before = {
        "useCase": use_case_path.read_bytes(),
        "state": state_path.read_bytes(),
    }

    status = workflow_status_for_alias(tmp_path, ALIAS)
    shown = workflow_show(tmp_path, ALIAS)

    assert status["currentStage"] == run.currentStage
    assert status["status"] == run.status
    assert status["state"]["currentStage"] == run.currentStage
    assert status["state"]["stageStates"] == [
        item.to_dict() for item in run.stageStates
    ]
    assert shown["currentStage"] == run.currentStage
    assert shown["status"] == run.status
    assert shown["useCase"]["workflow"]["lastWorkflowRunId"] == run.runId
    assert shown["useCase"]["workflow"]["currentStage"] == run.currentStage
    assert shown["useCase"]["workflow"]["workflowStatus"] == run.status
    assert shown["workflowState"]["stageStates"] == [
        item.to_dict() for item in run.stageStates
    ]
    assert use_case_path.read_bytes() == before["useCase"]
    assert state_path.read_bytes() == before["state"]


def _create_executable_workflow(
    project: Path,
    *,
    current_stage: str,
) -> WorkflowRun:
    create_main_skill_coverage_workspace(project)
    workflow_root = project / ".verifysignal" / "workflows" / "use-cases" / ALIAS
    workflow_root.mkdir(parents=True, exist_ok=True)
    for name in ("spec", "plan", "tasks"):
        (workflow_root / f"{name}.md").write_text(
            f"# {name}\n",
            encoding="utf-8",
        )
        if name != "spec":
            (workflow_root / f"{name}.yaml").write_text("{}\n", encoding="utf-8")
    run = create_workflow_run(
        project,
        "Validate a public profile page.",
        alias=ALIAS,
        integration="codex",
    )
    return _place_run_at_stage(project, run, current_stage)


def _place_run_at_stage(
    project: Path,
    run: WorkflowRun,
    current_stage: str,
) -> WorkflowRun:
    current_index = WORKFLOW_STAGES.index(current_stage)
    completed_at = now_iso()
    for index, stage in enumerate(run.stageStates):
        stage.status = "completed" if index < current_index else "pending"
        stage.completedAt = completed_at if index < current_index else None
        stage.blockers = []
    run.currentStage = current_stage
    run.status = "paused"
    run.completedAt = None
    run.nextCommand = f"/verifysignal-{current_stage} {run.useCaseAlias}"
    save_workflow_run(project, run)
    link_workflow_reference(project, run.useCaseAlias, run, run.status)
    save_workflow_state(
        project,
        run.useCaseAlias,
        state_document(
            project,
            run.useCaseAlias,
            run,
            current_stage=run.currentStage,
            status=run.status,
        ),
    )
    return run


def _seed_stale_later_stage_state(
    project: Path,
    run: WorkflowRun,
) -> WorkflowRun:
    for stage_name in ("run", "repair"):
        stage = _stage(run, stage_name)
        stage.status = "failed"
        stage.startedAt = "2026-08-05T00:00:00Z"
        stage.completedAt = "2026-08-05T00:01:00Z"
        stage.blockers = [{"code": f"stale-{stage_name}-blocker"}]
        stage.nextCommand = f"stale-{stage_name}-command"
    save_workflow_run(project, run)
    link_workflow_reference(project, run.useCaseAlias, run, run.status)
    save_workflow_state(
        project,
        run.useCaseAlias,
        state_document(
            project,
            run.useCaseAlias,
            run,
            current_stage=run.currentStage,
            status=run.status,
        ),
    )
    return run


def _assert_authoritative_projections(
    project: Path,
    alias: str,
    run_id: str,
) -> WorkflowRun:
    run = load_workflow_run(project, run_id)
    workflow = load_use_case(project, alias).workflow
    state = load_workflow_state(project, alias)
    assert workflow["lastWorkflowRunId"] == run.runId
    assert workflow["currentStage"] == run.currentStage
    assert workflow["workflowStatus"] == run.status
    assert state["currentStage"] == run.currentStage
    assert state["status"] == run.status
    assert state["stageStates"] == [item.to_dict() for item in run.stageStates]
    return run


def _stage(run: WorkflowRun, name: str):
    return next(stage for stage in run.stageStates if stage.stage == name)
