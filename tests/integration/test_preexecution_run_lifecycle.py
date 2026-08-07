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
from verifysignal_spec.workflows import run_lock as run_lock_module
from verifysignal_spec.workflows.engine import create_workflow_run
from verifysignal_spec.workflows.prerequisites import check_prerequisites
from verifysignal_spec.workflows.run_lock import acquire_run_invocation_lease
from verifysignal_spec.workflows.transitions import transition_workflow
from verifysignal_spec.workflows.write_safety import evaluate_rerun_decision


def test_current_preexecution_core_error_records_a_safe_non_run_attempt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    alias = _prepare_error_workspace(tmp_path, monkeypatch, mode="current-entitlement-error")
    attempted_at = "2026-08-05T01:02:03.000000004Z"
    monkeypatch.setattr(run_command, "core_attempt_iso", lambda: attempted_at)

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
    assert attempt["attemptedAt"] == attempted_at
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
    save_document(
        history_path,
        {
            "runId": "prior-real-run",
            "useCaseAlias": alias,
            "profile": "normal",
            "status": "failed",
            "startedAt": "2026-08-04T19:59:59Z",
            "completedAt": "2026-08-04T20:00:00Z",
            "coreStatus": "failed",
            "coverageStatus": "incomplete",
            "gateCoverage": [{"gateId": "page-visible", "status": "passed"}],
            "reportPath": previous_last_run["reportPath"],
            "evidenceDir": previous_last_run["evidenceDir"],
            "postCommitInterpretation": previous_last_run[
                "postCommitInterpretation"
            ],
            "sentinel": "history-preserved",
        },
    )
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
    assert all(
        updated["lastRun"].get(key) == value
        for key, value in previous_last_run.items()
    )
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
        startedAt="2026-08-05T01:00:00.000000001Z",
        completedAt="2026-08-05T01:01:00Z",
    )

    with pytest.raises(RuntimeError, match="late persistence failure"):
        workspace_repository.record_run(tmp_path, entry)

    persisted = workspace_repository.load_use_case(tmp_path, alias)
    assert persisted.lastCoreAttempt is not None
    assert persisted.lastCoreAttempt.attemptedAt == "2026-08-05T01:00:00.000000001Z"


@pytest.mark.parametrize("failure_point", ["result-interpretation", "record-run"])
def test_valid_core_run_keeps_conservative_attempt_until_last_run_is_durable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_point: str,
) -> None:
    alias = _prepare_error_workspace(tmp_path, monkeypatch, mode="ok")

    def fail_after_core(*_args, **_kwargs):
        raise RuntimeError(f"simulated {failure_point} failure")

    if failure_point == "result-interpretation":
        monkeypatch.setattr(run_command, "_result_with_public_report", fail_after_core)
    else:
        monkeypatch.setattr(run_command, "record_run", fail_after_core)

    with pytest.raises(RuntimeError, match=failure_point):
        run_command.run(tmp_path, alias, interactive=False, core_cmd=str(FAKE_CORE))

    persisted = workspace_repository.load_use_case(tmp_path, alias)
    assert persisted.lastRun is None
    assert persisted.lastCoreAttempt is not None
    assert persisted.lastCoreAttempt.operation == "run"
    assert persisted.lastCoreAttempt.status == "unknown"
    assert persisted.lastCoreAttempt.executionState == "unknown"
    assert persisted.lastCoreAttempt.sideEffectMayExist is True
    decision = evaluate_rerun_decision(persisted)
    assert decision["decision"] == "requires-confirmation"
    assert decision["outcomeClass"] == "unknown-write"
    assert decision["policyBranch"] == "afterUnknown"


def test_core_invocation_starts_only_after_write_ahead_marker_is_durable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    alias = _prepare_error_workspace(tmp_path, monkeypatch, mode="current-entitlement-error")
    original_run = run_command.CoreAdapter.run

    def assert_marker_before_core(adapter, *args, **kwargs):
        attempt = workspace_repository.load_use_case(tmp_path, alias).lastCoreAttempt
        assert attempt is not None
        assert attempt.operation == "run"
        assert attempt.status == "unknown"
        assert attempt.executionState == "unknown"
        assert attempt.sideEffectMayExist is True
        return original_run(adapter, *args, **kwargs)

    monkeypatch.setattr(run_command.CoreAdapter, "run", assert_marker_before_core)

    result = run_command.run(tmp_path, alias, interactive=False, core_cmd=str(FAKE_CORE))

    assert result["status"] == "blocked"


