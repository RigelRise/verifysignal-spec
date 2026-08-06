from __future__ import annotations

from pathlib import Path

import pytest

from tests.fixtures.workflows.main_skill_run_coverage import (
    ALIAS,
    create_main_skill_coverage_workspace,
)
from tests.fixtures.workflows.entitlement_preflight_recovery import write_active_run_documents
from tests.helpers import FAKE_CORE
from verifysignal_spec.commands import run as run_command
from verifysignal_spec.commands import validate as validate_command
from verifysignal_spec.commands import workflow as workflow_command
from verifysignal_spec.runtime.models import (
    ManagedRuntimeReadinessResult,
    RuntimeSetupBlocker,
)
from verifysignal_spec.workspace import layout
from verifysignal_spec.workspace.repository import (
    load_document,
    load_use_case,
    now_iso,
    save_document,
    save_use_case,
)
from verifysignal_spec.workflows.engine import create_workflow_run
from verifysignal_spec.workflows.models import WORKFLOW_STAGES, WorkflowRun
from verifysignal_spec.workflows.repository import (
    create_stage_states,
    link_workflow_reference,
    load_workflow_run,
    save_workflow_run,
    save_workflow_state,
    state_document,
)


@pytest.mark.parametrize(
    ("command", "current_stage", "protected_ready"),
    [
        ("validate", "tasks", False),
        ("run", "validate", True),
    ],
)
def test_terminal_stage_blocker_is_identical_for_check_and_direct_and_byte_stable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    command: str,
    current_stage: str,
    protected_ready: bool,
) -> None:
    create_main_skill_coverage_workspace(
        tmp_path,
        protected_ready=protected_ready,
    )
    run = create_workflow_run(
        tmp_path,
        "Validate a public profile page.",
        alias=ALIAS,
        integration="codex",
    )
    _place_run_at_stage(tmp_path, run, current_stage)
    calls = {"runtimeResolution": 0}

    def unexpected_runtime(*_args: object, **_kwargs: object) -> object:
        calls["runtimeResolution"] += 1
        raise AssertionError("out-of-order terminal commands must not resolve Core")

    monkeypatch.setattr(run_command, "ensure_core_runtime", unexpected_runtime)
    monkeypatch.setattr(validate_command, "ensure_core_runtime", unexpected_runtime)
    before = _project_file_bytes(tmp_path)

    checked = workflow_command.check(tmp_path, command, alias=ALIAS)
    assert _project_file_bytes(tmp_path) == before

    if command == "validate":
        direct = validate_command.run(
            tmp_path,
            ALIAS,
            runtime_readiness=True,
            core_cmd=str(FAKE_CORE),
        )
    else:
        direct = run_command.run(
            tmp_path,
            ALIAS,
            interactive=False,
            core_cmd=str(FAKE_CORE),
        )

    assert checked["status"] == "blocked"
    assert checked["canProceed"] is False
    assert direct["status"] == "blocked"
    assert checked["blockers"][0] == direct["blockers"][0]
    blocker = direct["blockers"][0]
    assert blocker["code"] == "workflow.stage-out-of-order"
    assert blocker["currentStage"] == current_stage
    assert blocker["requestedStage"] == command
    assert checked["nextCommand"] == blocker["recoveryCommand"]
    assert direct["nextAction"] == blocker["recoveryCommand"]
    assert calls == {"runtimeResolution": 0}
    assert _project_file_bytes(tmp_path) == before


@pytest.mark.parametrize(
    ("authority_kind", "expected_recovery"),
    [
        (
            "unreadable-referenced",
            "verifysignal workflow status wf-future-profile-view-unauth --json",
        ),
        ("ambiguous-newest", "verifysignal workflow list --json"),
    ],
)
@pytest.mark.parametrize("command", ["validate", "run"])
def test_invalid_workflow_authority_blocks_check_and_direct_before_core_without_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    authority_kind: str,
    expected_recovery: str,
    command: str,
) -> None:
    _create_invalid_authority_workspace(tmp_path, authority_kind)
    calls = {"runtimeResolution": 0, "coreAdapter": 0}

    def unexpected_runtime(*_args: object, **_kwargs: object) -> object:
        calls["runtimeResolution"] += 1
        raise AssertionError("invalid workflow authority must not resolve Core")

    def unexpected_core_adapter(*_args: object, **_kwargs: object) -> object:
        calls["coreAdapter"] += 1
        raise AssertionError("invalid workflow authority must not invoke Core")

    for module in (run_command, validate_command):
        monkeypatch.setattr(module, "ensure_core_runtime", unexpected_runtime)
        monkeypatch.setattr(module, "CoreAdapter", unexpected_core_adapter)
    before = _project_file_bytes(tmp_path)

    checked = workflow_command.check(tmp_path, command, alias=ALIAS)
    assert _project_file_bytes(tmp_path) == before

    if command == "validate":
        direct = validate_command.run(
            tmp_path,
            ALIAS,
            runtime_readiness=True,
            core_cmd=str(FAKE_CORE),
        )
    else:
        direct = run_command.run(
            tmp_path,
            ALIAS,
            interactive=False,
            core_cmd=str(FAKE_CORE),
        )

    assert checked["status"] == "blocked"
    assert direct["status"] == "blocked"
    assert checked["blockers"][0] == direct["blockers"][0]
    blocker = direct["blockers"][0]
    assert blocker["code"] == "workflow.authority-invalid"
    assert blocker["currentStage"] == "unknown"
    assert blocker["requestedStage"] == command
    assert blocker["recoveryCommand"] == expected_recovery
    assert checked["nextCommand"] == expected_recovery
    assert direct["nextAction"] == expected_recovery
    assert calls == {"runtimeResolution": 0, "coreAdapter": 0}
    assert _project_file_bytes(tmp_path) == before


