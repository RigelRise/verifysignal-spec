from __future__ import annotations

from pathlib import Path

from tests.fixtures.workflows.entitlement_preflight_recovery import (
    create_fresh_workspace_root,
    create_legacy_field_absent_workspace,
)
from verifysignal_spec.workspace import layout
from verifysignal_spec.workspace.repository import (
    get_core_resolution_mode,
    init_workspace,
    load_document,
)


def test_genuinely_new_workspace_persists_managed_only_mode(tmp_path: Path) -> None:
    project = create_fresh_workspace_root(tmp_path / "new-project")

    created = init_workspace(project)
    persisted = load_document(layout.workspace_root(project) / layout.WORKSPACE_FILE)

    assert created["coreResolutionMode"] == "managed-only"
    assert persisted["coreResolutionMode"] == "managed-only"
    assert get_core_resolution_mode(project) == "managed-only"


def test_preexisting_field_absent_workspace_remains_legacy_auto(tmp_path: Path) -> None:
    project = create_legacy_field_absent_workspace(tmp_path / "legacy-project")
    workspace_path = layout.workspace_root(project) / layout.WORKSPACE_FILE

    assert "coreResolutionMode" not in load_document(workspace_path)
    assert get_core_resolution_mode(project) == "legacy-auto"

    init_workspace(project, force=True)

    assert "coreResolutionMode" not in load_document(workspace_path)
    assert get_core_resolution_mode(project) == "legacy-auto"
