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
from verifysignal_spec.workspace.repository import load_document, now_iso, save_document, save_use_case
from verifysignal_spec.workflows.prerequisites import check_prerequisites


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
