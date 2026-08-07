from __future__ import annotations

from pathlib import Path

import pytest

from tests.fixtures.workflows.entitlement_preflight_recovery import (
    build_protected_readiness_snapshot,
)
from tests.fixtures.workflows.prerequisites import create_current_understanding_workspace
from tests.fixtures.workflows.side_effect_contract_alignment import create_write_policy_workspace
from tests.helpers import FAKE_CORE
from verifysignal_spec.workspace import layout
from verifysignal_spec.workspace.models import AuthoringQuestion, LastCoreAttempt
from verifysignal_spec.workspace.repository import (
    artifact_fingerprints,
    list_use_cases,
    load_document,
    load_readiness_snapshot,
    load_use_case,
    now_iso,
    readiness_current_state,
    save_document,
    save_last_core_attempt,
    save_use_case,
    snapshot_invalidation_reasons,
)
from verifysignal_spec.workflows.prerequisites import check_prerequisites
from verifysignal_spec.workflows.write_safety import evaluate_rerun_decision


def test_unknown_write_attempt_creates_the_exact_active_confirmation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    alias = _prepare_confirmation_workspace(tmp_path, monkeypatch, execution_state="unknown")

    result = check_prerequisites(tmp_path, "run", alias=alias)

    assert result["status"] == "blocked"
    assert result["canProceed"] is False
    assert result["requiresConfirmation"] is True
    assert result["rerunDecision"]["outcomeClass"] == "unknown-write"
    assert result["rerunDecision"]["policyBranch"] == "afterUnknown"
    stored = load_document(layout.confirmation_requirement_path(tmp_path, alias))
    assert stored["id"] == result["confirmation"]["id"]
    assert stored["scope"] == result["confirmation"]["scope"]
    assert stored["riskClass"] == "unknown-write-risk"
    assert stored["blocksExecution"] is True


