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
