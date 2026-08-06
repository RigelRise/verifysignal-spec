from __future__ import annotations

import os
from pathlib import Path

import pytest

from verifysignal_spec.workspace import layout
from verifysignal_spec.workspace.models import LastCoreAttempt
from verifysignal_spec.workspace.repository import (
    create_default_use_case,
    load_document,
    save_document,
    save_last_core_attempt,
)
from verifysignal_spec.workflows.migration import apply_migration, migration_plans

from tests.fixtures.workflows.guardrails import create_registry_missing_record_path


def test_missing_record_path_migration_plan_is_recoverable(tmp_path) -> None:
    project = tmp_path / "repo"
    project.mkdir()
    create_registry_missing_record_path(project, "login")
    plans = migration_plans(project)
    assert plans[0].id == "migrate-registry-record-path-login"
    assert not plans[0].destructive


def test_apply_migration_creates_canonical_use_case_record(tmp_path) -> None:
    project = tmp_path / "repo"
    project.mkdir()
    create_registry_missing_record_path(project, "login")
    result = apply_migration(project, "migrate-registry-record-path-login")
    assert result["status"] == "applied"
    assert (project / ".verifysignal/use-cases/login.yaml").exists()


def test_apply_migration_projects_existing_canonical_run_authority(
    tmp_path: Path,
) -> None:
    project = tmp_path / "repo"
    project.mkdir()
    create_registry_missing_record_path(project, "login")
    record = create_default_use_case(project, "login", "Validate login.")
    use_case_path = layout.use_case_path(project, record.alias)
    save_document(use_case_path, record.to_dict())
    attempt = LastCoreAttempt(
        attemptedAt="2026-08-05T00:00:00.000000001Z",
        operation="run",
        status="unknown",
        executionState="unknown",
        sideEffectMayExist=True,
    )
    save_last_core_attempt(project, record.alias, attempt)
    stale_projection = load_document(use_case_path)
    stale_projection["lastCoreAttempt"] = None
    save_document(use_case_path, stale_projection)

    result = apply_migration(
        project,
        "migrate-registry-record-path-login",
    )

    assert result["status"] == "applied"
    assert LastCoreAttempt.from_dict(
        load_document(use_case_path)["lastCoreAttempt"]
    ) == attempt


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink semantics")
def test_apply_migration_rejects_redirected_existing_record_before_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = tmp_path / "repo"
    project.mkdir()
    create_registry_missing_record_path(project, "login")
    use_cases_dir = project / layout.WORKSPACE_DIR / layout.USE_CASES_DIR
    use_cases_dir.rmdir()
    outside = tmp_path / "outside-use-cases"
    outside.mkdir()
    outside_record = outside / "login.yaml"
    save_document(
        outside_record,
        create_default_use_case(project, "login", "Validate login.").to_dict(),
    )
    outside_before = outside_record.read_bytes()
    use_cases_dir.symlink_to(outside, target_is_directory=True)
    redirected_path = layout.use_case_path(project, "login")
    original_read_text = Path.read_text
    redirected_reads: list[Path] = []

    def reject_redirected_read(path: Path, *args: object, **kwargs: object) -> str:
        if path == redirected_path:
            redirected_reads.append(path)
            raise AssertionError("redirected use-case authority was opened")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", reject_redirected_read)

    with pytest.raises(
        ValueError,
        match=r"(?i)(symbolic|symlink|outside|project|unsafe|ancestor)",
    ):
        apply_migration(project, "migrate-registry-record-path-login")

    assert redirected_reads == []
    assert outside_record.read_bytes() == outside_before