def test_concurrent_run_and_workflow_check_fail_closed_without_invoking_core(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    alias = _prepare_error_workspace(tmp_path, monkeypatch, mode="ok")
    lease = acquire_run_invocation_lease(tmp_path, alias)
    assert lease is not None

    def forbid_core(*_args, **_kwargs):
        raise AssertionError("Core must not run while the alias lease is held")

    monkeypatch.setattr(run_command.CoreAdapter, "run", forbid_core)
    try:
        checked = check_prerequisites(tmp_path, "run", alias)
        result = run_command.run(
            tmp_path,
            alias,
            interactive=False,
            core_cmd=str(FAKE_CORE),
        )
    finally:
        lease.release()

    assert checked["canProceed"] is False
    assert _blocker_codes(checked) == ["runtime.run-in-progress"]
    assert result["status"] == "blocked"
    assert result["coreStatus"] == "not-run"
    assert _blocker_codes(result) == ["runtime.run-in-progress"]
    persisted = workspace_repository.load_use_case(tmp_path, alias)
    assert persisted.lastCoreAttempt is None
    assert persisted.lastRun is None


def test_unavailable_run_lock_fails_workflow_check_and_direct_run_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    alias = _prepare_error_workspace(tmp_path, monkeypatch, mode="ok")
    runtime_calls = {"resolution": 0, "core": 0}

    def unavailable_lock(*_args, **_kwargs):
        raise OSError("simulated trustworthy lock primitive failure")

    def forbid_runtime(*_args, **_kwargs):
        runtime_calls["resolution"] += 1
        raise AssertionError("Runtime resolution must not follow lock failure")

    def forbid_core(*_args, **_kwargs):
        runtime_calls["core"] += 1
        raise AssertionError("Core must not run when the lease is unavailable")

    backend = (
        "_acquire_windows_mutex"
        if run_lock_module.os.name == "nt"
        else "_acquire_posix_lock"
    )
    monkeypatch.setattr(run_lock_module, backend, unavailable_lock)
    monkeypatch.setattr(run_command, "ensure_core_runtime", forbid_runtime)
    monkeypatch.setattr(run_command.CoreAdapter, "run", forbid_core)

    checked = check_prerequisites(tmp_path, "run", alias)
    result = run_command.run(
        tmp_path,
        alias,
        interactive=False,
        core_cmd=str(FAKE_CORE),
    )

    assert runtime_calls == {"resolution": 0, "core": 0}
    assert checked["canProceed"] is False
    assert result["canProceed"] is False
    assert checked["blockers"] == result["blockers"]
    assert _blocker_codes(checked) == ["runtime.run-lock-unavailable"]
    persisted = workspace_repository.load_use_case(tmp_path, alias)
    assert persisted.lastCoreAttempt is None
    assert persisted.lastRun is None
    assert list(_history_dir(tmp_path, alias).glob("*.yaml")) == []


def test_successful_last_run_outranks_write_ahead_marker_when_clear_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    alias = _prepare_error_workspace(tmp_path, monkeypatch, mode="ok")

    def fail_clear(*_args, **_kwargs):
        raise RuntimeError("simulated marker clear failure")

    monkeypatch.setattr(run_command, "clear_last_core_attempt", fail_clear)

    with pytest.raises(RuntimeError, match="marker clear failure"):
        run_command.run(tmp_path, alias, interactive=False, core_cmd=str(FAKE_CORE))

    persisted = workspace_repository.load_use_case(tmp_path, alias)
    assert persisted.lastRun is not None
    assert persisted.lastCoreAttempt is not None
    assert persisted.lastRun["startedAt"] == persisted.lastCoreAttempt.attemptedAt
    assert persisted.lastRun["completedAt"] > persisted.lastCoreAttempt.attemptedAt
    decision = evaluate_rerun_decision(persisted)
    assert decision.get("sourceRunId") == persisted.lastRun["runId"]


@pytest.mark.parametrize("risk_location", ["execution", "side-effects"])
def test_valid_run_preserves_explicit_runtime_write_risk_for_authored_none(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    risk_location: str,
) -> None:
    alias = _prepare_error_workspace(tmp_path, monkeypatch, mode="ok")
    record = workspace_repository.load_use_case(tmp_path, alias)
    record.sideEffects = {
        "class": "none",
        "mode": "observe",
        "allowed": [],
        "forbidden": [],
    }
    record.rerunPolicy = {
        "afterNoCommit": "allowed",
        "afterCommit": "blocked",
        "afterUnknown": "requires-confirmation",
    }
    save_use_case(tmp_path, record)
    original_run = run_command.CoreAdapter.run

    def return_explicit_runtime_write_risk(adapter, *args, **kwargs):
        response = original_run(adapter, *args, **kwargs)
        if risk_location == "execution":
            response["execution"] = {
                "started": True,
                "phase": "browser",
                "sideEffectMayExist": True,
            }
        else:
            response["data"]["sideEffects"] = {
                "policy": {"class": "none", "mode": "observe"},
                "commitStep": {"reached": False},
                "status": "not-observed",
                "sideEffectMayExist": True,
            }
        return response

    monkeypatch.setattr(
        run_command.CoreAdapter,
        "run",
        return_explicit_runtime_write_risk,
    )

    result = run_command.run(
        tmp_path,
        alias,
        interactive=False,
        core_cmd=str(FAKE_CORE),
    )

    assert result["status"] != "blocked"
    persisted = workspace_repository.load_use_case(tmp_path, alias)
    assert persisted.lastRun is not None
    assert persisted.lastRun["sideEffectPolicy"]["class"] == "none"
    assert persisted.lastRun["postCommitInterpretation"]["sideEffectMayExist"] is True
    history = load_document(
        layout.run_history_path(tmp_path, alias, persisted.lastRun["runId"])
    )
    assert history["postCommitInterpretation"]["sideEffectMayExist"] is True
    decision = evaluate_rerun_decision(persisted)
    assert decision["decision"] == "blocked"
    assert decision["outcomeClass"] == "commit"
    assert decision["policyBranch"] == "afterCommit"


def test_successful_run_never_clears_a_marker_owned_by_another_attempt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    alias = _prepare_error_workspace(tmp_path, monkeypatch, mode="ok")
    original_record_run = run_command.record_run
    foreign_attempt = LastCoreAttempt(
        attemptedAt="2999-08-05T01:00:00.000000001Z",
        operation="run",
        schema=None,
        status="unknown",
        errorCode=None,
        executionState="unknown",
        sideEffectMayExist=True,
    )

    def persist_run_then_replace_marker(project: Path, entry: RunHistoryEntry) -> None:
        original_record_run(project, entry)
        workspace_repository.save_last_core_attempt(project, alias, foreign_attempt)

    monkeypatch.setattr(run_command, "record_run", persist_run_then_replace_marker)

    with pytest.raises(workspace_repository.LastCoreAttemptOwnershipError):
        run_command.run(tmp_path, alias, interactive=False, core_cmd=str(FAKE_CORE))

    persisted = workspace_repository.load_use_case(tmp_path, alias)
    assert persisted.lastRun is not None
    assert persisted.lastCoreAttempt == foreign_attempt


def test_new_write_ahead_attempt_orders_after_prior_run_when_clock_moves_back(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    alias = _prepare_error_workspace(tmp_path, monkeypatch, mode="ok")
    record = workspace_repository.load_use_case(tmp_path, alias)
    record.lastRun = {
        "runId": "prior-safe-run",
        "status": "failed",
        "startedAt": "2026-08-05T02:00:00.000000001Z",
        "completedAt": "2026-08-05T02:00:00.000000002Z",
        "sideEffectPolicy": {"class": "none", "mode": "observe"},
        "postCommitInterpretation": {
            "postCommit": False,
            "sideEffectMayExist": False,
            "sideEffectStatus": "not-started",
            "failurePhase": "pre-commit",
            "rerunRisk": "safe",
        },
    }
    save_use_case(tmp_path, record)
    monkeypatch.setattr(
        workspace_repository.time,
        "time_ns",
        lambda: 1_754_356_800_000_000_001,
    )

    def fail_after_core(*_args, **_kwargs):
        raise RuntimeError("forced post-Core crash")

    monkeypatch.setattr(run_command, "_result_with_public_report", fail_after_core)

    with pytest.raises(RuntimeError, match="post-Core crash"):
        run_command.run(tmp_path, alias, interactive=False, core_cmd=str(FAKE_CORE))

    persisted = workspace_repository.load_use_case(tmp_path, alias)
    assert persisted.lastCoreAttempt is not None
    assert persisted.lastCoreAttempt.attemptedAt > record.lastRun["completedAt"]
    decision = evaluate_rerun_decision(persisted)
    assert decision["decision"] == "requires-confirmation"
    assert decision["outcomeClass"] == "unknown-write"
    assert decision["policyBranch"] == "afterUnknown"


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
    create_workflow_run(
        project,
        "Validate a write-capable collaboration flow.",
        alias=record.alias,
        integration="codex",
    )
    for stage in ("specify", "clarify", "plan", "tasks", "implement", "validate"):
        transition_workflow(
            project,
            record.alias,
            stage=stage,
            outcome="completed",
            handoff_summary="Canonical pre-execution fixture setup.",
        )
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