def test_changed_confirmation_is_replaced_without_touching_supersede_reviews(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    alias = _prepare_confirmation_workspace(tmp_path, monkeypatch, execution_state="unknown")
    confirmation_path = layout.confirmation_requirement_path(tmp_path, alias)
    save_document(
        confirmation_path,
        {
            "id": "confirm.stale.old-risk",
            "alias": alias,
            "riskClass": "stale-risk",
            "scope": "stale-scope",
            "reason": "This gate no longer describes current evidence.",
            "recommendedAction": "obsolete",
            "blocksExecution": True,
        },
    )
    review_path = layout.supersede_review_path(tmp_path, alias, "review-prior-run")
    save_document(
        review_path,
        {
            "schemaVersion": "verifysignal-spec-supersede-review/v1",
            "reviewId": "review-prior-run",
            "sourceRunId": "prior-run",
            "ownerDecision": "approved-rerun-after-write",
            "evidenceSummary": "Historical owner review.",
            "previousClassification": {"rerunRisk": "requires-confirmation"},
            "resultingClassification": {"rerunRisk": "safe"},
            "reason": "Preserve this audit record.",
            "createdAt": "2026-08-04T00:00:00Z",
        },
    )
    review_bytes = review_path.read_bytes()

    result = check_prerequisites(tmp_path, "run", alias=alias)

    stored = load_document(confirmation_path)
    assert stored["id"] == result["confirmation"]["id"]
    assert stored["id"] != "confirm.stale.old-risk"
    assert stored["scope"] == result["confirmation"]["scope"]
    assert stored["riskClass"] == "unknown-write-risk"
    assert review_path.read_bytes() == review_bytes


def test_safe_attempt_deletes_a_stale_active_gate_but_preserves_audit_history(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    alias = _prepare_confirmation_workspace(
        tmp_path,
        monkeypatch,
        execution_state="not-started",
        side_effect_may_exist=False,
    )
    confirmation_path = layout.confirmation_requirement_path(tmp_path, alias)
    save_document(
        confirmation_path,
        {
            "id": "confirm.stale.unknown-write-risk",
            "alias": alias,
            "riskClass": "unknown-write-risk",
            "scope": "unknown-write-risk",
            "reason": "An older unknown attempt required review.",
            "recommendedAction": "confirm",
            "blocksExecution": True,
        },
    )
    review_path = layout.supersede_review_path(tmp_path, alias, "review-prior-run")
    save_document(
        review_path,
        {
            "schemaVersion": "verifysignal-spec-supersede-review/v1",
            "reviewId": "review-prior-run",
            "sourceRunId": "prior-run",
            "ownerDecision": "approved-rerun-after-write",
            "evidenceSummary": "Historical owner review.",
            "previousClassification": {"rerunRisk": "requires-confirmation"},
            "resultingClassification": {"rerunRisk": "safe"},
            "reason": "Preserve this audit record.",
            "createdAt": "2026-08-04T00:00:00Z",
        },
    )
    review_bytes = review_path.read_bytes()

    result = check_prerequisites(tmp_path, "run", alias=alias)

    assert result["status"] == "ready"
    assert result["canProceed"] is True
    assert result["requiresConfirmation"] is False
    assert result["rerunDecision"]["outcomeClass"] == "no-commit"
    assert result["rerunDecision"]["policyBranch"] == "afterNoCommit"
    assert confirmation_path.exists() is False
    assert review_path.read_bytes() == review_bytes


@pytest.mark.parametrize("early_blocker", ["understanding", "missing-stage", "target"])
def test_early_workflow_return_still_reconciles_the_authoritative_active_gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    early_blocker: str,
) -> None:
    alias = _prepare_confirmation_workspace(
        tmp_path,
        monkeypatch,
        execution_state="unknown",
    )
    record = load_use_case(tmp_path, alias)
    expected_id = evaluate_rerun_decision(record)["confirmationId"]
    if early_blocker == "understanding":
        layout.workflow_global_understanding_path(tmp_path).unlink()
    elif early_blocker == "missing-stage":
        (layout.workflow_use_case_dir(tmp_path, alias) / "plan.md").unlink()
    else:
        record.authoringQuestions.append(
            AuthoringQuestion(
                id="browser-target-environment",
                prompt="Confirm the browser target.",
                status="pending",
                requiresConfirmation=True,
                suggestedAnswer={"baseUrl": "https://example.test"},
                suggestionSource="repository-start-instructions",
            )
        )
        save_use_case(tmp_path, record)
    confirmation_path = layout.confirmation_requirement_path(tmp_path, alias)
    save_document(
        confirmation_path,
        {
            "id": "confirm.stale.before-early-return",
            "alias": alias,
            "riskClass": "stale",
            "scope": "stale",
            "reason": "Obsolete gate.",
            "recommendedAction": "obsolete",
            "blocksExecution": True,
        },
    )

    result = check_prerequisites(tmp_path, "run", alias=alias)

    assert result["canProceed"] is False
    stored = load_document(confirmation_path)
    assert stored["id"] == expected_id
    assert stored["id"] != "confirm.stale.before-early-return"


def test_attempt_marker_is_not_readiness_artifact_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    alias = _prepare_confirmation_workspace(
        tmp_path,
        monkeypatch,
        execution_state="not-started",
        side_effect_may_exist=False,
    )
    record = load_use_case(tmp_path, alias)
    record.lastCoreAttempt = None
    save_use_case(tmp_path, record)
    snapshot = load_readiness_snapshot(tmp_path, alias)
    assert snapshot is not None
    snapshot.artifactFingerprints = artifact_fingerprints(tmp_path, record)
    save_document(layout.readiness_snapshot_path(tmp_path, alias), snapshot.to_dict())
    save_last_core_attempt(
        tmp_path,
        alias,
        LastCoreAttempt(
            attemptedAt="2026-08-05T01:00:00.000000001Z",
            operation="run",
            schema="verifysignal.error/v1",
            status="error",
            errorCode="entitlement.key-unknown",
            executionState="not-started",
            sideEffectMayExist=False,
        ),
    )
    updated = load_use_case(tmp_path, alias)

    reasons = snapshot_invalidation_reasons(tmp_path, updated, snapshot)
    current = readiness_current_state(tmp_path, updated)

    assert "artifact-changed" not in {item["code"] for item in reasons}
    assert current["status"] == "ready"


@pytest.mark.parametrize(
    ("execution_state", "side_effect_may_exist", "expected_outcome", "expected_decision"),
    [
        ("not-started", False, "no-commit", "allowed"),
        ("unknown", None, "unknown-write", "requires-confirmation"),
    ],
)
def test_list_projects_the_newer_attempt_instead_of_stale_last_run_risk(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    execution_state: str,
    side_effect_may_exist: bool | None,
    expected_outcome: str,
    expected_decision: str,
) -> None:
    create_current_understanding_workspace(tmp_path)
    record = create_write_policy_workspace(
        tmp_path,
        last_run={
            "runId": "older-real-run",
            "status": "passed",
            "completedAt": "2026-08-05T00:00:00Z",
            "sideEffectPolicy": {"class": "write", "mode": "enforce"},
            "postCommitInterpretation": {
                "postCommit": True,
                "sideEffectMayExist": True,
                "sideEffectStatus": "committed-confirmed",
                "rerunRisk": "requires-confirmation",
            },
        },
        protected_ready=True,
    )
    save_last_core_attempt(
        tmp_path,
        record.alias,
        LastCoreAttempt(
            attemptedAt="2026-08-05T01:00:00.000000001Z",
            operation="run",
            schema="verifysignal.error/v1",
            status="error",
            errorCode="entitlement.key-unknown",
            executionState=execution_state,  # type: ignore[arg-type]
            sideEffectMayExist=side_effect_may_exist,
        ),
    )

    rows, warnings = list_use_cases(tmp_path)
    row = next(item for item in rows if item["alias"] == record.alias)

    assert warnings == []
    assert row["risk"]["rerun"]["outcomeClass"] == expected_outcome
    assert row["risk"]["rerun"]["decision"] == expected_decision
    if execution_state == "not-started":
        assert row["current"]["status"] == "ready"
    else:
        assert row["current"]["status"] == "needs-rerun-confirmation"


def _prepare_confirmation_workspace(
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    execution_state: str,
    side_effect_may_exist: bool | None = None,
) -> str:
    monkeypatch.setenv("VERIFYSIGNAL_CORE_CMD", str(FAKE_CORE))
    monkeypatch.setenv("VERIFYSIGNAL_RUNTIME_CACHE_DIR", str(project / "runtime-cache"))
    create_current_understanding_workspace(project)
    record = create_write_policy_workspace(project)
    record.status = "ready"
    record.artifactCapabilities = {
        "capabilities": [
            "explicit-confirmation",
            "generated-runtime-inputs",
            "resource-identity",
            "side-effect-lifecycle",
            "write-activity-interpretation",
        ]
    }
    record.rerunPolicy = {
        "afterNoCommit": "allowed",
        "afterCommit": "blocked",
        "afterUnknown": "requires-confirmation",
    }
    save_use_case(project, record)
    record_path = layout.use_case_path(project, record.alias)
    document = load_document(record_path)
    document["lastCoreAttempt"] = {
        "attemptedAt": "2026-08-05T01:00:00Z",
        "operation": "run",
        "schema": "verifysignal.error/v1",
        "status": "error",
        "errorCode": "entitlement.key-unknown",
        "executionState": execution_state,
        "sideEffectMayExist": side_effect_may_exist,
    }
    save_document(record_path, document)
    readiness = build_protected_readiness_snapshot(
        record.alias,
        status="ready",
        protected_status="passed",
        readiness_scope="protected-operation",
        side_effect_class="write",
    )
    readiness["checkedAt"] = now_iso()
    save_document(layout.readiness_snapshot_path(project, record.alias), readiness)
    workflow_root = layout.workflow_use_case_dir(project, record.alias)
    workflow_root.mkdir(parents=True, exist_ok=True)
    for stage in ("spec", "plan", "tasks"):
        (workflow_root / f"{stage}.md").write_text(f"# {stage}\n", encoding="utf-8")
        if stage != "spec":
            (workflow_root / f"{stage}.yaml").write_text("{}\n", encoding="utf-8")
    return record.alias
