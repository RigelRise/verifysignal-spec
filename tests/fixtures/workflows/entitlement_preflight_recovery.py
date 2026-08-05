from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from verifysignal_spec import __version__ as SPEC_VERSION
from verifysignal_spec.workspace import layout
from verifysignal_spec.workspace.repository import (
    artifact_fingerprints,
    init_workspace,
    load_document,
    load_use_case,
    now_iso,
    save_document,
    save_use_case,
)


CommandCompatibilityStatus = Literal["not-checked", "passed", "blocked"]
TrustMaterialStatus = Literal["not-checked", "ready", "blocked"]
ProtectedOperationStatus = Literal["not-checked", "passed", "blocked"]
ReadinessScope = Literal["command-and-trust-inputs", "protected-operation"]
SideEffectClass = Literal["none", "authenticated-read", "write", "external-notification"]
AggregateReadinessStatus = Literal["ready", "not-checked", "stale", "needs-validate", "blocked", "unknown"]


def create_fresh_workspace_root(project: Path) -> Path:
    """Create a project directory that has never contained a Spec workspace."""
    project.mkdir(parents=True, exist_ok=True)
    workspace_path = layout.workspace_root(project) / layout.WORKSPACE_FILE
    if workspace_path.exists():
        raise ValueError("Fresh-workspace fixture requires an absent workspace file.")
    return project


def create_legacy_field_absent_workspace(project: Path) -> Path:
    """Create a durable legacy workspace whose runtime-mode field is absent."""
    project.mkdir(parents=True, exist_ok=True)
    init_workspace(project)
    workspace_path = layout.workspace_root(project) / layout.WORKSPACE_FILE
    workspace = load_document(workspace_path, default={}) or {}
    workspace.pop("coreResolutionMode", None)
    save_document(workspace_path, workspace)
    return project


def build_protected_readiness_snapshot(
    alias: str,
    *,
    status: AggregateReadinessStatus = "ready",
    command_status: CommandCompatibilityStatus = "passed",
    trust_status: TrustMaterialStatus = "ready",
    protected_status: ProtectedOperationStatus = "passed",
    readiness_scope: ReadinessScope = "protected-operation",
    side_effect_class: SideEffectClass = "none",
) -> dict[str, Any]:
    """Return a production-shaped readiness document with explicit layers."""
    return {
        "schemaVersion": "verifysignal-spec-readiness-snapshot/v1",
        "alias": alias,
        "status": status,
        "checkedAt": "2026-08-05T00:00:00Z",
        "artifactFingerprints": {},
        "specVersion": SPEC_VERSION,
        "artifactContractVersion": "verifysignal-spec-use-case/v1",
        "targetProjectRevision": None,
        "testedCodeScopeStatus": "unknown",
        "environmentBoundCredentialGroups": [],
        "sideEffectClass": side_effect_class,
        "commandCompatibilityStatus": command_status,
        "trustMaterialStatus": trust_status,
        "protectedOperationStatus": protected_status,
        "readinessScope": readiness_scope,
    }


def save_protected_ready_snapshot(
    project: Path,
    alias: str,
    *,
    side_effect_class: SideEffectClass = "none",
) -> None:
    """Make an intentionally runnable fixture explicit about protected readiness."""

    record = load_use_case(project, alias)
    record.status = "ready"
    save_use_case(project, record)
    snapshot = build_protected_readiness_snapshot(
        alias,
        side_effect_class=side_effect_class,
    )
    snapshot["checkedAt"] = now_iso()
    snapshot["artifactFingerprints"] = artifact_fingerprints(project, record)
    save_document(layout.readiness_snapshot_path(project, alias), snapshot)


def build_side_effect_policy(
    *,
    side_effect_class: SideEffectClass = "none",
    mode: Literal["enforce", "warn", "observe"] = "observe",
    commit_step_id: str | None = None,
    allowed: list[dict[str, Any]] | None = None,
    forbidden: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return a secret-free canonical side-effect policy for scenario tests."""
    policy: dict[str, Any] = {
        "class": side_effect_class,
        "mode": mode,
        "allowed": list(allowed or []),
        "forbidden": list(forbidden or []),
    }
    if commit_step_id is not None:
        policy["commitStepId"] = commit_step_id
    return policy
