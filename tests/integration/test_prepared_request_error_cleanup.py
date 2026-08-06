from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tests.fixtures.workflows.entitlement_preflight_recovery import (
    build_protected_readiness_snapshot,
)
from tests.fixtures.workflows.prerequisites import create_current_understanding_workspace
from tests.fixtures.workflows.side_effect_contract_alignment import create_write_policy_workspace
from tests.helpers import (
    FAKE_CORE,
    assert_exact_workspace_file_changes,
    assert_secret_canary_absent,
    workspace_file_snapshot,
)
from verifysignal_spec.commands import run as run_command
from verifysignal_spec.commands.run_request_preparation import (
    cleanup_owned_prepared_run_request,
    write_owned_prepared_run_request,
)
from verifysignal_spec.workspace import layout
from verifysignal_spec.workspace import repository as workspace_repository
from verifysignal_spec.workspace.repository import (
    load_use_case,
    now_iso,
    save_document,
    save_use_case,
)
from verifysignal_spec.workflows.engine import create_workflow_run
from verifysignal_spec.workflows.repository import load_active_workflow_run
from verifysignal_spec.workflows.transitions import transition_workflow
from verifysignal_spec.workflows.write_safety import evaluate_rerun_decision


FIXED_NOW = "2026-08-05T01:02:03Z"


