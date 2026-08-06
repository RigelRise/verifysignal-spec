from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from verifysignal_spec.workspace import layout
from verifysignal_spec.workspace import repository as workspace_repository
from verifysignal_spec.workspace.models import RunHistoryEntry
from verifysignal_spec.workspace.path_safety import (
    ensure_no_casefold_sibling_collision,
)
from verifysignal_spec.workspace.repository import (
    create_default_use_case,
    load_use_case,
    record_run,
    save_use_case,
)


STARTED_AT = "2026-08-05T00:00:00.000000001Z"
COMPLETED_AT = "2026-08-05T00:00:00.000000002Z"
UPPERCASE_RUN_ID = "run-20260805T010203Z"


def _simulate_directory_entries(
    monkeypatch: pytest.MonkeyPatch,
    directory: Path,
    names: list[str],
) -> None:
    original_iterdir = Path.iterdir

    def simulated_iterdir(path: Path) -> Iterator[Path]:
        if path == directory:
            return iter(path / name for name in names)
        return original_iterdir(path)

    monkeypatch.setattr(Path, "iterdir", simulated_iterdir)


def _saved_record(project: Path):
    record = create_default_use_case(project, "localized-home", "Localized home")
    save_use_case(project, record)
    return record


def _entry(alias: str, run_id: str = UPPERCASE_RUN_ID) -> RunHistoryEntry:
    return RunHistoryEntry(
        runId=run_id,
        useCaseAlias=alias,
        profile="normal",
        status="passed",
        startedAt=STARTED_AT,
        completedAt=COMPLETED_AT,
    )


def test_casefold_sibling_collision_is_detected_without_host_filesystem_support(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    directory = tmp_path / "history"
    directory.mkdir()
    target = directory / "Run-A.yaml"
    _simulate_directory_entries(
        monkeypatch,
        directory,
        ["Run-A.yaml", "run-a.yaml"],
    )

    with pytest.raises(
        ValueError,
        match=r"(?i)(case|collision|ambiguous|portable)",
    ):
        ensure_no_casefold_sibling_collision(
            target,
            authority="RunHistory authority",
        )


def test_casefold_sibling_check_fails_closed_when_parent_scan_is_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    directory = tmp_path / "history"
    directory.mkdir()
    original_iterdir = Path.iterdir

    def unavailable_iterdir(path: Path) -> Iterator[Path]:
        if path == directory:
            raise PermissionError("simulated denied directory scan")
        return original_iterdir(path)

    monkeypatch.setattr(Path, "iterdir", unavailable_iterdir)

    with pytest.raises(ValueError, match=r"(?i)(verified|safely|authority)"):
        ensure_no_casefold_sibling_collision(
            directory / "Run-A.yaml",
            authority="RunHistory authority",
        )


def test_unique_uppercase_run_history_id_remains_supported(tmp_path: Path) -> None:
    record = _saved_record(tmp_path)
    entry = _entry(record.alias)

    record_run(tmp_path, entry)

    assert layout.run_history_path(tmp_path, record.alias, entry.runId).is_file()
    assert load_use_case(tmp_path, record.alias).lastRun["runId"] == entry.runId


def test_run_history_write_rejects_simulated_casefold_collision_before_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = _saved_record(tmp_path)
    history_dir = layout.workspace_root(tmp_path) / layout.RUNS_DIR / record.alias
    history_dir.mkdir(parents=True)
    _simulate_directory_entries(
        monkeypatch,
        history_dir,
        [f"{UPPERCASE_RUN_ID.casefold()}.yaml"],
    )
    use_case_path = layout.use_case_path(tmp_path, record.alias)
    base_before = use_case_path.read_bytes()

    with pytest.raises(
        ValueError,
        match=r"(?i)(case|collision|ambiguous|portable)",
    ):
        record_run(tmp_path, _entry(record.alias))

    assert use_case_path.read_bytes() == base_before
    assert not layout.run_authority_path(tmp_path, record.alias).exists()
    assert not layout.run_history_path(
        tmp_path,
        record.alias,
        UPPERCASE_RUN_ID,
    ).exists()


def test_run_history_read_rejects_simulated_casefold_ambiguity_before_selection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    alias = "localized-home"
    history_dir = layout.workspace_root(tmp_path) / layout.RUNS_DIR / alias
    history_dir.mkdir(parents=True)
    _simulate_directory_entries(
        monkeypatch,
        history_dir,
        [f"{UPPERCASE_RUN_ID}.yaml", f"{UPPERCASE_RUN_ID.casefold()}.yaml"],
    )

    with pytest.raises(
        ValueError,
        match=r"(?i)(case|collision|ambiguous|portable)",
    ):
        workspace_repository._load_run_history_documents(tmp_path, alias)
