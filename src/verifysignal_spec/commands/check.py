from __future__ import annotations

from pathlib import Path
from typing import Any

from verifysignal_spec.integrations.manifests import load_all_states
from verifysignal_spec.runtime.resolver import ensure_core_runtime
from verifysignal_spec.runtime.telemetry import ping_outcome, send_usage_ping
from verifysignal_spec.workspace import layout
from verifysignal_spec.workspace.validation import validate_workspace


def run(project: Path, core_cmd: str | None = None, api_base_url: str | None = None) -> dict[str, Any]:
    workspace_exists = layout.workspace_root(project).exists()
    findings = validate_workspace(project) if workspace_exists else [{"severity": "blocking", "code": "workspace-missing", "message": "Run `verifysignal-spec init` first."}]
    runtime = ensure_core_runtime(
        project,
        explicit_core_cmd=core_cmd,
        api_base_url=api_base_url,
        context="check",
        managed_only=True if not workspace_exists else None,
    )
    core = {
        "available": runtime.status == "ready",
        "compatible": runtime.status == "ready",
        "message": runtime.message,
        "verifysignalVersion": runtime.runtimeVersion,
        "contractVersion": runtime.contractVersion,
        "missingOperations": runtime.missingOperations,
        "incompatibleOperations": runtime.incompatibleOperations,
    }
    integrations = load_all_states(project).get("integrations", {}) if workspace_exists else {}
    status = "passed" if workspace_exists and not any(item.get("severity") == "blocking" for item in findings) and runtime.status == "ready" else "blocked"
    # Fire-and-forget usage heartbeat only when an entitled runtime actually ran the check.
    if runtime.status == "ready":
        send_usage_ping("check", ping_outcome(status), api_base_url=api_base_url)
    return {
        "schemaVersion": "verifysignal-spec-check/v1",
        "status": status,
        "workspace": {"exists": workspace_exists, "path": str(layout.workspace_root(project)), "findings": findings},
        "managedRuntimeReadiness": runtime.to_dict(),
        "core": core,
        "integrations": integrations,
    }
