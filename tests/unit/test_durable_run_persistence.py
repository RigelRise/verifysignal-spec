from __future__ import annotations

import os
from pathlib import Path
import stat

import pytest

from verifysignal_spec.workspace import layout
from verifysignal_spec.workspace import repository as workspace_repository
from verifysignal_spec.workspace.models import LastCoreAttempt, RunHistoryEntry
from verifysignal_spec.workspace.repository import (
    clear_last_core_attempt,
    create_default_use_case,
    load_use_case,
    record_run,
    save_last_core_attempt,
    save_use_case,
)
from verifysignal_spec.workspace.textio import (
    atomic_write_text_lf,
    durable_atomic_write_text_lf,
)


@pytest.mark.skipif(os.name == "nt", reason="POSIX directory fsync ordering")
def test_durable_atomic_write_fsyncs_file_and_directory_around_replace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "authority.yaml"
    events: list[str] = []
    original_replace = os.replace

    def observe_fsync(descriptor: int) -> None:
        mode = os.fstat(descriptor).st_mode
        events.append("fsync-directory" if stat.S_ISDIR(mode) else "fsync-file")

    def observe_replace(source: str | bytes, destination: str | bytes) -> None:
        events.append("replace")
        original_replace(source, destination)

    monkeypatch.setattr(os, "fsync", observe_fsync)
    monkeypatch.setattr(os, "replace", observe_replace)

    durable_atomic_write_text_lf(target, "authority\n")

    assert target.read_bytes() == b"authority\n"
    assert events == ["fsync-file", "replace", "fsync-directory"]