def test_core_error_removes_only_the_exact_new_prepared_request(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    alias = _prepare_cleanup_workspace(tmp_path, monkeypatch)
    run_dir = _run_dir(tmp_path, alias)
    run_dir.mkdir(parents=True, exist_ok=True)
    neighbor = run_dir / "neighbor.run-request.json"
    neighbor.write_text('{"owner":"neighbor"}\n', encoding="utf-8")
    canonical = layout.run_request_path(tmp_path, alias)
    before = {neighbor: neighbor.read_bytes(), canonical: canonical.read_bytes()}
    workspace_before = workspace_file_snapshot(tmp_path)
    transient = run_dir / f"{alias}-20260805T010203Z.run-request.json"
    workflow_run = load_active_workflow_run(tmp_path, alias)
    assert workflow_run is not None

    monkeypatch.setattr(
        workspace_repository,
        "now_iso",
        lambda: "2026-08-05T01:02:04Z",
    )
    result = run_command.run(tmp_path, alias, interactive=False, core_cmd=str(FAKE_CORE))

    assert result["status"] == "blocked"
    assert transient.exists() is False
    assert sorted(path.name for path in run_dir.glob("*.run-request.json")) == [neighbor.name]
    assert list(run_dir.glob("*.yaml")) == []
    for path, content in before.items():
        assert path.read_bytes() == content
    assert_exact_workspace_file_changes(
        tmp_path,
        workspace_before,
        changed=[
            "registry.yaml",
            f"use-cases/{alias}.yaml",
            f"workflows/runs/{workflow_run.runId}.yaml",
            f"workflows/use-cases/{alias}/state.yaml",
        ],
    )


@pytest.mark.parametrize("failure_boundary", ["adapter", "normalizer"])
def test_exception_before_outcome_classification_releases_and_removes_the_owned_request(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_boundary: str,
) -> None:
    alias = _prepare_cleanup_workspace(tmp_path, monkeypatch)
    transient = _run_dir(tmp_path, alias) / f"{alias}-20260805T010203Z.run-request.json"

    def raise_failure(*_args, **_kwargs):
        raise RuntimeError(f"forced {failure_boundary} failure")

    if failure_boundary == "adapter":
        monkeypatch.setattr(run_command.CoreAdapter, "run", raise_failure)
    else:
        monkeypatch.setattr(
            run_command.CoreAdapter,
            "run",
            lambda *_args, **_kwargs: {
                "schema": "verifysignal.error/v1",
                "schemaVersion": 1,
                "operation": "run",
                "status": "error",
                "error": {"code": "entitlement.key-unknown"},
            },
        )
        monkeypatch.setattr(run_command, "normalize_core_outcome", raise_failure)

    with pytest.raises(RuntimeError, match=f"forced {failure_boundary} failure"):
        run_command.run(tmp_path, alias, interactive=False, core_cmd=str(FAKE_CORE))

    assert transient.exists() is False
    assert list(_run_dir(tmp_path, alias).glob("*.run-request.json")) == []
    assert list(_run_dir(tmp_path, alias).glob("*.yaml")) == []
    attempt = load_use_case(tmp_path, alias).lastCoreAttempt
    assert attempt is not None
    assert attempt.operation == "run"
    assert attempt.status == "error"
    assert attempt.executionState == "unknown"
    assert attempt.sideEffectMayExist is None
    rerun = evaluate_rerun_decision(load_use_case(tmp_path, alias))
    assert rerun["decision"] == "requires-confirmation"
    assert rerun["outcomeClass"] == "unknown-write"
    assert rerun["policyBranch"] == "afterUnknown"


def test_preexisting_exact_prepared_path_is_never_overwritten_or_deleted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    alias = _prepare_cleanup_workspace(tmp_path, monkeypatch)
    run_dir = _run_dir(tmp_path, alias)
    run_dir.mkdir(parents=True, exist_ok=True)
    preexisting = run_dir / f"{alias}-20260805T010203Z.run-request.json"
    preexisting.write_text('{"owner":"user-authored"}\n', encoding="utf-8")
    original = preexisting.read_bytes()

    result = run_command.run(tmp_path, alias, interactive=False, core_cmd=str(FAKE_CORE))

    assert result["status"] == "blocked"
    assert preexisting.read_bytes() == original
    assert list(run_dir.glob("*.yaml")) == []


def test_cleanup_refuses_a_prepared_path_outside_the_project_workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    alias = _prepare_cleanup_workspace(tmp_path, monkeypatch)
    outside = tmp_path.parent / f"{tmp_path.name}-outside-user-owned.json"
    outside.write_text('{"owner":"outside"}\n', encoding="utf-8")
    original = outside.read_bytes()
    monkeypatch.setattr(
        run_command,
        "write_prepared_run_request",
        lambda _output_dir, _run_id, _document: outside,
    )

    result = run_command.run(tmp_path, alias, interactive=False, core_cmd=str(FAKE_CORE))

    assert result["status"] == "blocked"
    assert outside.read_bytes() == original
    assert list(_run_dir(tmp_path, alias).glob("*.yaml")) == []


def test_core_error_output_attempt_marker_and_workspace_are_secret_safe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    alias = _prepare_cleanup_workspace(tmp_path, monkeypatch)
    canary = "VS_TEST_SECRET_DO_NOT_PERSIST_4f89fbb1"
    env_file = tmp_path / "approved-test.env"
    env_file.write_text(f"APP_TEST_PASSWORD={canary}\n", encoding="utf-8")
    os.chmod(env_file, 0o600)

    result = run_command.run(
        tmp_path,
        alias,
        interactive=False,
        core_cmd=str(FAKE_CORE),
        env_file=env_file,
    )

    assert result["status"] == "blocked"
    assert list(_run_dir(tmp_path, alias).glob("*.yaml")) == []
    assert list(_run_dir(tmp_path, alias).glob("*.run-request.json")) == []
    assert_secret_canary_absent(tmp_path, canary, json.dumps(result, sort_keys=True))


@pytest.mark.parametrize(
    "data",
    [
        [],
        {},
        {"runId": ""},
        {"runId": "../escaped"},
        {"runId": "../../outside"},
        {"runId": "nested/escaped"},
    ],
)
def test_contract_invalid_run_envelopes_never_create_history_or_escape_the_run_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    data: object,
) -> None:
    alias = _prepare_cleanup_workspace(tmp_path, monkeypatch)
    workspace_before = workspace_file_snapshot(tmp_path)

    def invalid_run_response(_self, *_args, **_kwargs):
        return {
            "schema": "verifysignal.run/v1",
            "schemaVersion": 1,
            "operation": "run",
            "status": "passed",
            "data": data,
        }

    monkeypatch.setattr(run_command.CoreAdapter, "run", invalid_run_response)

    result = run_command.run(tmp_path, alias, interactive=False, core_cmd=str(FAKE_CORE))

    assert result["status"] == "blocked"
    assert result["blockers"][0]["code"] == "core.contract-invalid"
    assert result["nextAction"] == "verifysignal core update --json"
    assert list(_run_dir(tmp_path, alias).glob("*.yaml")) == []
    assert list(_run_dir(tmp_path, alias).glob("*.run-request.json")) == []
    assert (tmp_path / ".verifysignal" / "escaped.yaml").exists() is False
    assert (tmp_path / "outside.yaml").exists() is False
    changed = set(workspace_file_snapshot(tmp_path)) - set(workspace_before)
    assert not any(path.endswith(".yaml") and "/runs/" in path for path in changed)


@pytest.mark.parametrize("tainted_field", ["schema", "errorCode"])
def test_untrusted_core_identifiers_are_redacted_from_output_and_attempt_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tainted_field: str,
) -> None:
    alias = _prepare_cleanup_workspace(tmp_path, monkeypatch)
    canary = f"VS_TEST_SECRET_DO_NOT_PERSIST_{tainted_field}_b6ec90"

    def tainted_response(_self, *_args, **_kwargs):
        if tainted_field == "schema":
            return {
                "schema": canary,
                "schemaVersion": 1,
                "operation": "run",
                "status": "passed",
                "data": {"runId": "safe-run"},
            }
        return {
            "schema": "verifysignal.error/v1",
            "schemaVersion": 1,
            "operation": "run",
            "status": "error",
            "error": {"code": canary},
            "execution": {
                "started": False,
                "phase": "pre-execution",
                "sideEffectMayExist": False,
            },
        }

    monkeypatch.setattr(run_command.CoreAdapter, "run", tainted_response)

    result = run_command.run(tmp_path, alias, interactive=False, core_cmd=str(FAKE_CORE))

    assert result["status"] == "blocked"
    assert list(_run_dir(tmp_path, alias).glob("*.yaml")) == []
    assert_secret_canary_absent(tmp_path, canary, json.dumps(result, sort_keys=True))


