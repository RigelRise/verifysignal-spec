from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.fixtures.workflows.entitlement_preflight_recovery import (
    build_protected_readiness_snapshot,
)
from tests.fixtures.workflows.prerequisites import create_current_understanding_workspace
from tests.fixtures.workflows.side_effect_contract_alignment import create_write_policy_workspace
from tests.helpers import FAKE_CORE
from verifysignal_spec.commands import run as run_command
from verifysignal_spec.workspace import layout, repository as workspace_repository
from verifysignal_spec.workspace.models import LastCoreAttempt, RunHistoryEntry
from verifysignal_spec.workspace.repository import load_document, now_iso, save_document, save_use_case


def test_current_preexecution_core_error_records_a_safe_non_run_attempt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    alias = _prepare_error_workspace(tmp_path, monkeypatch, mode="current-entitlement-error")

    result = run_command.run(tmp_path, alias, interactive=False, core_cmd=str(FAKE_CORE))

    assert result["status"] == "blocked"
    assert _blocker_codes(result) == ["entitlement.unverifiable"]
    document = load_document(layout.use_case_path(tmp_path, alias))
    attempt = document["lastCoreAttempt"]
    assert attempt["operation"] == "run"
    assert attempt["schema"] == "verifysignal.error/v1"
    assert attempt["status"] == "error"
    assert attempt["errorCode"] == "entitlement.key-unknown"
    assert attempt["executionState"] == "not-started"
    assert attempt["sideEffectMayExist"] is False
    assert attempt["attemptedAt"]
    assert re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{9}Z",
        attempt["attemptedAt"],
    )
    assert _forbidden_attempt_fields(attempt) == set()
    assert list(_history_dir(tmp_path, alias).glob("*.yaml")) == []
    assert document.get("lastRun") is None


def test_legacy_core_error_preserves_every_prior_real_run_projection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    alias = _prepare_error_workspace(tmp_path, monkeypatch, mode="legacy-entitlement-error")
    use_case_path = layout.use_case_path(tmp_path, alias)
    document = load_document(use_case_path)
    previous_last_run = {
        "runId": "prior-real-run",
        "status": "failed",
        "completedAt": "2026-08-04T20:00:00Z",
        "coreStatus": "failed",
        "coverageStatus": "incomplete",
        "gateCoverage": [{"gateId": "page-visible", "status": "passed"}],
        "reportPath": ".verifysignal/runs/add-collaboration-project/prior-real-run/report.json",
        "evidenceDir": ".verifysignal/runs/add-collaboration-project/prior-real-run/evidence",
        "postCommitInterpretation": {
            "postCommit": False,
            "sideEffectMayExist": False,
            "sideEffectStatus": "not-started",
            "failurePhase": "pre-commit",
            "rerunRisk": "safe",
        },
    }
    document["lastRun"] = previous_last_run
    document["repair"] = {"repairId": "prior-repair", "status": "proposed"}
    save_document(use_case_path, document)

    history_path = layout.run_history_path(tmp_path, alias, "prior-real-run")
    evidence_path = _history_dir(tmp_path, alias) / "prior-real-run" / "evidence" / "page.txt"
    repair_path = layout.repair_path(tmp_path, "prior-repair")
    save_document(history_path, {"runId": "prior-real-run", "sentinel": "history-preserved"})
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text("evidence-preserved\n", encoding="utf-8")
    save_document(repair_path, {"repairId": "prior-repair", "sentinel": "repair-preserved"})
    prior_files = {
        history_path: history_path.read_bytes(),
        evidence_path: evidence_path.read_bytes(),
        repair_path: repair_path.read_bytes(),
    }

    result = run_command.run(tmp_path, alias, interactive=False, core_cmd=str(FAKE_CORE))

    assert result["status"] == "blocked"
    assert _blocker_codes(result) == ["entitlement.unverifiable"]
    updated = load_document(use_case_path)
    assert updated["lastRun"] == previous_last_run
    assert updated["repair"] == {"repairId": "prior-repair", "status": "proposed"}
    assert sorted(path.name for path in _history_dir(tmp_path, alias).glob("*.yaml")) == [
        "prior-real-run.yaml"
    ]
    for path, content in prior_files.items():
        assert path.read_bytes() == content
    attempt = updated["lastCoreAttempt"]
    assert attempt["operation"] == "run"
    assert attempt["schema"] == "verifysignal.error/v1"
    assert attempt["errorCode"] == "entitlement.key-unknown"
    assert attempt["executionState"] == "unknown"
    assert attempt.get("sideEffectMayExist") is None
    assert _forbidden_attempt_fields(attempt) == set()


