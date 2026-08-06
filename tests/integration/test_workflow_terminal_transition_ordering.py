from __future__ import annotations

from pathlib import Path

import pytest

from tests.fixtures.workflows.main_skill_run_coverage import (
    ALIAS,
    create_main_skill_coverage_workspace,
)
from tests.helpers import FAKE_CORE
from verifysignal_spec.commands import run as run_command
from verifysignal_spec.commands import validate as validate_command
from verifysignal_spec.commands import workflow as workflow_command
from verifysignal_spec.runtime.models import (
    ManagedRuntimeReadinessResult,
    RuntimeSetupBlocker,
)
from verifysignal_spec.workspace.repository import now_iso
from verifysignal_spec.workflows.engine import create_workflow_run
from verifysignal_spec.workflows.models import WORKFLOW_STAGES, WorkflowRun
from verifysignal_spec.workflows.repository import (
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


def _stage(run: WorkflowRun, name: str):
    return next(stage for stage in run.stageStates if stage.stage == name)


def _project_file_bytes(project: Path) -> dict[str, bytes]:
    root = project / ".verifysignal"
    return {
        str(path.relative_to(project)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file() and not path.is_symlink()
    }
