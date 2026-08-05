from __future__ import annotations

import os
from pathlib import Path

from helpers import FAKE_CORE
from tests.fixtures.managed_runtime import write_fake_core_executable
from tests.fixtures.workflows.entitlement_preflight_recovery import create_fresh_workspace_root

from verifysignal_spec.runtime import resolver as runtime_resolver
from verifysignal_spec.runtime.resolver import ensure_core_runtime
from verifysignal_spec.workspace import layout
from verifysignal_spec.workspace.repository import (
    get_core_resolution_mode,
    init_workspace,
    load_document,
    save_core_configuration,
    save_document,
)


def test_explicit_core_command_wins_before_managed_sources(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VERIFYSIGNAL_RUNTIME_CACHE_DIR", str(tmp_path / "cache"))

    result = ensure_core_runtime(tmp_path, explicit_core_cmd=str(FAKE_CORE))

    assert result.status == "ready"
    assert result.source == "explicit"
    assert result.runtimeCommand == str(FAKE_CORE)


def test_workspace_core_command_wins_over_environment(tmp_path: Path, monkeypatch) -> None:
    init_workspace(tmp_path)
    save_core_configuration(tmp_path, str(FAKE_CORE), source="workspace", version="0.1.0")
    monkeypatch.setenv("VERIFYSIGNAL_CORE_CMD", "missing-env-core")

    result = ensure_core_runtime(tmp_path)

    assert result.status == "ready"
    assert result.source == "workspace"


def test_terminal_workspace_candidate_does_not_scan_ancestor_siblings(
    tmp_path: Path,
    monkeypatch,
) -> None:
    init_workspace(tmp_path)
    save_core_configuration(
        tmp_path,
        "missing-workspace-core",
        source="workspace",
        version="0.1.0",
    )

    def fail_ancestor_scan(_project: Path) -> list[Path]:
        raise AssertionError("terminal workspace resolution must not scan ancestor siblings")

    monkeypatch.setattr(runtime_resolver, "_ancestor_sibling_paths", fail_ancestor_scan)

    result = ensure_core_runtime(tmp_path)

    assert result.status == "blocked"
    assert [attempt.source for attempt in result.attempts] == ["workspace"]


def test_verifysignal_core_path_candidate_is_selected(tmp_path: Path, monkeypatch) -> None:
    bin_dir = tmp_path / "bin"
    core = write_fake_core_executable(bin_dir / "verifysignal-core")
    monkeypatch.delenv("VERIFYSIGNAL_CORE_CMD", raising=False)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setenv("VERIFYSIGNAL_RUNTIME_CACHE_DIR", str(tmp_path / "cache"))

    result = ensure_core_runtime(tmp_path)

    assert result.status == "ready"
    assert result.source == "path"
    assert result.runtimeCommand == str(core)


def test_public_verifysignal_path_candidate_is_not_selected_as_core(tmp_path: Path, monkeypatch) -> None:
    bin_dir = tmp_path / "bin"
    public_cli = write_fake_core_executable(bin_dir / "verifysignal")
    monkeypatch.delenv("VERIFYSIGNAL_CORE_CMD", raising=False)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setenv("VERIFYSIGNAL_RUNTIME_CACHE_DIR", str(tmp_path / "cache"))

    result = ensure_core_runtime(tmp_path)

    assert result.runtimeCommand != str(public_cli)
    assert all(attempt.source != "path" or attempt.command != str(public_cli) for attempt in result.attempts)


def test_managed_only_excludes_workspace_environment_path_and_ancestor_candidates(tmp_path: Path, monkeypatch) -> None:
    init_workspace(tmp_path)
    workspace_path = layout.workspace_root(tmp_path) / layout.WORKSPACE_FILE
    workspace = load_document(workspace_path)
    workspace["coreResolutionMode"] = "managed-only"
    workspace["coreCommand"] = "workspace-core"
    save_document(workspace_path, workspace)
    monkeypatch.setenv("VERIFYSIGNAL_CORE_CMD", "environment-core")
    monkeypatch.setattr(runtime_resolver.shutil, "which", lambda _name: "/fixture/path/verifysignal-core")
    monkeypatch.setattr(runtime_resolver, "_ancestor_sibling_paths", lambda _project: [Path("/fixture/ancestor/verifysignal")])

    candidates = runtime_resolver._override_candidates(
        tmp_path,
        None,
        managed_only=get_core_resolution_mode(tmp_path) == "managed-only",
    )

    assert candidates == []
    assert runtime_resolver._override_candidates(tmp_path, "explicit-core", managed_only=True) == [
        ("explicit", "explicit-core")
    ]


def test_fresh_workspace_mode_excludes_all_ambient_local_candidates(tmp_path: Path, monkeypatch) -> None:
    project = create_fresh_workspace_root(tmp_path / "new-project")
    init_workspace(project)
    workspace_path = layout.workspace_root(project) / layout.WORKSPACE_FILE
    workspace = load_document(workspace_path)
    workspace["coreCommand"] = "workspace-core"
    save_document(workspace_path, workspace)
    monkeypatch.setenv("VERIFYSIGNAL_CORE_CMD", "environment-core")
    monkeypatch.setattr(runtime_resolver.shutil, "which", lambda _name: "/fixture/path/verifysignal-core")
    monkeypatch.setattr(runtime_resolver, "_ancestor_sibling_paths", lambda _project: [Path("/fixture/ancestor/verifysignal")])

    mode = get_core_resolution_mode(project)
    candidates = runtime_resolver._override_candidates(project, None, managed_only=mode == "managed-only")

    assert mode == "managed-only"
    assert candidates == []