@pytest.mark.skipif(os.name == "nt", reason="POSIX directory fsync durability")
def test_durable_atomic_write_fsyncs_parent_entry_for_new_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "new-authority-directory" / "authority.yaml"
    directory_descriptors: dict[int, Path] = {}
    synced_directories: list[Path] = []
    original_open = os.open
    original_fsync = os.fsync

    def observe_open(
        path: str | bytes,
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        kwargs = {} if dir_fd is None else {"dir_fd": dir_fd}
        descriptor = original_open(path, flags, mode, **kwargs)
        if dir_fd is None and stat.S_ISDIR(os.fstat(descriptor).st_mode):
            directory_descriptors[descriptor] = Path(os.fsdecode(path)).resolve()
        return descriptor

    def observe_fsync(descriptor: int) -> None:
        directory = directory_descriptors.get(descriptor)
        if directory is not None:
            synced_directories.append(directory)
        original_fsync(descriptor)

    monkeypatch.setattr(os, "open", observe_open)
    monkeypatch.setattr(os, "fsync", observe_fsync)

    durable_atomic_write_text_lf(target, "authority\n")

    assert target.read_bytes() == b"authority\n"
    assert target.parent.resolve() in synced_directories
    assert target.parent.parent.resolve() in synced_directories


def test_attempt_and_real_run_authority_use_durable_document_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = create_default_use_case(tmp_path, "localized-home", "Localized home")
    save_use_case(tmp_path, record)
    durable_paths: list[Path] = []

    def observe_durable_write(path: Path, text: str) -> None:
        durable_paths.append(path)
        atomic_write_text_lf(path, text)

    monkeypatch.setattr(
        workspace_repository,
        "durable_atomic_write_text_lf",
        observe_durable_write,
    )
    monkeypatch.setattr(
        workspace_repository,
        "durable_create_text_lf",
        observe_durable_write,
    )
    attempt = LastCoreAttempt(
        attemptedAt="2026-08-05T00:00:00.000000001Z",
        operation="run",
        schema=None,
        status="unknown",
        errorCode=None,
        executionState="unknown",
        sideEffectMayExist=True,
    )
    save_last_core_attempt(tmp_path, record.alias, attempt)
    entry = RunHistoryEntry(
        runId="real-run",
        useCaseAlias=record.alias,
        profile="normal",
        status="passed",
        startedAt=attempt.attemptedAt,
        completedAt="2026-08-05T00:00:00.000000002Z",
    )
    record_run(tmp_path, entry)
    clear_last_core_attempt(
        tmp_path,
        record.alias,
        expected_attempted_at=attempt.attemptedAt,
    )

    use_case_path = layout.use_case_path(tmp_path, record.alias)
    history_path = layout.run_history_path(tmp_path, record.alias, entry.runId)
    assert durable_paths.count(use_case_path) == 3
    assert history_path in durable_paths


def test_durable_atomic_write_replaces_existing_file(tmp_path: Path) -> None:
    target = tmp_path / "authority.yaml"
    target.write_text("old\n", encoding="utf-8")

    durable_atomic_write_text_lf(target, "new\n")

    assert target.read_bytes() == b"new\n"


def test_stale_use_case_writer_cannot_erase_inflight_run_authority(
    tmp_path: Path,
) -> None:
    record = create_default_use_case(tmp_path, "localized-home", "Localized home")
    save_use_case(tmp_path, record)
    stale_record = load_use_case(tmp_path, record.alias)
    attempt = LastCoreAttempt(
        attemptedAt="2026-08-05T00:00:00.000000001Z",
        operation="run",
        schema=None,
        status="unknown",
        errorCode=None,
        executionState="unknown",
        sideEffectMayExist=True,
    )

    save_last_core_attempt(tmp_path, record.alias, attempt)
    save_use_case(tmp_path, stale_record)

    assert load_use_case(tmp_path, record.alias).lastCoreAttempt == attempt


def test_stale_use_case_writer_cannot_erase_completed_run_authority(
    tmp_path: Path,
) -> None:
    record = create_default_use_case(tmp_path, "localized-home", "Localized home")
    save_use_case(tmp_path, record)
    stale_record = load_use_case(tmp_path, record.alias)
    attempt = LastCoreAttempt(
        attemptedAt="2026-08-05T00:00:00.000000001Z",
        operation="run",
        schema=None,
        status="unknown",
        errorCode=None,
        executionState="unknown",
        sideEffectMayExist=True,
    )
    entry = RunHistoryEntry(
        runId="real-run",
        useCaseAlias=record.alias,
        profile="normal",
        status="passed",
        startedAt=attempt.attemptedAt,
        completedAt="2026-08-05T00:00:00.000000002Z",
    )

    save_last_core_attempt(tmp_path, record.alias, attempt)
    record_run(tmp_path, entry)
    clear_last_core_attempt(
        tmp_path,
        record.alias,
        expected_attempted_at=attempt.attemptedAt,
    )
    save_use_case(tmp_path, stale_record)

    persisted = load_use_case(tmp_path, record.alias)
    assert persisted.lastCoreAttempt is None
    assert persisted.lastRun is not None
    assert persisted.lastRun["runId"] == entry.runId


def test_existing_corrupt_run_authority_fails_closed(tmp_path: Path) -> None:
    record = create_default_use_case(tmp_path, "localized-home", "Localized home")
    save_use_case(tmp_path, record)
    authority_path = layout.run_authority_path(tmp_path, record.alias)
    authority_path.write_text("not: [valid", encoding="utf-8")

    with pytest.raises(ValueError, match="run authority"):
        load_use_case(tmp_path, record.alias)


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink semantics")
def test_existing_symlink_run_authority_fails_closed(tmp_path: Path) -> None:
    record = create_default_use_case(tmp_path, "localized-home", "Localized home")
    save_use_case(tmp_path, record)
    outside = tmp_path / "outside.json"
    outside.write_text("{}\n", encoding="utf-8")
    authority_path = layout.run_authority_path(tmp_path, record.alias)
    authority_path.symlink_to(outside)

    with pytest.raises(ValueError, match="run authority"):
        load_use_case(tmp_path, record.alias)
