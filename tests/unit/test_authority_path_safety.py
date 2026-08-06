from __future__ import annotations

from pathlib import Path

import pytest

from verifysignal_spec.workspace import layout
from verifysignal_spec.workspace.repository import (
    create_default_use_case,
    load_use_case,
    save_document,
    save_use_case,
)
from verifysignal_spec.workflows.models import WorkflowRun
from verifysignal_spec.workflows.repository import (
    create_stage_states,
    load_workflow_run,
    save_workflow_run,
)


def _symlink_directory(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target, target_is_directory=True)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"Directory symlinks are unavailable on this host: {exc}")


def _workflow_run(project: Path) -> WorkflowRun:
    timestamp = "2026-08-05T00:00:00.000000001Z"
    return WorkflowRun(
        runId="workflow-run-1",
        useCaseAlias="localized-home",
        status="paused",
        currentStage="understand",
        startedAt=timestamp,
        updatedAt=timestamp,
        stageStates=create_stage_states(project, "localized-home"),
    )


def test_workflow_run_load_rejects_symlinked_runs_ancestor(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    workflows_dir = project / layout.WORKSPACE_DIR / layout.WORKFLOWS_DIR
    workflows_dir.mkdir(parents=True)
    outside = tmp_path / "outside-workflow-runs"
    outside.mkdir()
    run = _workflow_run(project)
    outside_path = outside / f"{run.runId}.yaml"
    save_document(outside_path, run.to_dict())
    outside_before = outside_path.read_bytes()
    _symlink_directory(workflows_dir / layout.WORKFLOW_RUNS_DIR, outside)

    with pytest.raises(
        ValueError,
        match=r"(?i)(symbolic|symlink|outside|project|unsafe|ancestor)",
    ):
        load_workflow_run(project, run.runId)

    assert outside_path.read_bytes() == outside_before


def test_workflow_run_save_rejects_symlinked_runs_ancestor_without_external_write(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    workflows_dir = project / layout.WORKSPACE_DIR / layout.WORKFLOWS_DIR
    workflows_dir.mkdir(parents=True)
    outside = tmp_path / "outside-workflow-runs"
    outside.mkdir()
    _symlink_directory(workflows_dir / layout.WORKFLOW_RUNS_DIR, outside)
    run = _workflow_run(project)
    outside_path = outside / f"{run.runId}.yaml"

    with pytest.raises(
        ValueError,
        match=r"(?i)(symbolic|symlink|outside|project|unsafe|ancestor)",
    ):
        save_workflow_run(project, run)

    assert not outside_path.exists()


def test_use_case_load_rejects_symlinked_use_cases_ancestor(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    workspace_dir = project / layout.WORKSPACE_DIR
    workspace_dir.mkdir(parents=True)
    outside = tmp_path / "outside-use-cases"
    outside.mkdir()
    record = create_default_use_case(project, "localized-home", "Localized home")
    outside_path = outside / f"{record.alias}.yaml"
    save_document(outside_path, record.to_dict())
    outside_before = outside_path.read_bytes()
    _symlink_directory(workspace_dir / layout.USE_CASES_DIR, outside)

    with pytest.raises(
        ValueError,
        match=r"(?i)(symbolic|symlink|outside|project|unsafe|ancestor)",
    ):
        load_use_case(project, record.alias)

    assert outside_path.read_bytes() == outside_before


def test_use_case_save_rejects_symlinked_use_cases_ancestor_without_external_write(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    workspace_dir = project / layout.WORKSPACE_DIR
    workspace_dir.mkdir(parents=True)
    outside = tmp_path / "outside-use-cases"
    outside.mkdir()
    record = create_default_use_case(project, "localized-home", "Localized home")
    outside_path = outside / f"{record.alias}.yaml"
    save_document(outside_path, record.to_dict())
    outside_before = outside_path.read_bytes()
    record.title = "Changed outside the project"
    _symlink_directory(workspace_dir / layout.USE_CASES_DIR, outside)

    with pytest.raises(
        ValueError,
        match=r"(?i)(symbolic|symlink|outside|project|unsafe|ancestor)",
    ):
        save_use_case(project, record)

    assert outside_path.read_bytes() == outside_before
