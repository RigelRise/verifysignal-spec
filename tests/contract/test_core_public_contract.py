from __future__ import annotations

from verifysignal_spec.core.contracts import PUBLIC_CONTRACT_VERSION, REQUIRED_OPERATIONS, public_contract_summary, validate_version_response


def test_core_public_contract_declares_required_operations_and_schemas() -> None:
    summary = public_contract_summary()

    assert summary["contractVersion"] == PUBLIC_CONTRACT_VERSION
    assert {item["operationName"] for item in summary["requiredOperations"]} == {
        "version",
        "contracts",
        "authoring-check",
        "run",
        "report.inspect",
    }
    assert summary["requiredOperationsByName"]["contracts"]["schemaName"] == "verifysignal.contracts/v1"
    assert summary["requiredOperationsByName"]["report.inspect"]["schemaName"] == "verifysignal.report-inspection/v1"


def test_crystallize_is_optional_and_run_stays_v1() -> None:
    # crystallize is an optional experimental capability, never a required operation:
    # an old Core that predates it must stay compatible.
    summary = public_contract_summary()
    assert "crystallize" not in REQUIRED_OPERATIONS
    assert "crystallize" not in {item["operationName"] for item in summary["requiredOperations"]}

    # run is additive (--record/--replay) and stays on verifysignal.run/v1 -- NOT bumped.
    assert REQUIRED_OPERATIONS["run"] == ("verifysignal.run/v1", 1)
    assert summary["requiredOperationsByName"]["run"]["schemaName"] == "verifysignal.run/v1"
    assert summary["requiredOperationsByName"]["run"]["schemaVersion"] == 1


def test_core_without_crystallize_stays_compatible() -> None:
    payload = {
        "data": {
            "verifysignalVersion": "0.1.0",
            "contractVersion": PUBLIC_CONTRACT_VERSION,
            "operations": [
                {"name": name, "schema": schema, "schemaVersion": version}
                for name, (schema, version) in REQUIRED_OPERATIONS.items()
            ],
        }
    }

    result = validate_version_response(payload)

    assert result.compatible is True
    assert result.missingOperations == []


def test_core_contract_incompatibility_reports_missing_operation_names() -> None:
    payload = {
        "data": {
            "verifysignalVersion": "0.1.0",
            "contractVersion": PUBLIC_CONTRACT_VERSION,
            "operations": [
                {"name": name, "schema": schema, "schemaVersion": version}
                for name, (schema, version) in REQUIRED_OPERATIONS.items()
                if name != "contracts"
            ],
        }
    }

    result = validate_version_response(payload)

    assert result.compatible is False
    assert result.missingOperations == ["contracts"]
    assert result.to_dict()["requiredOperationsByName"]["run"]["schemaVersion"] == 1


def test_core_contract_incompatibility_reports_schema_mismatch_details() -> None:
    payload = {
        "data": {
            "verifysignalVersion": "0.1.0",
            "contractVersion": PUBLIC_CONTRACT_VERSION,
            "operations": [
                {
                    "name": name,
                    "schema": ("verifysignal.run/v2" if name == "run" else schema),
                    "schemaVersion": (2 if name == "run" else version),
                }
                for name, (schema, version) in REQUIRED_OPERATIONS.items()
            ],
        }
    }

    result = validate_version_response(payload)
    data = result.to_dict()

    assert result.compatible is False
    assert data["compatibilityStatus"] == "incompatible"
    assert result.incompatibleOperations[0]["operationName"] == "run"
    assert result.incompatibleOperations[0]["expectedSchema"] == "verifysignal.run/v1"
    assert result.incompatibleOperations[0]["actualSchema"] == "verifysignal.run/v2"
    assert data["recoveryAction"] == "Upgrade VerifySignal Runtime or VerifySignal CLI to compatible public CLI JSON schemas."
