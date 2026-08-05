from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from .contracts import ALLOWED_CORE_STATUSES, REQUIRED_OPERATIONS, core_blocker_code, core_public_error_code


PROTECTED_SUCCESS_SCHEMAS = {
    operation: REQUIRED_OPERATIONS[operation][0]
    for operation in ("authoring-check", "run")
}
CORE_ERROR_SCHEMA = "verifysignal.error/v1"

OutcomeKind = Literal["success", "core-error", "contract-invalid"]


@dataclass(frozen=True, slots=True)
class NormalizedCoreOutcome:
    """Redacted interpretation of a protected public Core response."""

    operation: str
    kind: OutcomeKind
    schema: str | None
    status: str
    errorCode: str | None = None
    blockerCode: str | None = None
    executionKnown: bool = False
    executionStarted: bool | None = None
    executionPhase: str | None = None
    sideEffectMayExist: bool | None = None
    eligibleForRunPersistence: bool = False

    def to_dict(self) -> dict[str, Any]:
        # Keep this as an explicit allowlist. Never copy arbitrary Core fields
        # into a normalized outcome: error messages and nested data may contain
        # receipt, credential, target, or environment material.
        return {
            "operation": self.operation,
            "kind": self.kind,
            "schema": self.schema,
            "status": self.status,
            "errorCode": self.errorCode,
            "blockerCode": self.blockerCode,
            "executionKnown": self.executionKnown,
            "executionStarted": self.executionStarted,
            "executionPhase": self.executionPhase,
            "sideEffectMayExist": self.sideEffectMayExist,
            "eligibleForRunPersistence": self.eligibleForRunPersistence,
        }


def normalize_core_outcome(operation: str, response: dict[str, Any]) -> NormalizedCoreOutcome:
    """Normalize one protected response using only the public CLI envelope."""

    if not isinstance(response, dict):
        return _contract_invalid(operation, None)

    observed_schema = response.get("schema")
    schema = observed_schema if isinstance(observed_schema, str) and observed_schema else None
    response_operation = response.get("operation")
    status = response.get("status")
    expected_schema = PROTECTED_SUCCESS_SCHEMAS.get(operation)

    if (
        expected_schema is not None
        and schema == expected_schema
        and response_operation == operation
        and status in ALLOWED_CORE_STATUSES
    ):
        execution = _execution_projection(response)
        return NormalizedCoreOutcome(
            operation=operation,
            kind="success",
            schema=schema,
            status=status,
            executionKnown=execution[0],
            executionStarted=execution[1],
            executionPhase=execution[2],
            sideEffectMayExist=execution[3],
            eligibleForRunPersistence=operation == "run",
        )

    if (
        expected_schema is not None
        and schema == CORE_ERROR_SCHEMA
        and response_operation == operation
        and status == "error"
    ):
        error_code = core_public_error_code(response)
        execution = _execution_projection(response)
        return NormalizedCoreOutcome(
            operation=operation,
            kind="core-error",
            schema=schema,
            status="error",
            errorCode=error_code,
            blockerCode=core_blocker_code(error_code),
            executionKnown=execution[0],
            executionStarted=execution[1],
            executionPhase=execution[2],
            sideEffectMayExist=execution[3],
            eligibleForRunPersistence=False,
        )

    return _contract_invalid(operation, schema)


def _execution_projection(
    response: dict[str, Any],
) -> tuple[bool, bool | None, str | None, bool | None]:
    execution = response.get("execution")
    if not isinstance(execution, dict):
        return False, None, None, None
    started = execution.get("started")
    phase = execution.get("phase")
    side_effect = execution.get("sideEffectMayExist")
    if (
        not isinstance(started, bool)
        or not isinstance(phase, str)
        or not phase.strip()
        or not isinstance(side_effect, bool)
    ):
        return False, None, None, None
    return True, started, phase, side_effect


def _contract_invalid(operation: str, schema: str | None) -> NormalizedCoreOutcome:
    return NormalizedCoreOutcome(
        operation=operation,
        kind="contract-invalid",
        schema=schema,
        status="error",
        blockerCode="core.contract-invalid",
    )
