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
from verifysignal_spec.workspace import layout
from verifysignal_spec.workspace.repository import now_iso, save_document, save_use_case


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
        changed=[f"use-cases/{alias}.yaml"],
    )


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
