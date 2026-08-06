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


@pytest.mark.parametrize("side_effect_may_exist", [None, True])
def test_not_started_attempt_requires_explicit_false_side_effect_authority(
    tmp_path: Path,
    side_effect_may_exist: bool | None,
) -> None:
    record = _saved_record(tmp_path)
    attempt = _attempt().to_dict()
    attempt["executionState"] = "not-started"
    attempt["sideEffectMayExist"] = side_effect_may_exist
    save_document(
        layout.run_authority_path(tmp_path, record.alias),
        _authority_document(record.alias, attempt, None),
    )

    with pytest.raises(ValueError, match="(?i)(not-started|side-effect|coherent)"):
        load_use_case(tmp_path, record.alias)


def test_run_authority_rejects_secret_looking_attempt_values(tmp_path: Path) -> None:
    record = _saved_record(tmp_path)
    attempt = _attempt().to_dict()
    attempt["errorCode"] = "Bearer abc123abc123abc123abc123"
    save_document(
        layout.run_authority_path(tmp_path, record.alias),
        _authority_document(record.alias, attempt, None),
    )

    with pytest.raises(ValueError, match="secret"):
        load_use_case(tmp_path, record.alias)


def test_record_run_rejects_nested_secret_before_writing_run_history(
    tmp_path: Path,
) -> None:
    record = _saved_record(tmp_path)
    entry = _entry(record.alias)
    entry.runtimeOutputs = [
        {
            "name": "diagnostic",
            "metadata": {
                "apiToken": "sk_live_not_for_logs_123456789",
            },
        }
    ]
    history_path = layout.run_history_path(
        tmp_path,
        record.alias,
        entry.runId,
    )
    rejection: ValueError | None = None

    try:
        record_run(tmp_path, entry)
    except ValueError as exc:
        rejection = exc

    assert rejection is not None
    assert "secret" in str(rejection).lower()
    assert not history_path.exists()


def test_record_run_rejects_summary_secret_before_writing_run_history(
    tmp_path: Path,
) -> None:
    record = _saved_record(tmp_path)
    entry = _entry(record.alias)
    entry.summary = {
        "diagnostics": {
            "apiToken": "sk_live_not_for_logs_123456789",
        }
    }
    history_path = layout.run_history_path(
        tmp_path,
        record.alias,
        entry.runId,
    )
    rejection: ValueError | None = None

    try:
        record_run(tmp_path, entry)
    except ValueError as exc:
        rejection = exc

    assert rejection is not None
    assert "secret" in str(rejection).lower()
    assert not history_path.exists()


def test_equal_time_matching_run_history_cannot_diverge_from_canonical_risk(
    tmp_path: Path,
) -> None:
    record = _saved_record(tmp_path)
    entry = _entry(record.alias)
    entry.postCommitInterpretation = {
        "postCommit": False,
        "sideEffectMayExist": False,
    }
    save_last_core_attempt(tmp_path, record.alias, _attempt())
    record_run(tmp_path, entry)
    clear_last_core_attempt(
        tmp_path,
        record.alias,
        expected_attempted_at=ATTEMPTED_AT,
    )
    history_path = layout.run_history_path(tmp_path, record.alias, entry.runId)
    history = load_document(history_path)
    history["postCommitInterpretation"] = {
        "postCommit": True,
        "sideEffectMayExist": True,
    }
    save_document(history_path, history)

    with pytest.raises(ValueError, match="(?i)(conflict|diverge|authority)"):
        load_use_case(tmp_path, record.alias)


def test_run_authority_rejects_completion_before_start(tmp_path: Path) -> None:
    record = _saved_record(tmp_path)
    last_run = {
        "runId": "time-reversed-run",
        "status": "passed",
        "startedAt": COMPLETED_AT,
        "completedAt": ATTEMPTED_AT,
    }
    save_document(
        layout.run_authority_path(tmp_path, record.alias),
        _authority_document(record.alias, None, last_run),
    )

    with pytest.raises(ValueError, match="(?i)(timestamp|completion|started)"):
        load_use_case(tmp_path, record.alias)


