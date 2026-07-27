from __future__ import annotations

from pathlib import Path
from typing import Any

from verifysignal_spec.core.adapter import CoreAdapter
from verifysignal_spec.runtime.entitlement import load_receipt, receipt_status
from verifysignal_spec.runtime.env_file import (
    EnvironmentFileError,
    declared_environment_keys_for_run_request,
    load_environment_file,
    resolve_environment_file_path,
)
from verifysignal_spec.runtime.resolver import ensure_core_runtime
from verifysignal_spec.workflows.target_confirmation import (
    record_for_run_request,
    target_confirmation_blocker,
)


def run(
    project: Path,
    run_request: Path,
    skills: list[Path],
    *,
    headed: bool = False,
    slow_mo_ms: int = 0,
    core_cmd: str | None = None,
    api_base_url: str | None = None,
    env_file: Path | None = None,
) -> dict[str, Any]:
    """Invoke Core's optional stateful pre-commit probe operation."""
    if not skills:
        raise ValueError("Probe requires at least one --skill path.")
    record = record_for_run_request(project, run_request)
    blocker = target_confirmation_blocker(project, record) if record else None
    if blocker:
        return {
            "status": "blocked",
            "message": blocker["message"],
            "requiresConfirmation": True,
            "blockers": [blocker],
            "nextCommand": blocker["recoveryCommand"],
        }
    environment_values: dict[str, str] = {}
    if env_file:
        try:
            environment_values = load_environment_file(
                resolve_environment_file_path(project, env_file),
                declared_keys=declared_environment_keys_for_run_request(
                    project,
                    run_request,
                ),
            )
        except EnvironmentFileError as exc:
            return {
                "status": "blocked",
                "message": exc.message,
                "blockers": [exc.blocker()],
                "valuesIncluded": False,
            }
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
        env=environment_values,
        entitlement_receipt=_valid_receipt_path(),
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


def _valid_receipt_path() -> str | None:
    receipt = load_receipt()
    if not receipt:
        return None
    status = receipt_status(receipt)
    return status.receiptPath if status.status == "valid" else None