def test_blocked_run_preflight_does_not_transition_the_run_stage(
    tmp_path: Path,
) -> None:
    create_main_skill_coverage_workspace(tmp_path, protected_ready=False)
    run = create_workflow_run(
        tmp_path,
        "Validate a public profile page.",
        alias=ALIAS,
        integration="codex",
    )
    run = _place_run_at_stage(tmp_path, run, "run")

    result = run_command.run(
        tmp_path,
        ALIAS,
        interactive=False,
        core_cmd=str(FAKE_CORE),
    )

    assert result["status"] == "blocked"
    unchanged = load_workflow_run(tmp_path, run.runId)
    assert unchanged.currentStage == "run"
    assert unchanged.status == "paused"
    assert _stage(unchanged, "run").status == "pending"
    assert _stage(unchanged, "run").blockers == []


def test_managed_runtime_preflight_block_returns_without_transitioning_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    create_main_skill_coverage_workspace(tmp_path, protected_ready=True)
    run = create_workflow_run(
        tmp_path,
        "Validate a public profile page.",
        alias=ALIAS,
        integration="codex",
    )
    run = _place_run_at_stage(tmp_path, run, "run")
    runtime = ManagedRuntimeReadinessResult.blocked(
        RuntimeSetupBlocker(
            code="runtime.setup-unavailable",
            message="Managed runtime setup is temporarily unavailable.",
        )
    )
    monkeypatch.setattr(
        run_command,
        "ensure_core_runtime",
        lambda *_args, **_kwargs: runtime,
    )

    result = run_command.run(
        tmp_path,
        ALIAS,
        interactive=False,
        core_cmd=str(FAKE_CORE),
    )

    assert result["status"] == "blocked"
    assert result["blockers"][0]["code"] == "runtime.setup-unavailable"
    unchanged = load_workflow_run(tmp_path, run.runId)
    assert unchanged.currentStage == "run"
    assert unchanged.status == "paused"
    assert _stage(unchanged, "run").status == "pending"
    assert _stage(unchanged, "run").blockers == []


def _create_invalid_authority_workspace(project: Path, authority_kind: str) -> None:
    create_main_skill_coverage_workspace(project, protected_ready=True)
    record = load_use_case(project, ALIAS)
    record.workflow = {
        "workflowDir": f".verifysignal/workflows/use-cases/{ALIAS}",
        "currentStage": "run",
        "workflowStatus": "paused",
    }
    save_document(
        layout.workflow_state_path(project, ALIAS),
        {
            "schemaVersion": "verifysignal-spec-workflow-state/v1",
            "alias": ALIAS,
            "currentStage": "run",
            "status": "paused",
            "stageStates": [],
        },
    )

    if authority_kind == "unreadable-referenced":
        run_id = "wf-future-profile-view-unauth"
        record.workflow["lastWorkflowRunId"] = run_id
        save_use_case(project, record)
        save_document(
            layout.workflow_run_path(project, run_id),
            {
                "schemaVersion": "verifysignal-spec-workflow-run/v2",
                "runId": run_id,
                "useCaseAlias": ALIAS,
                "status": "paused",
                "currentStage": "validate",
            },
        )
        return

    if authority_kind != "ambiguous-newest":
        raise ValueError(f"Unknown invalid-authority fixture: {authority_kind}")
    save_use_case(project, record)
    for run_id in ("wf-equal-profile-a", "wf-equal-profile-b"):
        stage_states = create_stage_states(project, ALIAS)
        for state in stage_states[: WORKFLOW_STAGES.index("tasks")]:
            state.status = "completed"
        save_workflow_run(
            project,
            WorkflowRun(
                runId=run_id,
                useCaseAlias=ALIAS,
                status="paused",
                currentStage="tasks",
                stageStates=stage_states,
            ),
        )
        path = layout.workflow_run_path(project, run_id)
        document = load_document(path)
        document["updatedAt"] = "2026-08-05T00:00:00Z"
        save_document(path, document)


def _place_run_at_stage(
    project: Path,
    run: WorkflowRun,
    current_stage: str,
) -> WorkflowRun:
    if current_stage == "run":
        write_active_run_documents(project, run.useCaseAlias)
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


def _stage(run: WorkflowRun, name: str):
    return next(stage for stage in run.stageStates if stage.stage == name)


def _project_file_bytes(project: Path) -> dict[str, bytes]:
    root = project / ".verifysignal"
    return {
        str(path.relative_to(project)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file() and not path.is_symlink()
    }