@pytest.mark.parametrize(
    "timestamp_fields",
    [
        {},
        {"startedAt": "not-a-timestamp"},
    ],
    ids=["missing", "unparseable"],
)
def test_alias_run_history_requires_comparable_timestamp(
    tmp_path: Path,
    timestamp_fields: dict[str, str],
) -> None:
    record = _saved_record(tmp_path)
    save_last_core_attempt(tmp_path, record.alias, _attempt())
    history_path = layout.run_history_path(
        tmp_path,
        record.alias,
        "unorderable-run",
    )
    save_document(
        history_path,
        {
            "runId": "unorderable-run",
            "useCaseAlias": record.alias,
            "status": "passed",
            **timestamp_fields,
        },
    )

    with pytest.raises(ValueError, match="(?i)(timestamp|order|history)"):
        load_use_case(tmp_path, record.alias)


def test_malformed_raw_base_attempt_is_not_silently_tombstoned(
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
    base = load_document(use_case_path)
    base["lastCoreAttempt"] = ["malformed-attempt"]
    save_document(use_case_path, base)

    with pytest.raises(ValueError, match="(?i)(attempt|projection|authority)"):
        load_use_case(tmp_path, record.alias)


def test_first_sidecar_recovers_timestamp_less_legacy_run_from_history(
    tmp_path: Path,
) -> None:
    record = _saved_record(tmp_path)
    record.lastRun = {
        "runId": "legacy-real-run",
        "status": "passed",
        "profile": "normal",
    }
    save_use_case(tmp_path, record)
    history_entry = RunHistoryEntry(
        runId="legacy-real-run",
        useCaseAlias=record.alias,
        profile="normal",
        status="passed",
        startedAt=ATTEMPTED_AT,
        completedAt=COMPLETED_AT,
    )
    save_document(
        layout.run_history_path(tmp_path, record.alias, history_entry.runId),
        history_entry.to_dict(),
    )
    attempt = _attempt()
    attempt.attemptedAt = "2026-08-05T00:00:00.000000003Z"

    save_last_core_attempt(tmp_path, record.alias, attempt)

    recovered = load_use_case(tmp_path, record.alias)
    assert recovered.lastRun is not None
    assert recovered.lastRun["runId"] == history_entry.runId
    assert recovered.lastRun["startedAt"] == ATTEMPTED_AT
    assert recovered.lastRun["completedAt"] == COMPLETED_AT


def test_first_sidecar_accepts_identical_equal_time_legacy_history(
    tmp_path: Path,
) -> None:
    record = _saved_record(tmp_path)
    record.lastRun = {
        "runId": "legacy-equal-run",
        "status": "passed",
        "profile": "normal",
        "startedAt": ATTEMPTED_AT,
        "completedAt": COMPLETED_AT,
    }
    save_use_case(tmp_path, record)
    history_entry = RunHistoryEntry(
        runId="legacy-equal-run",
        useCaseAlias=record.alias,
        profile="normal",
        status="passed",
        startedAt=ATTEMPTED_AT,
        completedAt=COMPLETED_AT,
    )
    save_document(
        layout.run_history_path(tmp_path, record.alias, history_entry.runId),
        history_entry.to_dict(),
    )
    attempt = _attempt()
    attempt.attemptedAt = "2026-08-05T00:00:00.000000003Z"

    save_last_core_attempt(tmp_path, record.alias, attempt)

    recovered = load_use_case(tmp_path, record.alias)
    assert recovered.lastRun is not None
    assert recovered.lastRun["runId"] == history_entry.runId
    assert recovered.lastCoreAttempt == attempt


def test_first_sidecar_recovers_unique_newer_history_over_older_base(
    tmp_path: Path,
) -> None:
    record = _saved_record(tmp_path)
    record.lastRun = {
        "runId": "older-base-run",
        "status": "passed",
        "profile": "normal",
        "startedAt": ATTEMPTED_AT,
        "completedAt": COMPLETED_AT,
    }
    save_use_case(tmp_path, record)
    newer_history = RunHistoryEntry(
        runId="newer-history-run",
        useCaseAlias=record.alias,
        profile="normal",
        status="passed",
        startedAt="2026-08-05T00:00:00.000000003Z",
        completedAt="2026-08-05T00:00:00.000000004Z",
    )
    save_document(
        layout.run_history_path(tmp_path, record.alias, newer_history.runId),
        newer_history.to_dict(),
    )
    attempt = _attempt()
    attempt.attemptedAt = "2026-08-05T00:00:00.000000005Z"

    save_last_core_attempt(tmp_path, record.alias, attempt)

    recovered = load_use_case(tmp_path, record.alias)
    assert recovered.lastRun is not None
    assert recovered.lastRun["runId"] == newer_history.runId
    assert recovered.lastRun["completedAt"] == newer_history.completedAt


def test_first_sidecar_rejects_equal_newest_history_with_different_ids(
    tmp_path: Path,
) -> None:
    record = _saved_record(tmp_path)
    record.lastRun = {
        "runId": "older-base-run",
        "status": "passed",
        "profile": "normal",
        "startedAt": ATTEMPTED_AT,
        "completedAt": COMPLETED_AT,
    }
    save_use_case(tmp_path, record)
    for run_id in ("equal-newest-a", "equal-newest-b"):
        entry = RunHistoryEntry(
            runId=run_id,
            useCaseAlias=record.alias,
            profile="normal",
            status="passed",
            startedAt="2026-08-05T00:00:00.000000003Z",
            completedAt="2026-08-05T00:00:00.000000004Z",
        )
        save_document(
            layout.run_history_path(tmp_path, record.alias, entry.runId),
            entry.to_dict(),
        )
    attempt = _attempt()
    attempt.attemptedAt = "2026-08-05T00:00:00.000000005Z"

    with pytest.raises(ValueError, match="(?i)(ambiguous|conflict|history)"):
        save_last_core_attempt(tmp_path, record.alias, attempt)

    assert not layout.run_authority_path(tmp_path, record.alias).exists()


def test_first_sidecar_rejects_same_id_equal_time_risk_divergence(
    tmp_path: Path,
) -> None:
    record = _saved_record(tmp_path)
    record.lastRun = {
        "runId": "legacy-risk-run",
        "status": "passed",
        "profile": "normal",
        "startedAt": ATTEMPTED_AT,
        "completedAt": COMPLETED_AT,
        "postCommitInterpretation": {
            "postCommit": False,
            "sideEffectMayExist": False,
        },
    }
    save_use_case(tmp_path, record)
    history_entry = RunHistoryEntry(
        runId="legacy-risk-run",
        useCaseAlias=record.alias,
        profile="normal",
        status="passed",
        startedAt=ATTEMPTED_AT,
        completedAt=COMPLETED_AT,
        postCommitInterpretation={
            "postCommit": True,
            "sideEffectMayExist": True,
        },
    )
    save_document(
        layout.run_history_path(tmp_path, record.alias, history_entry.runId),
        history_entry.to_dict(),
    )
    attempt = _attempt()
    attempt.attemptedAt = "2026-08-05T00:00:00.000000003Z"

    with pytest.raises(ValueError, match="(?i)(risk|diverge|conflict|history)"):
        save_last_core_attempt(tmp_path, record.alias, attempt)

    assert not layout.run_authority_path(tmp_path, record.alias).exists()


def test_recovered_future_history_advances_first_marker_identity(
    tmp_path: Path,
) -> None:
    record = _saved_record(tmp_path)
    record.lastRun = {
        "runId": "future-legacy-run",
        "status": "passed",
        "profile": "normal",
    }
    save_use_case(tmp_path, record)
    future_completed_at = "2099-08-05T00:00:00.000000002Z"
    history_entry = RunHistoryEntry(
        runId="future-legacy-run",
        useCaseAlias=record.alias,
        profile="normal",
        status="passed",
        startedAt="2099-08-05T00:00:00.000000001Z",
        completedAt=future_completed_at,
    )
    save_document(
        layout.run_history_path(tmp_path, record.alias, history_entry.runId),
        history_entry.to_dict(),
    )
    stale_wall_clock_attempt = _attempt()

    persisted = save_last_core_attempt(
        tmp_path,
        record.alias,
        stale_wall_clock_attempt,
    )

    assert persisted.lastCoreAttempt is not None
    assert persisted.lastCoreAttempt.attemptedAt > future_completed_at


def test_later_marker_cannot_mask_intervening_run_history(
    tmp_path: Path,
) -> None:
    record = _saved_record(tmp_path)
    save_last_core_attempt(tmp_path, record.alias, _attempt())
    record_run(tmp_path, _entry(record.alias))
    later_attempt = _attempt()
    later_attempt.attemptedAt = "2026-08-05T00:00:00.000000005Z"
    save_last_core_attempt(
        tmp_path,
        record.alias,
        later_attempt,
        expected_attempted_at=ATTEMPTED_AT,
    )
    intervening = RunHistoryEntry(
        runId="intervening-real-run",
        useCaseAlias=record.alias,
        profile="normal",
        status="passed",
        startedAt="2026-08-05T00:00:00.000000003Z",
        completedAt="2026-08-05T00:00:00.000000004Z",
    )
    save_document(
        layout.run_history_path(tmp_path, record.alias, intervening.runId),
        intervening.to_dict(),
    )

    with pytest.raises(ValueError, match="(?i)(newer|conflict|downgrade|history)"):
        load_use_case(tmp_path, record.alias)


def test_base_attempt_equal_to_canonical_completion_is_not_tombstoned(
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
    base = load_document(use_case_path)
    equal_attempt = _attempt()
    equal_attempt.attemptedAt = COMPLETED_AT
    base["lastCoreAttempt"] = equal_attempt.to_dict()
    save_document(use_case_path, base)

    with pytest.raises(ValueError, match="(?i)(attempt|tombstone|conflict)"):
        load_use_case(tmp_path, record.alias)


def test_base_run_equal_to_canonical_marker_requires_run_history_provenance(
    tmp_path: Path,
) -> None:
    record = _saved_record(tmp_path)
    marker = _attempt()
    marker.attemptedAt = COMPLETED_AT
    save_last_core_attempt(tmp_path, record.alias, marker)
    use_case_path = layout.use_case_path(tmp_path, record.alias)
    base = load_document(use_case_path)
    base["lastRun"] = {
        "runId": "unproven-equal-run",
        "status": "passed",
        "startedAt": ATTEMPTED_AT,
        "completedAt": COMPLETED_AT,
    }
    save_document(use_case_path, base)

    with pytest.raises(ValueError, match="(?i)(run|provenance|conflict|authority)"):
        load_use_case(tmp_path, record.alias)


@pytest.mark.parametrize(
    "attempted_at",
    [
        "2026-08-05T00:00:00.000000000Z",
        "2026-08-05T00:00:00.000000002Z",
        "2026-08-05T00:00:00.000000003Z",
    ],
    ids=["older-than-start", "between-start-and-completion", "equal-completion"],
)
def test_canonical_cross_slot_marker_rejects_impossible_run_ordering(
    tmp_path: Path,
    attempted_at: str,
) -> None:
    record = _saved_record(tmp_path)
    attempt = _attempt()
    attempt.attemptedAt = attempted_at
    last_run = {
        "runId": "canonical-real-run",
        "status": "passed",
        "startedAt": ATTEMPTED_AT,
        "completedAt": "2026-08-05T00:00:00.000000003Z",
    }
    save_document(
        layout.run_authority_path(tmp_path, record.alias),
        _authority_document(record.alias, attempt.to_dict(), last_run),
    )

    with pytest.raises(ValueError, match="(?i)(attempt|run|ordering|timestamp)"):
        load_use_case(tmp_path, record.alias)


@pytest.mark.parametrize(
    "attempted_at",
    [
        ATTEMPTED_AT,
        "2026-08-05T00:00:00.000000004Z",
    ],
    ids=["retained-same-start", "strictly-later-attempt"],
)
def test_canonical_cross_slot_marker_accepts_recoverable_run_ordering(
    tmp_path: Path,
    attempted_at: str,
) -> None:
    record = _saved_record(tmp_path)
    attempt = _attempt()
    attempt.attemptedAt = attempted_at
    last_run = {
        "runId": "canonical-real-run",
        "status": "passed",
        "startedAt": ATTEMPTED_AT,
        "completedAt": "2026-08-05T00:00:00.000000003Z",
    }
    save_document(
        layout.run_authority_path(tmp_path, record.alias),
        _authority_document(record.alias, attempt.to_dict(), last_run),
    )

    recovered = load_use_case(tmp_path, record.alias)

    assert recovered.lastCoreAttempt is not None
    assert recovered.lastCoreAttempt.attemptedAt == attempted_at
    assert recovered.lastRun == last_run


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
