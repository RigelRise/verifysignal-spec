from __future__ import annotations

from pathlib import Path

import pytest

from verifysignal_spec.workspace import layout
from verifysignal_spec.workspace import repository as workspace_repository
from verifysignal_spec.workspace.models import LastCoreAttempt, RunHistoryEntry
from verifysignal_spec.workspace.repository import (
    clear_last_core_attempt,
    create_default_use_case,
    list_use_cases,
    load_document,
    load_use_case,
    record_run,
    save_document,
    save_last_core_attempt,
    save_use_case,
)
from verifysignal_spec.workspace.validation import validate_workspace


ATTEMPTED_AT = "2026-08-05T00:00:00.000000001Z"
COMPLETED_AT = "2026-08-05T00:00:00.000000002Z"


def test_run_authority_rejects_integer_boolean_impersonation(tmp_path: Path) -> None:
    record = _saved_record(tmp_path)
    document = _authority_document(record.alias, _attempt().to_dict(), None)
    document["lastCoreAttempt"]["sideEffectMayExist"] = 0
    save_document(layout.run_authority_path(tmp_path, record.alias), document)

    with pytest.raises(ValueError, match="side-effect authority"):
        load_use_case(tmp_path, record.alias)


def test_newer_base_projection_than_canonical_authority_fails_closed(
    tmp_path: Path,
) -> None:
    record = _saved_record(tmp_path)
    save_last_core_attempt(tmp_path, record.alias, _attempt())
    record_run(tmp_path, _entry(record.alias))
    clear_last_core_attempt(
        tmp_path,
        record.alias,
        expected_attempted_at=ATTEMPTED_AT,
    )
    use_case_path = layout.use_case_path(tmp_path, record.alias)
    base_document = load_document(use_case_path)
    base_document["lastRun"] = {
        "runId": "newer-old-spec-run",
        "status": "passed",
        "startedAt": "2026-08-05T00:00:00.000000003Z",
        "completedAt": "2026-08-05T00:00:00.000000004Z",
        "postCommitInterpretation": {
            "postCommit": True,
            "sideEffectMayExist": True,
            "sideEffectStatus": "committed-confirmed",
            "rerunRisk": "requires-confirmation",
        },
    }
    save_document(use_case_path, base_document)

    with pytest.raises(ValueError, match="(?i)(newer|conflict|downgrade)"):
        load_use_case(tmp_path, record.alias)


@pytest.mark.parametrize(
    ("extra_key", "extra_value", "message"),
    [
        ("unexpected", "safe-value", "invalid lastRun"),
        ("apiToken", "sk_live_not_for_logs_123456789", "secret"),
    ],
)
def test_run_authority_rejects_unallowlisted_or_secret_last_run_fields(
    tmp_path: Path,
    extra_key: str,
    extra_value: str,
    message: str,
) -> None:
    record = _saved_record(tmp_path)
    last_run = {
        "runId": "real-run",
        "status": "passed",
        "startedAt": ATTEMPTED_AT,
        "completedAt": COMPLETED_AT,
        extra_key: extra_value,
    }
    save_document(
        layout.run_authority_path(tmp_path, record.alias),
        _authority_document(record.alias, None, last_run),
    )

    with pytest.raises(ValueError, match=message):
        load_use_case(tmp_path, record.alias)


def test_workspace_validation_opens_canonical_run_authority(tmp_path: Path) -> None:
    record = _saved_record(tmp_path)
    save_document(
        layout.run_authority_path(tmp_path, record.alias),
        _authority_document(
            record.alias,
            None,
            {
                "runId": "real-run",
                "status": "passed",
                "startedAt": ATTEMPTED_AT,
                "completedAt": COMPLETED_AT,
                "apiToken": "sk_live_not_for_logs_123456789",
            },
        ),
    )

    findings = validate_workspace(tmp_path)

    assert any(
        finding["severity"] == "blocking"
        and finding["code"] == "invalid-record"
        and "secret" in finding["message"].lower()
        for finding in findings
    )


