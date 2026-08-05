from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.fixtures.workflows.entitlement_preflight_recovery import build_side_effect_policy
from tests.fixtures.workflows.side_effect_contract_alignment import create_write_policy_workspace
from verifysignal_spec.workspace.models import UseCaseRecord
from verifysignal_spec.workflows.write_safety import (
    build_rerun_approval_review,
    evaluate_rerun_decision,
)


def _real_run(
    *,
    post_commit: bool,
    side_effect_may_exist: bool,
    side_effect_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "runId": "real-run",
        "status": "passed" if post_commit else "failed",
        "completedAt": "2026-08-05T00:00:00Z",
        "sideEffectPolicy": side_effect_policy or {"class": "write", "mode": "enforce"},
        "postCommitInterpretation": {
            "postCommit": post_commit,
            "sideEffectMayExist": side_effect_may_exist,
            "failurePhase": "post-commit" if post_commit else "pre-commit",
            "sideEffectStatus": "committed-confirmed" if post_commit else "not-started",
            "rerunRisk": "requires-confirmation" if post_commit else "safe",
        },
    }


def _attempt(
    execution_state: str,
    *,
    side_effect_may_exist: bool | None = None,
) -> dict[str, Any]:
    return {
        "attemptedAt": "2026-08-05T01:00:00Z",
        "operation": "run",
        "schema": "verifysignal.error/v1",
        "status": "error",
        "errorCode": "entitlement.key-unknown",
        "executionState": execution_state,
        "sideEffectMayExist": side_effect_may_exist,
    }


@pytest.mark.parametrize(
    (
        "case_name",
        "side_effect_class",
        "last_run",
        "last_attempt",
        "expected_decision",
        "expected_outcome",
        "expected_branch",
    ),
    [
        ("no-run", "write", None, None, "allowed", "none", "none"),
        (
            "no-commit",
            "write",
            _real_run(post_commit=False, side_effect_may_exist=False),
            None,
            "allowed",
            "no-commit",
            "afterNoCommit",
        ),
        (
            "commit",
            "write",
            _real_run(post_commit=True, side_effect_may_exist=True),
            None,
            "blocked",
            "commit",
            "afterCommit",
        ),
        (
            "unknown-write-attempt",
            "write",
            None,
            _attempt("unknown"),
            "requires-confirmation",
            "unknown-write",
            "afterUnknown",
        ),
        (
            "safe-not-started-attempt",
            "write",
            None,
            _attempt("not-started", side_effect_may_exist=False),
            "allowed",
            "no-commit",
            "afterNoCommit",
        ),
        (
            "unknown-non-write-attempt",
            "none",
            None,
            _attempt("unknown"),
            "allowed",
            "no-commit",
            "afterNoCommit",
        ),
        (
            "historical-write-after-current-none",
            "none",
            _real_run(
                post_commit=True,
                side_effect_may_exist=True,
                side_effect_policy={"class": "write", "mode": "enforce"},
            ),
            None,
            "blocked",
            "commit",
            "afterCommit",
        ),
        (
            "newer-safe-attempt-after-real-write",
            "write",
            _real_run(post_commit=True, side_effect_may_exist=True),
            _attempt("not-started", side_effect_may_exist=False),
            "allowed",
            "no-commit",
            "afterNoCommit",
        ),
    ],
)
def test_one_evaluator_selects_exactly_one_rerun_policy_branch(
    tmp_path: Path,
    case_name: str,
    side_effect_class: str,
    last_run: dict[str, Any] | None,
    last_attempt: dict[str, Any] | None,
    expected_decision: str,
    expected_outcome: str,
    expected_branch: str,
) -> None:
    record = _record_for_case(
        tmp_path / case_name,
        side_effect_class=side_effect_class,
        last_run=last_run,
        last_attempt=last_attempt,
    )

    decision = evaluate_rerun_decision(record)

    assert decision["decision"] == expected_decision
    assert decision["outcomeClass"] == expected_outcome
    assert decision["policyBranch"] == expected_branch
    assert isinstance(decision["reason"], str) and decision["reason"]
    assert isinstance(decision["refreshRuntimeInputs"], list)
    assert isinstance(decision["nextAction"], str) and decision["nextAction"]


def test_only_a_run_attempt_can_override_the_previous_real_run(tmp_path: Path) -> None:
    record = _record_for_case(
        tmp_path,
        side_effect_class="write",
        last_run=_real_run(post_commit=True, side_effect_may_exist=True),
        last_attempt={**_attempt("not-started", side_effect_may_exist=False), "operation": "authoring-check"},
    )

    decision = evaluate_rerun_decision(record)

    assert decision["decision"] == "blocked"
    assert decision["outcomeClass"] == "commit"
    assert decision["policyBranch"] == "afterCommit"
    assert decision["sourceRunId"] == "real-run"


