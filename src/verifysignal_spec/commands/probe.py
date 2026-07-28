from __future__ import annotations

from pathlib import Path
from typing import Any

from verifysignal_spec.core.adapter import CoreAdapter
from verifysignal_spec.runtime.entitlement import api_base_url_for_runtime, valid_receipt_path
from verifysignal_spec.runtime.resolver import ensure_core_runtime


def run(
    project: Path,
    run_request: Path,
    skills: list[Path],
    *,
    headed: bool = False,
    slow_mo_ms: int = 0,
    core_cmd: str | None = None,
    api_base_url: str | None = None,
) -> dict[str, Any]:
    """Invoke Core's optional stateful pre-commit probe operation."""
    if not skills:
        raise ValueError("Probe requires at least one --skill path.")
    managed_runtime = ensure_core_runtime(
        project,
        explicit_core_cmd=core_cmd,
        api_base_url=api_base_url,
        context="probe",
    )
    if managed_runtime.status != "ready":
        return _runtime_setup_blocked_payload(managed_runtime)
    return CoreAdapter(executable=managed_runtime.runtimeCommand, cwd=project).probe(
        run_request=run_request,
        main_skill=skills[0],
        skills=skills,
        headed=headed,
        slow_mo_ms=slow_mo_ms,
        entitlement_receipt=valid_receipt_path(
            api_base_url_for_runtime(managed_runtime, api_base_url),
        ),
    )


def _runtime_setup_blocked_payload(managed_runtime: Any) -> dict[str, Any]:
    runtime_payload = managed_runtime.to_dict()
    blockers = runtime_payload.get("blockers", [])
    is_core_missing = any(blocker.get("code") == "core.missing" for blocker in blockers)
    return {
        "status": "blocked",
        "message": "Probe requires a resolved VerifySignal Core runtime; Core setup is required."
        if is_core_missing
        else "Probe requires a Core runtime advertising verifysignal.probe/v1.",
        "managedRuntimeReadiness": runtime_payload,
        "blockers": blockers,
        "nextCommand": managed_runtime.nextAction,
    }
