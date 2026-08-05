from __future__ import annotations

from typing import Any

import pytest


def _normalize(operation: str, response: dict[str, Any]) -> dict[str, Any]:
    from verifysignal_spec.core.outcomes import normalize_core_outcome

    return normalize_core_outcome(operation, response).to_dict()


@pytest.mark.parametrize(
    ("operation", "schema", "eligible_for_run_persistence"),
    [
        ("authoring-check", "verifysignal.authoring-check/v1", False),
        ("run", "verifysignal.run/v1", True),
    ],
)
def test_exact_operation_success_schema_is_required(
    operation: str,
    schema: str,
    eligible_for_run_persistence: bool,
) -> None:
    data = {"runId": "run-20260805T010203Z"} if operation == "run" else {}
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

    assert outcome == {
        "operation": operation,
        "kind": "success",
        "schema": schema,
        "status": "passed",
        "errorCode": None,
        "blockerCode": None,
        "executionKnown": False,
        "executionStarted": None,
        "executionPhase": None,
        "sideEffectMayExist": None,
        "eligibleForRunPersistence": eligible_for_run_persistence,
    }


@pytest.mark.parametrize(
    "response",
    [
        {
            "schema": "verifysignal.authoring-check/v1",
            "schemaVersion": 1,
            "operation": "authoring-check",
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
        {
            "schemaVersion": 1,
            "operation": "run",
            "status": "passed",
            "data": {},
        },
        {
            "schema": "verifysignal.run/v2",
            "schemaVersion": 2,
            "operation": "run",
            "status": "passed",
            "data": {},
        },
    ],
)
def test_wrong_missing_or_operation_mismatched_success_schema_fails_closed(
    response: dict[str, Any],
) -> None:
    outcome = _normalize("run", response)

    assert outcome["kind"] == "contract-invalid"
    assert outcome["status"] == "error"
    assert outcome["blockerCode"] == "core.contract-invalid"
    assert outcome["eligibleForRunPersistence"] is False


def test_current_error_prefers_top_level_code_and_preserves_execution_metadata() -> None:
    outcome = _normalize(
        "run",
        {
            "schema": "verifysignal.error/v1",
            "schemaVersion": 1,
            "operation": "run",
            "status": "error",
            "error": {"code": "entitlement.key-unknown"},
            "data": {
                "findings": [
                    {
                        "severity": "blocking",
                        "code": "entitlement.expired",
                    }
                ]
            },
            "execution": {
                "started": False,
                "phase": "pre-execution",
                "sideEffectMayExist": False,
            },
        },
    )

    assert outcome == {
        "operation": "run",
        "kind": "core-error",
        "schema": "verifysignal.error/v1",
        "status": "error",
        "errorCode": "entitlement.key-unknown",
        "blockerCode": "entitlement.unverifiable",
        "executionKnown": True,
        "executionStarted": False,
        "executionPhase": "pre-execution",
        "sideEffectMayExist": False,
        "eligibleForRunPersistence": False,
    }


def test_legacy_findings_are_used_only_when_top_level_code_is_absent() -> None:
    outcome = _normalize(
        "authoring-check",
        {
            "schema": "verifysignal.error/v1",
            "schemaVersion": 1,
            "operation": "authoring-check",
            "status": "error",
            "data": {
                "findings": [
                    {
                        "severity": "blocking",
                        "code": "entitlement.expired",
                    }
                ]
            },
        },
    )

    assert outcome["kind"] == "core-error"
    assert outcome["errorCode"] == "entitlement.expired"
    assert outcome["blockerCode"] == "entitlement.expired"
    assert outcome["executionKnown"] is False
    assert outcome["executionStarted"] is None
    assert outcome["executionPhase"] is None
    assert outcome["sideEffectMayExist"] is None
    assert outcome["eligibleForRunPersistence"] is False


def test_error_schema_with_non_error_status_is_contract_invalid() -> None:
    outcome = _normalize(
        "run",
        {
            "schema": "verifysignal.error/v1",
            "schemaVersion": 1,
            "operation": "run",
            "status": "blocked",
            "error": {"code": "entitlement.key-unknown"},
        },
    )

    assert outcome["kind"] == "contract-invalid"
    assert outcome["status"] == "error"
    assert outcome["blockerCode"] == "core.contract-invalid"
    assert outcome["eligibleForRunPersistence"] is False


def test_missing_execution_metadata_remains_unknown() -> None:
    outcome = _normalize(
        "run",
        {
            "schema": "verifysignal.error/v1",
            "schemaVersion": 1,
            "operation": "run",
            "status": "error",
            "error": {"code": "entitlement.key-unknown"},
        },
    )

    assert outcome["executionKnown"] is False
    assert outcome["executionStarted"] is None
    assert outcome["executionPhase"] is None
    assert outcome["sideEffectMayExist"] is None
    assert outcome["eligibleForRunPersistence"] is False


def test_malformed_execution_metadata_remains_unknown_as_a_complete_unit() -> None:
    outcome = _normalize(
        "run",
        {
            "schema": "verifysignal.error/v1",
            "schemaVersion": 1,
            "operation": "run",
            "status": "error",
            "error": {"code": "entitlement.key-unknown"},
            "execution": {
                "started": "false",
                "phase": "pre-execution",
                "sideEffectMayExist": False,
            },
        },
    )

    assert outcome["kind"] == "core-error"
    assert outcome["executionKnown"] is False
    assert outcome["executionStarted"] is None
    assert outcome["executionPhase"] is None
    assert outcome["sideEffectMayExist"] is None


def test_error_operation_mismatch_is_contract_invalid() -> None:
    outcome = _normalize(
        "run",
        {
            "schema": "verifysignal.error/v1",
            "schemaVersion": 1,
            "operation": "authoring-check",
            "status": "error",
            "error": {"code": "entitlement.key-unknown"},
        },
    )

    assert outcome["kind"] == "contract-invalid"
    assert outcome["blockerCode"] == "core.contract-invalid"
    assert outcome["eligibleForRunPersistence"] is False


@pytest.mark.parametrize(
    "data",
    [
        None,
        [],
        {},
        {"runId": ""},
        {"runId": "../outside"},
        {"runId": "nested/run"},
        {"runId": "/absolute"},
        {"runId": ".hidden"},
    ],
)
def test_run_success_requires_a_mapping_with_a_path_safe_nonempty_run_id(data: Any) -> None:
    outcome = _normalize(
        "run",
        {
            "schema": "verifysignal.run/v1",
            "schemaVersion": 1,
            "operation": "run",
            "status": "passed",
            "data": data,
        },
    )

    assert outcome["kind"] == "contract-invalid"
    assert outcome["schema"] == "verifysignal.run/v1"
    assert outcome["blockerCode"] == "core.contract-invalid"
    assert outcome["eligibleForRunPersistence"] is False


def test_success_requires_the_public_schema_version_and_mapping_data() -> None:
    for response in (
        {
            "schema": "verifysignal.run/v1",
            "schemaVersion": 2,
            "operation": "run",
            "status": "passed",
            "data": {"runId": "safe-run"},
        },
        {
            "schema": "verifysignal.authoring-check/v1",
            "schemaVersion": 1,
            "operation": "authoring-check",
            "status": "passed",
            "data": [],
        },
    ):
        outcome = _normalize(response["operation"], response)

        assert outcome["kind"] == "contract-invalid"
        assert outcome["eligibleForRunPersistence"] is False


def test_unknown_schema_and_error_code_are_replaced_by_safe_public_values() -> None:
    canary = "VS_TEST_SECRET_DO_NOT_PERSIST_in_schema_or_code"

    invalid_schema = _normalize(
        "run",
        {
            "schema": canary,
            "schemaVersion": 1,
            "operation": "run",
            "status": "passed",
            "data": {"runId": "safe-run"},
        },
    )
    unknown_error = _normalize(
        "run",
        {
            "schema": "verifysignal.error/v1",
            "schemaVersion": 1,
            "operation": "run",
            "status": "error",
            "error": {"code": canary},
            "execution": {
                "started": False,
                "phase": "pre-execution",
                "sideEffectMayExist": False,
            },
        },
    )

    assert invalid_schema["schema"] is None
    assert canary not in str(invalid_schema)
    assert unknown_error["errorCode"] == "core.error"
    assert unknown_error["blockerCode"] == "core.error"
    assert canary not in str(unknown_error)


def test_unknown_execution_phase_fails_closed_without_reflecting_it() -> None:
    canary = "VS_TEST_SECRET_DO_NOT_PERSIST_in_phase"
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
                "phase": canary,
                "sideEffectMayExist": False,
            },
        },
    )

    assert outcome["executionKnown"] is False
    assert outcome["executionPhase"] is None
    assert canary not in str(outcome)
