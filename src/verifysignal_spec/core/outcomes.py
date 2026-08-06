from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

from .contracts import (
    ALLOWED_CORE_STATUSES,
    CORE_ENTITLEMENT_ERROR_MAP,
    REQUIRED_OPERATIONS,
    core_blocker_code,
    core_public_error_code,
)


PROTECTED_SUCCESS_SCHEMAS = {
    operation: REQUIRED_OPERATIONS[operation][0]
    for operation in ("authoring-check", "run")
}
CORE_ERROR_SCHEMA = "verifysignal.error/v1"
KNOWN_PUBLIC_SCHEMAS = {
    CORE_ERROR_SCHEMA,
    *(schema for schema, _version in REQUIRED_OPERATIONS.values()),
}
KNOWN_EXECUTION_PHASES = {
    "pre-execution",
    "execution",
    "post-execution",
}
PUBLIC_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,199}$")
PROTECTED_OPERATION_ERROR_CODES = {
    "authoring-check": {
        "unsupported-placeholder-namespace",
        "unresolved-placeholder-reference",
        "structural-validation-error",
        "undeclared-credential-reference",
        "missing-credential-value",
        "contract-capability-unsupported",
        "invalid-target-composition",
    },
    "run": {
        "browser-assets-unavailable",
        "execution-error",
        "structural-validation-error",
        "replay-origin-mismatch",
    },
}

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


def normalize_core_outcome(operation: str, response: Any) -> NormalizedCoreOutcome:
    """Normalize one protected response using only the public CLI envelope."""

    if not isinstance(response, dict):
        return _contract_invalid(operation, None)

    observed_schema = response.get("schema")
    schema = observed_schema if observed_schema in KNOWN_PUBLIC_SCHEMAS else None
    response_operation = response.get("operation")
    status = response.get("status")
    expected_schema = PROTECTED_SUCCESS_SCHEMAS.get(operation)
    expected_version = REQUIRED_OPERATIONS.get(operation, (None, None))[1]
    data = response.get("data")

    if (
        expected_schema is not None
        and schema == expected_schema
        and response.get("schemaVersion") == expected_version
        and response_operation == operation
        and status in ALLOWED_CORE_STATUSES
        and isinstance(data, dict)
        and (operation != "run" or public_run_id(response) is not None)
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
        and response.get("schemaVersion") == 1
        and response_operation == operation
        and status == "error"
    ):
        error_code = _safe_error_code(operation, core_public_error_code(response))
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
        or phase not in KNOWN_EXECUTION_PHASES
        or not isinstance(side_effect, bool)
    ):
        return False, None, None, None
    return True, started, phase, side_effect


def _path_safe_run_id(value: Any) -> bool:
    return isinstance(value, str) and bool(PUBLIC_RUN_ID_RE.fullmatch(value))


def public_run_id(response: Any) -> str | None:
    """Return a non-conflicting run identity from current or legacy envelopes."""

    if not isinstance(response, dict):
        return None
    data = response.get("data")
    if not isinstance(data, dict):
        return None
    summary = data.get("summary")
    summary_run_id = summary.get("runId") if isinstance(summary, dict) else None
    legacy_run_id = data.get("runId")
    candidates = [
        value
        for value in (summary_run_id, legacy_run_id)
        if value is not None
    ]
    if not candidates or any(not _path_safe_run_id(value) for value in candidates):
        return None
    if len(set(candidates)) != 1:
        return None
    return str(candidates[0])


def _safe_error_code(operation: str, value: str | None) -> str | None:
    if value is None:
        return None
    public_codes = {
        *CORE_ENTITLEMENT_ERROR_MAP,
        *PROTECTED_OPERATION_ERROR_CODES.get(operation, set()),
    }
    return value if value in public_codes else "core.error"


def _contract_invalid(operation: str, schema: str | None) -> NormalizedCoreOutcome:
    return NormalizedCoreOutcome(
        operation=operation,
        kind="contract-invalid",
        schema=schema,
        status="error",
        blockerCode="core.contract-invalid",
    )
