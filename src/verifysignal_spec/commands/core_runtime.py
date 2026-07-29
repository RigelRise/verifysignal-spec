from __future__ import annotations

from pathlib import Path
from typing import Any

from verifysignal_spec.core.adapter import CoreAdapter
from verifysignal_spec.runtime.cache import load_cache_entry
from verifysignal_spec.runtime.distribution import normalize_platform
from verifysignal_spec.runtime.resolver import ensure_core_runtime
from verifysignal_spec.workspace.repository import (
    get_core_configuration,
    mark_managed_core_checked,
    reset_core_configuration,
    save_managed_core_configuration,
)


def reset(project: Path) -> dict[str, Any]:
    state = reset_core_configuration(project.resolve())
    return {
        "schemaVersion": "verifysignal-spec-core-reset/v1",
        "status": "reset",
        "coreResolutionMode": "managed-only",
        "removedFields": state["removedFields"],
        "managedRuntimeRetained": bool(state["workspace"].get("managedCoreVersion")),
    }


def update(project: Path, *, api_base_url: str | None = None) -> dict[str, Any]:
    project = project.resolve()
    previous = get_core_configuration(project)
    previous_version = previous.get("managedCoreVersion")
    reset_result = reset(project)
    runtime = ensure_core_runtime(
        project,
        api_base_url=api_base_url,
        context="update",
        managed_only=True,
        force_latest=True,
    )
    fallback: dict[str, Any] | None = None
    managed_version = runtime.cache.coreVersion or runtime.runtimeVersion
    if runtime.status == "ready" and managed_version:
        save_managed_core_configuration(
            project,
            managed_version,
            successful_update=True,
        )
        status = "ready"
    else:
        mark_managed_core_checked(project)
        status = "blocked"
        platform = normalize_platform()
        previous_entry = (
            load_cache_entry(
                platform=platform,
                version=str(previous_version),
                api_base_url=api_base_url,
            )
            if platform and previous_version
            else None
        )
        if previous_entry:
            try:
                compatibility = CoreAdapter(
                    executable=previous_entry.runtimeCommand,
                    cwd=project,
                ).check_compatibility()
            except Exception:
                compatibility = None
            if compatibility and compatibility.compatible:
                save_managed_core_configuration(
                    project,
                    previous_entry.coreVersion,
                    successful_update=False,
                )
                fallback = {
                    "status": "active",
                    "source": "managed-cache",
                    "coreVersion": previous_entry.coreVersion,
                    "verified": True,
                }
    return {
        "schemaVersion": "verifysignal-spec-core-update/v1",
        "status": status,
        "coreResolutionMode": "managed-only",
        "reset": reset_result,
        "runtime": runtime.to_dict(),
        "fallback": fallback,
    }


def version(
    project: Path,
    *,
    core_cmd: str | None = None,
    api_base_url: str | None = None,
) -> dict[str, Any]:
    project = project.resolve()
    runtime = ensure_core_runtime(
        project,
        explicit_core_cmd=core_cmd,
        api_base_url=api_base_url,
        context="version",
    )
    if runtime.status != "ready" or not runtime.runtimeCommand:
        return runtime.to_dict()
    return CoreAdapter(executable=runtime.runtimeCommand, cwd=project).version()