def test_list_uses_canonical_attempt_after_stale_projection_write(
    tmp_path: Path,
) -> None:
    record = _saved_record(tmp_path)
    stale_record = load_use_case(tmp_path, record.alias)
    save_last_core_attempt(tmp_path, record.alias, _attempt())
    save_use_case(tmp_path, stale_record)

    rows, warnings = list_use_cases(tmp_path)

    assert warnings == []
    assert rows[0]["risk"]["rerun"]["outcomeClass"] == "unknown-write"
    assert rows[0]["risk"]["rerun"]["decision"] == "requires-confirmation"


def test_marker_remains_authoritative_when_use_case_projection_write_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = _saved_record(tmp_path)
    original = workspace_repository.save_document_durable

    def fail_projection(path: Path, data: object) -> None:
        if path == layout.use_case_path(tmp_path, record.alias):
            raise OSError("projection write failed")
        original(path, data)

    monkeypatch.setattr(workspace_repository, "save_document_durable", fail_projection)

    with pytest.raises(OSError, match="projection write failed"):
        save_last_core_attempt(tmp_path, record.alias, _attempt())

    assert load_use_case(tmp_path, record.alias).lastCoreAttempt == _attempt()


def test_completed_run_remains_authoritative_when_projection_write_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = _saved_record(tmp_path)
    save_last_core_attempt(tmp_path, record.alias, _attempt())
    original = workspace_repository.save_document_durable

    def fail_projection(path: Path, data: object) -> None:
        if path == layout.use_case_path(tmp_path, record.alias):
            raise OSError("projection write failed")
        original(path, data)

    monkeypatch.setattr(workspace_repository, "save_document_durable", fail_projection)

    with pytest.raises(OSError, match="projection write failed"):
        record_run(tmp_path, _entry(record.alias))

    persisted = load_use_case(tmp_path, record.alias)
    assert persisted.lastCoreAttempt == _attempt()
    assert persisted.lastRun is not None
    assert persisted.lastRun["runId"] == "real-run"


def test_tombstone_remains_authoritative_when_projection_write_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = _saved_record(tmp_path)
    save_last_core_attempt(tmp_path, record.alias, _attempt())
    record_run(tmp_path, _entry(record.alias))
    original = workspace_repository.save_document_durable

    def fail_projection(path: Path, data: object) -> None:
        if path == layout.use_case_path(tmp_path, record.alias):
            raise OSError("projection write failed")
        original(path, data)

    monkeypatch.setattr(workspace_repository, "save_document_durable", fail_projection)

    with pytest.raises(OSError, match="projection write failed"):
        clear_last_core_attempt(
            tmp_path,
            record.alias,
            expected_attempted_at=ATTEMPTED_AT,
        )

    persisted = load_use_case(tmp_path, record.alias)
    assert persisted.lastCoreAttempt is None
    assert persisted.lastRun is not None
    assert persisted.lastRun["runId"] == "real-run"


def _saved_record(tmp_path: Path):
    record = create_default_use_case(tmp_path, "localized-home", "Localized home")
    save_use_case(tmp_path, record)
    return record


def _attempt() -> LastCoreAttempt:
    return LastCoreAttempt(
        attemptedAt=ATTEMPTED_AT,
        operation="run",
        schema=None,
        status="unknown",
        errorCode=None,
        executionState="unknown",
        sideEffectMayExist=True,
    )


def _entry(alias: str) -> RunHistoryEntry:
    return RunHistoryEntry(
        runId="real-run",
        useCaseAlias=alias,
        profile="normal",
        status="passed",
        startedAt=ATTEMPTED_AT,
        completedAt=COMPLETED_AT,
    )


def _authority_document(
    alias: str,
    attempt: dict[str, object] | None,
    last_run: dict[str, object] | None,
) -> dict[str, object]:
    return {
        "schemaVersion": "verifysignal-spec-run-authority/v1",
        "useCaseAlias": alias,
        "lastCoreAttempt": attempt,
        "lastRun": last_run,
    }