def test_prepared_writer_refuses_a_symlinked_runs_root(tmp_path: Path) -> None:
    workspace = tmp_path / ".verifysignal"
    workspace.mkdir(parents=True)
    outside = tmp_path / "outside-user-files"
    outside.mkdir()
    (workspace / "runs").symlink_to(outside, target_is_directory=True)

    ownership = write_owned_prepared_run_request(
        tmp_path,
        workspace / "runs" / "alias",
        "attempt",
        {"safe": True},
    )

    assert ownership.createdByThisInvocation is False
    assert list(outside.rglob("*")) == []


def test_direct_run_refuses_a_symlinked_runs_root_before_core_invocation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    alias = _prepare_cleanup_workspace(tmp_path, monkeypatch)
    runs_root = tmp_path / ".verifysignal" / "runs"
    if runs_root.exists():
        runs_root.rmdir()
    outside = tmp_path / "outside-user-files"
    outside.mkdir()
    runs_root.symlink_to(outside, target_is_directory=True)
    core_calls = 0

    def core_spy(_self, *_args, **_kwargs):
        nonlocal core_calls
        core_calls += 1
        raise AssertionError("Core must not run when prepared-request ownership is refused")

    monkeypatch.setattr(run_command.CoreAdapter, "run", core_spy)

    result = run_command.run(tmp_path, alias, interactive=False, core_cmd=str(FAKE_CORE))

    assert result["status"] == "blocked"
    assert result["blockers"][0]["code"] == "runtime.prepared-request-ownership-refused"
    assert core_calls == 0
    assert list(outside.rglob("*")) == []


def test_prepared_writer_uses_exclusive_creation_after_a_name_collision(tmp_path: Path) -> None:
    output_dir = tmp_path / ".verifysignal" / "runs" / "alias"
    output_dir.mkdir(parents=True)
    existing = output_dir / "attempt.run-request.json"
    existing.write_text('{"owner":"user"}\n', encoding="utf-8")
    original = existing.read_bytes()

    ownership = write_owned_prepared_run_request(
        tmp_path,
        output_dir,
        "attempt",
        {"safe": True},
    )

    assert ownership.createdByThisInvocation is True
    assert ownership.path.name == "attempt.1.run-request.json"
    assert existing.read_bytes() == original
    assert cleanup_owned_prepared_run_request(tmp_path, ownership) is True
    assert existing.read_bytes() == original


def test_cleanup_stays_anchored_when_the_created_directory_path_is_replaced(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / ".verifysignal" / "runs" / "alias"
    ownership = write_owned_prepared_run_request(
        tmp_path,
        output_dir,
        "attempt",
        {"safe": True},
    )
    assert ownership.createdByThisInvocation is True
    detached = output_dir.with_name("alias-detached")
    output_dir.rename(detached)
    output_dir.mkdir()
    replacement = output_dir / ownership.path.name
    replacement.write_text('{"owner":"replacement"}\n', encoding="utf-8")
    replacement_bytes = replacement.read_bytes()

    removed = cleanup_owned_prepared_run_request(tmp_path, ownership)

    assert removed is True
    assert replacement.read_bytes() == replacement_bytes
    assert (detached / ownership.path.name).exists() is False


def _prepare_cleanup_workspace(
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> str:
    monkeypatch.setenv("VERIFYSIGNAL_CORE_CMD", str(FAKE_CORE))
    monkeypatch.setenv("FAKE_VERIFYSIGNAL_MODE", "current-entitlement-error")
    monkeypatch.setenv("VERIFYSIGNAL_RUNTIME_CACHE_DIR", str(project / "runtime-cache"))
    monkeypatch.setattr(run_command, "now_iso", lambda: FIXED_NOW)
    create_current_understanding_workspace(project)
    record = create_write_policy_workspace(project)
    record.status = "ready"
    record.credentialRefs = {
        "app": {
            "source": "environment",
            "keys": {"password": "APP_TEST_PASSWORD"},
        }
    }
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
            handoff_summary="Canonical prepared-request fixture setup.",
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


def _run_dir(project: Path, alias: str) -> Path:
    return layout.workspace_root(project) / layout.RUNS_DIR / alias
