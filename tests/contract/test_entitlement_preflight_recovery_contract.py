from __future__ import annotations

from typing import Any

from verifysignal_spec.core.contracts import REQUIRED_OPERATIONS
from verifysignal_spec.workspace.models import ReadinessSnapshot
from verifysignal_spec.workflows.models import RuntimeReadinessCheck


EXPECTED_PROTECTED_SCHEMAS = {
    "authoring-check": "verifysignal.authoring-check/v1",
    "run": "verifysignal.run/v1",
}

NORMALIZED_OUTCOME_FIELDS = {
    "operation",
    "kind",
    "schema",
    "status",
    "errorCode",
    "blockerCode",
    "executionKnown",
    "executionStarted",
    "executionPhase",
    "sideEffectMayExist",
    "eligibleForRunPersistence",
}


def _normalize(operation: str, response: dict[str, Any]) -> dict[str, Any]:
    from verifysignal_spec.core.outcomes import normalize_core_outcome

    return normalize_core_outcome(operation, response).to_dict()


def test_protected_success_schemas_track_the_existing_public_operation_contract() -> None:
    assert {
        operation: REQUIRED_OPERATIONS[operation][0]
        for operation in EXPECTED_PROTECTED_SCHEMAS
    } == EXPECTED_PROTECTED_SCHEMAS

    for operation, schema in EXPECTED_PROTECTED_SCHEMAS.items():
        data = {"runId": "contract-run-1"} if operation == "run" else {}
        outcome = _normalize(
            operation,
            {
                "schema": schema,
                "schemaVersion": 1,
                "operation": operation,
                "status": "passed",
                "data": data,
            },
        )
        assert outcome["kind"] == "success"
        assert outcome["schema"] == schema


def test_current_public_error_normalizes_to_the_additive_redacted_shape() -> None:
    outcome = _normalize(
        "run",
        {
            "schema": "verifysignal.error/v1",
            "schemaVersion": 1,
            "operation": "run",
            "status": "error",
            "error": {"code": "entitlement.key-unknown"},
            "execution": {
                "started": False,
                "phase": "pre-execution",
                "sideEffectMayExist": False,
            },
        },
    )

    assert set(outcome) == NORMALIZED_OUTCOME_FIELDS
    assert outcome["schema"] == "verifysignal.error/v1"
    assert outcome["kind"] == "core-error"
    assert outcome["blockerCode"] == "entitlement.unverifiable"
    assert outcome["executionKnown"] is True
    assert outcome["eligibleForRunPersistence"] is False


def test_readiness_snapshot_v1_keeps_its_schema_and_emits_additive_layers() -> None:
    snapshot = ReadinessSnapshot(
        alias="localized-home",
        status="ready",
        checkedAt="2026-08-05T00:00:00Z",
        commandCompatibilityStatus="passed",
        trustMaterialStatus="ready",
        protectedOperationStatus="passed",
        readinessScope="protected-operation",
    ).to_dict()

    assert snapshot["schemaVersion"] == "verifysignal-spec-readiness-snapshot/v1"
    assert snapshot["commandCompatibilityStatus"] == "passed"
    assert snapshot["trustMaterialStatus"] == "ready"
    assert snapshot["protectedOperationStatus"] == "passed"
    assert snapshot["readinessScope"] == "protected-operation"


def test_runtime_readiness_projection_emits_the_same_additive_layers() -> None:
    readiness = RuntimeReadinessCheck(
        useCaseAlias="localized-home",
        status="passed",
        commandCompatibilityStatus="passed",
        trustMaterialStatus="ready",
        protectedOperationStatus="passed",
        readinessScope="protected-operation",
    ).to_dict()

    assert readiness["commandCompatibilityStatus"] == "passed"
    assert readiness["trustMaterialStatus"] == "ready"
    assert readiness["protectedOperationStatus"] == "passed"
    assert readiness["readinessScope"] == "protected-operation"


def test_unknown_or_operation_mismatched_schema_uses_contract_invalid_blocker() -> None:
    for response in (
        {
            "schema": "verifysignal.unknown/v1",
            "schemaVersion": 1,
            "operation": "run",
            "status": "passed",
            "data": {},
        },
        {
            "schema": "verifysignal.run/v1",
            "schemaVersion": 1,
            "operation": "authoring-check",
            "status": "passed",
            "data": {},
        },
    ):
        outcome = _normalize("run", response)
        assert outcome["kind"] == "contract-invalid"
        assert outcome["blockerCode"] == "core.contract-invalid"
        assert outcome["eligibleForRunPersistence"] is False