def test_confirm_risk_releases_the_exact_unknown_attempt_without_a_synthetic_run_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    alias = _prepare_error_workspace(tmp_path, monkeypatch, mode="legacy-entitlement-error")

    blocked = run_command.run(tmp_path, alias, interactive=False, core_cmd=str(FAKE_CORE))
    confirmation_id = blocked["rerunDecision"]["confirmationId"]
    monkeypatch.setenv("FAKE_VERIFYSIGNAL_MODE", "ok")

    resumed = run_command.run(
        tmp_path,
        alias,
        interactive=False,
        core_cmd=str(FAKE_CORE),
        confirmed_risks=[confirmation_id],
    )

    assert resumed["status"] != "blocked"
    updated = load_document(layout.use_case_path(tmp_path, alias))
    assert updated.get("lastCoreAttempt") is None
    assert len(list(_history_dir(tmp_path, alias).glob("*.yaml"))) == 1


def test_attempt_marker_is_not_cleared_when_valid_run_persistence_fails_late(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    alias = _prepare_error_workspace(tmp_path, monkeypatch, mode="current-entitlement-error")
    record = workspace_repository.load_use_case(tmp_path, alias)
    record.lastCoreAttempt = LastCoreAttempt(
        attemptedAt="2026-08-05T01:00:00.000000001Z",
        operation="run",
        schema="verifysignal.error/v1",
        status="error",
        errorCode="entitlement.key-unknown",
        executionState="not-started",
        sideEffectMayExist=False,
    )
    save_use_case(tmp_path, record)

    def fail_output_projection(*_args, **_kwargs):
        raise RuntimeError("simulated late persistence failure")

    monkeypatch.setattr(
        workspace_repository,
        "_publish_outputs_from_run",
        fail_output_projection,
    )
    entry = RunHistoryEntry(
        runId="valid-run-before-late-failure",
        useCaseAlias=alias,
        profile="normal",
        status="passed",
        startedAt="2026-08-05T02:00:00Z",
        completedAt="2026-08-05T02:01:00Z",
    )

    with pytest.raises(RuntimeError, match="late persistence failure"):
        workspace_repository.record_run(tmp_path, entry)

    persisted = workspace_repository.load_use_case(tmp_path, alias)
    assert persisted.lastCoreAttempt is not None
    assert persisted.lastCoreAttempt.attemptedAt == "2026-08-05T01:00:00.000000001Z"


def _prepare_error_workspace(
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    mode: str,
) -> str:
    monkeypatch.setenv("VERIFYSIGNAL_CORE_CMD", str(FAKE_CORE))
    monkeypatch.setenv("FAKE_VERIFYSIGNAL_MODE", mode)
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


def _history_dir(project: Path, alias: str) -> Path:
    return layout.workspace_root(project) / layout.RUNS_DIR / alias


def _blocker_codes(result: dict[str, object]) -> list[str]:
    blockers = result.get("blockers")
    if not isinstance(blockers, list):
        return []
    return [str(item.get("code")) for item in blockers if isinstance(item, dict)]


def _forbidden_attempt_fields(attempt: dict[str, object]) -> set[str]:
    forbidden = {
        "command",
        "credential",
        "data",
        "environment",
        "evidenceDir",
        "message",
        "path",
        "preparedRequestPath",
        "rawResponse",
        "receipt",
        "reportPath",
        "runId",
        "signature",
        "stderr",
        "stdout",
        "token",
    }
    return forbidden & set(attempt)
