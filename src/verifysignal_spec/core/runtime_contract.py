from __future__ import annotations

from pathlib import Path

from verifysignal_spec.runtime.models import ManagedRuntimeReadinessResult
from verifysignal_spec.runtime.resolver import ensure_core_runtime

from .adapter import CoreAdapter
from .errors import CoreExecutionError, CoreIncompatibleError, CoreMissingError
from .executable_contract import project_core_contract


class CoreRuntimeResolutionError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        blocker_code: str = "core.missing",
        recovery_action: str | None = None,
    ) -> None:
        super().__init__(message)
        self.blocker_code = blocker_code
        self.recovery_action = recovery_action


def resolve_core_runtime(
    project: Path,
    *,
    explicit_core_cmd: str | None = None,
    api_base_url: str | None = None,
    context: str = "contracts",
) -> ManagedRuntimeReadinessResult:
    runtime = ensure_core_runtime(
        project,
        explicit_core_cmd=explicit_core_cmd,
        api_base_url=api_base_url,
        context=context,
    )
    if runtime.status == "ready" and runtime.runtimeCommand:
        return runtime
    blocker = runtime.blockers[0] if runtime.blockers else None
    blocker_code = blocker.code if blocker else "core.missing"
    message = (
        runtime.message
        or (blocker.message if blocker else None)
        or "VerifySignal Core runtime is unavailable."
    )
    recovery_action = (
        blocker.recoveryCommand
        if blocker and blocker.recoveryCommand
        else runtime.nextAction
    )
    raise CoreRuntimeResolutionError(
        f"{blocker_code}: {message}",
        blocker_code=blocker_code,
        recovery_action=recovery_action,
    )


def resolve_core_executable_contract(
    project: Path,
    *,
    explicit_core_cmd: str | None = None,
    api_base_url: str | None = None,
    context: str = "contracts",
) -> tuple[dict, ManagedRuntimeReadinessResult]:
    runtime = resolve_core_runtime(
        project,
        explicit_core_cmd=explicit_core_cmd,
        api_base_url=api_base_url,
        context=context,
    )
    adapter = CoreAdapter(executable=runtime.runtimeCommand, cwd=project)
    try:
        raw = adapter.contracts()
    except (CoreMissingError, CoreIncompatibleError, CoreExecutionError) as exc:
        raise CoreRuntimeResolutionError(
            str(exc),
            blocker_code="core-contract.discovery-failed",
            recovery_action=(
                "Upgrade VerifySignal Core or re-run verifysignal init for a "
                "compatible runtime."
            ),
        ) from exc
    return (
        project_core_contract(
            raw,
            runtime_identity=runtime.runtimeCommand,
            core_version=runtime.runtimeVersion,
            public_contract_version=runtime.contractVersion,
        ),
        runtime,
    )
