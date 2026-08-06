from __future__ import annotations

from pathlib import Path
from typing import Any

from verifysignal_spec.core.adapter import CoreAdapter
from verifysignal_spec.runtime.entitlement import api_base_url_for_runtime, valid_receipt_path
from verifysignal_spec.runtime.resolver import ensure_core_runtime


def run(
    project: Path,
    run_dir: Path,
    *,
    out: Path | None = None,
    core_cmd: str | None = None,
    api_base_url: str | None = None,
) -> dict[str, Any]:
    """Crystallize a completed run into a reusable fixture via Core's `crystallize`.

    Unlike `discover`, crystallization is entitlement-PROTECTED: it reads private run evidence, so it
    resolves through the protected runtime context and hands Core a receipt exactly like `run` does.
    Passing the receipt only when it is currently valid keeps the rejection Core's to make.

    The resolver context also declares the required optional capability (see
    CONTEXT_REQUIRED_CAPABILITY), so a compatible Core that does not advertise
    verifysignal.crystallize/v1 is reported as a capability blocker instead of being invoked and
    crashing on an unknown subcommand.
    """
    managed_runtime = ensure_core_runtime(
        project,
        explicit_core_cmd=core_cmd,
        api_base_url=api_base_url,
        context="crystallize",
    )
    if managed_runtime.status != "ready":
        return _runtime_setup_blocked_payload(managed_runtime)
    entitlement_api_base_url = api_base_url_for_runtime(managed_runtime, api_base_url)
    return CoreAdapter(executable=managed_runtime.runtimeCommand, cwd=project).crystallize(
        run_dir=run_dir,
        out=out,
        entitlement_receipt=valid_receipt_path(entitlement_api_base_url),
        entitlement_api_base_url=entitlement_api_base_url,
    )


def _runtime_setup_blocked_payload(managed_runtime: Any) -> dict[str, Any]:
    runtime_payload = managed_runtime.to_dict()
    blockers = runtime_payload.get("blockers", [])
    is_core_missing = any(blocker.get("code") == "core.missing" for blocker in blockers)
    return {
        "status": "blocked",
        "message": "Crystallize requires a resolved VerifySignal Core runtime; Core setup is required."
        if is_core_missing
        else "Crystallize requires a resolved VerifySignal Core runtime.",
        "managedRuntimeReadiness": runtime_payload,
        "blockers": blockers,
        "nextCommand": managed_runtime.nextAction,
    }