@pytest.mark.parametrize("attempted_at", ["", "not-a-timestamp"])
def test_non_comparable_attempt_does_not_override_a_timestamped_real_run(
    tmp_path: Path,
    attempted_at: str,
) -> None:
    record = _record_for_case(
        tmp_path,
        side_effect_class="write",
        last_run=_real_run(post_commit=True, side_effect_may_exist=True),
        last_attempt={
            **_attempt("not-started", side_effect_may_exist=False),
            "attemptedAt": attempted_at,
        },
    )

    decision = evaluate_rerun_decision(record)

    assert decision["decision"] == "blocked"
    assert decision["outcomeClass"] == "commit"
    assert decision["policyBranch"] == "afterCommit"
    assert decision["sourceRunId"] == "real-run"


def test_approval_is_scoped_to_the_exact_unknown_attempt_without_a_run_id(tmp_path: Path) -> None:
    record = _record_for_case(
        tmp_path,
        side_effect_class="write",
        last_run=None,
        last_attempt=_attempt("unknown"),
    )
    blocked = evaluate_rerun_decision(record)

    review = build_rerun_approval_review(
        record,
        blocked,
        created_at="2026-08-05T01:05:00Z",
        created_by="test",
    )
    approved = evaluate_rerun_decision(record, supersede_reviews=[review])

    assert blocked["decision"] == "requires-confirmation"
    assert "unknown-run" not in review.sourceRunId
    assert approved["decision"] == "allowed"
    assert approved["outcomeClass"] == "unknown-write"
    assert approved["policyBranch"] == "afterUnknown"


def test_approval_follows_a_newer_unknown_attempt_instead_of_an_older_real_run(tmp_path: Path) -> None:
    record = _record_for_case(
        tmp_path,
        side_effect_class="write",
        last_run=_real_run(post_commit=False, side_effect_may_exist=False),
        last_attempt=_attempt("unknown"),
    )
    blocked = evaluate_rerun_decision(record)

    review = build_rerun_approval_review(
        record,
        blocked,
        created_at="2026-08-05T01:05:00Z",
        created_by="test",
    )
    approved = evaluate_rerun_decision(record, supersede_reviews=[review])

    assert blocked["outcomeClass"] == "unknown-write"
    assert review.sourceRunId.startswith("core-attempt-")
    assert review.sourceRunId != "real-run"
    assert approved["decision"] == "allowed"
    assert approved["supersededBy"] == review.reviewId


def test_legacy_write_interpretation_remains_write_evidence_after_current_class_becomes_none(
    tmp_path: Path,
) -> None:
    last_run = _real_run(post_commit=True, side_effect_may_exist=True)
    last_run.pop("sideEffectPolicy")
    record = _record_for_case(
        tmp_path,
        side_effect_class="none",
        last_run=last_run,
        last_attempt=None,
    )

    decision = evaluate_rerun_decision(record)

    assert decision["decision"] == "blocked"
    assert decision["outcomeClass"] == "commit"
    assert decision["policyBranch"] == "afterCommit"


def test_equal_timestamp_attempt_does_not_override_the_real_run(tmp_path: Path) -> None:
    record = _record_for_case(
        tmp_path,
        side_effect_class="write",
        last_run=_real_run(post_commit=True, side_effect_may_exist=True),
        last_attempt={
            **_attempt("not-started", side_effect_may_exist=False),
            "attemptedAt": "2026-08-05T00:00:00Z",
        },
    )

    decision = evaluate_rerun_decision(record)

    assert decision["decision"] == "blocked"
    assert decision["outcomeClass"] == "commit"
    assert decision["sourceRunId"] == "real-run"


def test_attempt_confirmation_identity_uses_all_redacted_attempt_evidence(tmp_path: Path) -> None:
    first = _record_for_case(
        tmp_path / "first",
        side_effect_class="write",
        last_run=None,
        last_attempt=_attempt("unknown"),
    )
    second_attempt = {
        **_attempt("unknown"),
        "errorCode": "entitlement.expired",
    }
    second = _record_for_case(
        tmp_path / "second",
        side_effect_class="write",
        last_run=None,
        last_attempt=second_attempt,
    )

    first_decision = evaluate_rerun_decision(first)
    second_decision = evaluate_rerun_decision(second)

    assert first_decision["confirmationId"] != second_decision["confirmationId"]
    assert "entitlement" not in first_decision["confirmationId"]
    assert "entitlement" not in second_decision["confirmationId"]


def _record_for_case(
    project: Path,
    *,
    side_effect_class: str,
    last_run: dict[str, Any] | None,
    last_attempt: dict[str, Any] | None,
) -> UseCaseRecord:
    record = create_write_policy_workspace(project, last_run=last_run)
    record.sideEffects = build_side_effect_policy(side_effect_class=side_effect_class)
    record.rerunPolicy = {
        "afterNoCommit": "allowed",
        "afterCommit": "blocked",
        "afterUnknown": "requires-confirmation",
    }
    payload = record.to_dict()
    if last_attempt is not None:
        payload["lastCoreAttempt"] = dict(last_attempt)
    return UseCaseRecord.from_dict(payload)
