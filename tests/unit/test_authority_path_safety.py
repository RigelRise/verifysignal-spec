from __future__ import annotations

import os
import subprocess
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from verifysignal_spec.workspace import layout
from verifysignal_spec.workspace.path_safety import ensure_unredirected_project_path
from verifysignal_spec.workspace.repository import (
    create_default_use_case,
    load_use_case,
    save_document,
    save_last_core_attempt,
    save_use_case,
)
from verifysignal_spec.workspace.models import LastCoreAttempt
from verifysignal_spec.workflows.engine import create_workflow_run
from verifysignal_spec.workflows.models import WorkflowRun
from verifysignal_spec.workflows.repository import (
    create_stage_states,
    list_workflow_runs,
    load_active_workflow_run,
    load_workflow_run,
    save_workflow_run,
)


def _symlink_directory(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target, target_is_directory=True)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"Directory symlinks are unavailable on this host: {exc}")


@pytest.fixture
def windows_junction() -> Iterator[Callable[[Path, Path], Path]]:
    """Create no-privilege Windows junctions and remove only the junctions."""

    if os.name != "nt":
        pytest.skip("Native Windows junction semantics")
    created: list[Path] = []

    def create(link: Path, target: Path) -> Path:
        completed = subprocess.run(
            ["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(target)],
            check=False,
            capture_output=True,
            text=True,
            errors="replace",
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).strip()
            pytest.fail(
                "Windows junction creation failed; native reparse coverage "
                f"cannot be skipped: {detail}"
            )
        created.append(link)
        is_junction = getattr(link, "is_junction", None)
        if not callable(is_junction) or not is_junction():
            pytest.fail("mklink /J did not produce a detectable Windows junction.")
        return link

    yield create

    for link in reversed(created):
        try:
            os.rmdir(link)
        except FileNotFoundError:
            pass


def _workflow_run(
    project: Path,
    *,
    run_id: str = "workflow-run-1",
) -> WorkflowRun:
    timestamp = "2026-08-05T00:00:00.000000001Z"
    return WorkflowRun(
        runId=run_id,
        useCaseAlias="localized-home",
        status="paused",
        currentStage="understand",
        startedAt=timestamp,
        updatedAt=timestamp,
        stageStates=create_stage_states(project, "localized-home"),
    )


@pytest.mark.skipif(os.name != "nt", reason="Native Windows junction semantics")
def test_windows_junction_ancestor_is_rejected_without_silent_skip(
    tmp_path: Path,
    windows_junction: Callable[[Path, Path], Path],
) -> None:
    project = tmp_path / "project"
    workspace_dir = project / layout.WORKSPACE_DIR
    workspace_dir.mkdir(parents=True)
    outside = tmp_path / "outside-use-cases"
    outside.mkdir()
    junction = windows_junction(workspace_dir / layout.USE_CASES_DIR, outside)

    with pytest.raises(ValueError, match=r"(?i)(reparse|junction|unsafe)"):
        ensure_unredirected_project_path(
            project,
            junction / "localized-home.yaml",
            authority="Use-case authority",
        )

    assert list(outside.iterdir()) == []


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


def test_unique_uppercase_workflow_run_id_remains_supported(tmp_path: Path) -> None:
    project = tmp_path / "project"
    run = _workflow_run(project, run_id="Run-A")

    save_workflow_run(project, run)

    assert load_workflow_run(project, run.runId).runId == "Run-A"


def test_workflow_run_save_rejects_casefold_filename_collision_before_overwrite(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    original = _workflow_run(project, run_id="Run-A")
    save_workflow_run(project, original)
    original_path = layout.workflow_run_path(project, original.runId)
    original_bytes = original_path.read_bytes()

    with pytest.raises(ValueError, match=r"(?i)(case|collision|ambiguous|portable)"):
        save_workflow_run(project, _workflow_run(project, run_id="run-a"))

    assert original_path.read_bytes() == original_bytes
    assert [path.name for path in layout.workflow_runs_dir(project).iterdir()] == [
        "Run-A.yaml"
    ]


def test_workflow_run_selection_rejects_casefold_filename_collision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = tmp_path / "project"
    alias = "localized-home"
    record = create_default_use_case(project, alias, "Localized home")
    save_use_case(project, record)
    for run_id in ("Run-A", "run-a"):
        run = _workflow_run(project, run_id=run_id)
        save_document(layout.workflow_run_path(project, run_id), run.to_dict())
    candidates = [
        path.name
        for path in layout.workflow_runs_dir(project).iterdir()
        if path.name.casefold() in {"run-a.yaml"}
    ]
    if len(candidates) != 2:
        directory = layout.workflow_runs_dir(project)
        original_iterdir = Path.iterdir

        def simulated_case_sensitive_siblings(path: Path):
            if path == directory:
                return iter([directory / "Run-A.yaml", directory / "run-a.yaml"])
            return original_iterdir(path)

        monkeypatch.setattr(Path, "iterdir", simulated_case_sensitive_siblings)

    with pytest.raises(ValueError, match=r"(?i)(case|collision|ambiguous|portable)"):
        load_active_workflow_run(project, alias)


def test_workflow_run_repository_rejects_noncanonical_yaml_extension(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = tmp_path / "project"
    run = _workflow_run(project, run_id="Run-A")
    noncanonical = layout.workflow_runs_dir(project) / "Run-A.YAML"
    save_document(noncanonical, run.to_dict())
    before = noncanonical.read_bytes()
    directory = layout.workflow_runs_dir(project)
    original_glob = Path.glob

    def posix_case_sensitive_glob(path: Path, pattern: str):
        if path == directory and pattern == "*.yaml":
            return iter([])
        return original_glob(path, pattern)

    monkeypatch.setattr(Path, "glob", posix_case_sensitive_glob)

    with pytest.raises(ValueError, match=r"(?i)(case|collision|extension|portable)"):
        list_workflow_runs(project)
    with pytest.raises(ValueError, match=r"(?i)(case|collision|extension|portable)"):
        load_workflow_run(project, run.runId)
    with pytest.raises(ValueError, match=r"(?i)(case|collision|extension|portable)"):
        save_workflow_run(project, run)

    assert noncanonical.read_bytes() == before


def test_workflow_creation_rejects_redirected_workflows_ancestor_without_external_writes(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    workspace_dir = project / layout.WORKSPACE_DIR
    workspace_dir.mkdir(parents=True)
    outside = tmp_path / "outside-workflows"
    outside.mkdir()
    _symlink_directory(workspace_dir / layout.WORKFLOWS_DIR, outside)

    with pytest.raises(
        ValueError,
        match=r"(?i)(symbolic|symlink|outside|project|unsafe|ancestor)",
    ):
        create_workflow_run(
            project,
            "Validate the localized home page.",
            alias="localized-home",
            integration="codex",
        )

    assert list(outside.iterdir()) == []


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


def test_use_case_document_alias_must_match_requested_filename_without_wrong_sidecar(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    record = create_default_use_case(project, "localized-home", "Localized home")
    save_use_case(project, record)
    document = record.to_dict()
    document["alias"] = "different-alias"
    save_document(layout.use_case_path(project, record.alias), document)
    attempt = LastCoreAttempt(
        attemptedAt="2026-08-05T00:00:00.000000001Z",
        operation="run",
        status="unknown",
        executionState="unknown",
        sideEffectMayExist=True,
    )

    with pytest.raises(ValueError, match=r"(?i)(alias|identity|filename)"):
        load_use_case(project, record.alias)
    with pytest.raises(ValueError, match=r"(?i)(alias|identity|filename)"):
        save_last_core_attempt(project, record.alias, attempt)

    assert not layout.run_authority_path(project, record.alias).exists()
    assert not layout.run_authority_path(project, "different-alias").exists()


@pytest.mark.parametrize(
    "alias",
    [
        "con",
        "prn.txt",
        "portable.",
        "line-break\n",
        "control\x1fcharacter",
    ],
)
def test_aliases_reject_non_portable_windows_and_control_names(alias: str) -> None:
    with pytest.raises(ValueError):
        layout.ensure_path_safe_alias(alias)


@pytest.mark.parametrize(
    "run_id",
    [
        "CON",
        "com1.result",
        "portable.",
        "line-break\n",
        "control\x1fcharacter",
    ],
)
def test_run_ids_reject_non_portable_windows_and_control_names(run_id: str) -> None:
    with pytest.raises(ValueError):
        layout.ensure_path_safe_run_id(run_id)


@pytest.mark.parametrize(
    "generated_id",
    [
        "nul",
        "lpt1.result",
        "portable.",
        "line-break\n",
        "control\x1fcharacter",
    ],
)
def test_generated_ids_reject_non_portable_windows_and_control_names(
    generated_id: str,
) -> None:
    with pytest.raises(ValueError):
        layout.ensure_path_safe_id(generated_id)
