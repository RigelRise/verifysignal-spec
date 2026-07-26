from __future__ import annotations

from dataclasses import dataclass
from typing import Any

PUBLIC_CONTRACT_VERSION = "verifysignal-public-cli-json/v1"

REQUIRED_PUBLIC_SCHEMA_NAMES = [
    PUBLIC_CONTRACT_VERSION,
    "verifysignal-core-version/v1",
    "verifysignal-core-authoring-check/v1",
    "verifysignal-core-run-result/v1",
    "verifysignal-core-report-inspect/v1",
]

REQUIRED_OPERATIONS = {
    "version": ("verifysignal.version/v1", 1),
    "contracts": ("verifysignal.contracts/v1", 1),
    "authoring-check": ("verifysignal.authoring-check/v1", 1),
    "run": ("verifysignal.run/v1", 1),
    "report.inspect": ("verifysignal.report-inspection/v1", 1),
}

REQUIRED_OPERATION_METADATA = [
    {
        "operationName": name,
        "schemaName": schema,
        "schemaVersion": version,
    }
    for name, (schema, version) in REQUIRED_OPERATIONS.items()
]

ALLOWED_CORE_STATUSES = {"passed", "failed", "blocked", "error"}

CORE_ENTITLEMENT_ERROR_MAP = {
    "entitlement.missing": "entitlement.unlock-required",
    "entitlement.unreadable": "entitlement.malformed",
    "entitlement.raw-token": "entitlement.rejected",
    "entitlement.malformed": "entitlement.malformed",
    "entitlement.signature-invalid": "entitlement.unverifiable",
    "entitlement.key-unknown": "entitlement.unverifiable",
    # A trust failure: the receipt's signing key is real but not trusted in this runtime context.
    # Core emits and publishes this (operation-contract.ts, runtime-trust-contract.ts); the map used
    # to lack it, so it fell through to a generic message.
    "entitlement.trust-key-context-disallowed": "entitlement.unverifiable",
    "entitlement.expired": "entitlement.expired",
    "entitlement.issuer-mismatch": "entitlement.rejected",
    "entitlement.audience-mismatch": "entitlement.rejected",
    "entitlement.scope-missing": "entitlement.rejected",
    "entitlement.policy-denied": "entitlement.rejected",
    "entitlement.contract-mismatch": "core.incompatible",
    "entitlement.version-mismatch": "core.incompatible",
    "entitlement.subject-invalid": "entitlement.rejected",
}


@dataclass(slots=True)
class CompatibilityResult:
    compatible: bool
    verifysignalVersion: str | None = None
    contractVersion: str | None = None
    missingOperations: list[str] | None = None
    incompatibleOperations: list[dict[str, Any]] | None = None
    message: str = ""
    raw: dict[str, Any] | None = None
    recoveryAction: str = "Upgrade VerifySignal Core or VerifySignal Spec to compatible public CLI JSON schemas."

    def to_dict(self) -> dict[str, Any]:
        compatibility_status = "compatible"
        if self.incompatibleOperations:
            compatibility_status = "incompatible"
        elif self.missingOperations:
            compatibility_status = "missing"
        elif not self.compatible:
            compatibility_status = "incompatible"
        data = {
            "compatible": self.compatible,
            "compatibilityStatus": compatibility_status,
            "verifysignalVersion": self.verifysignalVersion,
            "contractVersion": self.contractVersion,
            "missingOperations": self.missingOperations or [],
            "incompatibleOperations": self.incompatibleOperations or [],
            "message": self.message,
            "severity": "info" if self.compatible else "blocked",
            "recoveryAction": "" if self.compatible else self.recoveryAction,
        }
        data.update(public_contract_summary())
        return data


def public_contract_summary() -> dict[str, Any]:
    operations = list(REQUIRED_OPERATION_METADATA)
    return {
        "contractVersion": PUBLIC_CONTRACT_VERSION,
        "requiredPublicSchemaNames": list(REQUIRED_PUBLIC_SCHEMA_NAMES),
        "requiredOperations": operations,
        "requiredOperationsByName": {item["operationName"]: item for item in operations},
    }


def validate_version_response(data: dict[str, Any]) -> CompatibilityResult:
    payload = data.get("data", {})
    contract_version = payload.get("contractVersion")
    operations = payload.get("operations", [])
    operation_map = {item.get("name"): item for item in operations if isinstance(item, dict)}
    missing: list[str] = []
    incompatible: list[dict[str, Any]] = []
    for name, (schema, version) in REQUIRED_OPERATIONS.items():
        item = operation_map.get(name)
        if not item:
            missing.append(name)
            continue
        actual_schema = item.get("schema")
        actual_version = item.get("schemaVersion")
        if actual_schema != schema or actual_version != version:
            incompatible.append(
                {
                    "operationName": name,
                    "expectedSchema": schema,
                    "expectedSchemaVersion": version,
                    "actualSchema": actual_schema,
                    "actualSchemaVersion": actual_version,
                    "compatibilityStatus": "incompatible",
                    "severity": "blocked",
                    "recoveryAction": "Upgrade VerifySignal Core or VerifySignal Spec to compatible public CLI JSON schemas.",
                }
            )
    compatible = contract_version == PUBLIC_CONTRACT_VERSION and not missing
    if contract_version != PUBLIC_CONTRACT_VERSION:
        incompatible.append(
            {
                "operationName": "version",
                "expectedSchema": PUBLIC_CONTRACT_VERSION,
                "expectedSchemaVersion": None,
                "actualSchema": contract_version,
                "actualSchemaVersion": None,
                "compatibilityStatus": "incompatible",
                "severity": "blocked",
                "recoveryAction": "Upgrade VerifySignal Core or VerifySignal Spec to compatible public CLI JSON schemas.",
            }
        )
    compatible = compatible and not incompatible
    message = "Core contract is compatible." if compatible else "Core public CLI JSON contract is incompatible."
    return CompatibilityResult(
        compatible=compatible,
        verifysignalVersion=payload.get("verifysignalVersion"),
        contractVersion=contract_version,
        missingOperations=missing,
        incompatibleOperations=incompatible,
        message=message,
        raw=data,
    )


def core_supports_discover(version_response: dict[str, Any]) -> bool:
    """Optional-capability check for Core feature 016 dynamic grounding.

    `discover` is intentionally NOT part of REQUIRED_OPERATIONS (adding it would
    mark every current Core incompatible). A client treats it as available only
    when the public `version` operations array advertises it.
    """
    payload = version_response.get("data", {}) if isinstance(version_response, dict) else {}
    operations = payload.get("operations", []) if isinstance(payload, dict) else []
    if not isinstance(operations, list):
        return False
    for item in operations:
        if isinstance(item, dict) and item.get("name") == "discover" and item.get("schema") == "verifysignal.discover/v1":
            return True
    return False


def core_supports_crystallize(version_response: dict[str, Any]) -> bool:
    """Optional-capability check for Core crystallization.

    `crystallize` is intentionally NOT part of REQUIRED_OPERATIONS (adding it
    would mark every current Core incompatible). A client treats it as available
    only when the public `version` operations array advertises it.
    """
    payload = version_response.get("data", {}) if isinstance(version_response, dict) else {}
    operations = payload.get("operations", []) if isinstance(payload, dict) else []
    if not isinstance(operations, list):
        return False
    for item in operations:
        if isinstance(item, dict) and item.get("name") == "crystallize" and item.get("schema") == "verifysignal.crystallize/v1":
            return True
    return False


def core_supports_probe(version_response: dict[str, Any]) -> bool:
    """Return whether Core advertises the exact optional probe v1 contract."""
    payload = version_response.get("data", {}) if isinstance(version_response, dict) else {}
    operations = payload.get("operations", []) if isinstance(payload, dict) else []
    if not isinstance(operations, list):
        return False
    return any(
        isinstance(item, dict)
        and item.get("name") == "probe"
        and item.get("schema") == "verifysignal.probe/v1"
        and item.get("schemaVersion") == 1
        for item in operations
    )


def _run_operation_modes(version_response: dict[str, Any]) -> list[str]:
    payload = version_response.get("data", {}) if isinstance(version_response, dict) else {}
    operations = payload.get("operations", []) if isinstance(payload, dict) else []
    if not isinstance(operations, list):
        return []
    for item in operations:
        if isinstance(item, dict) and item.get("name") == "run":
            modes = item.get("modes", [])
            return [str(mode) for mode in modes] if isinstance(modes, list) else []
    return []


def core_supports_run_record(version_response: dict[str, Any]) -> bool:
    """Optional-capability check for `run --record`.

    Record/replay are MODES of the run operation, advertised in its version entry (`modes`).
    Advertised, never assumed: a Core that predates the advertisement is treated as not
    supporting them, so the client blocks with a clear code instead of failing inside Core.
    """
    return "record" in _run_operation_modes(version_response)


def core_supports_run_replay(version_response: dict[str, Any]) -> bool:
    """Optional-capability check for `run --replay` (see core_supports_run_record)."""
    return "replay" in _run_operation_modes(version_response)


def normalize_status(data: dict[str, Any]) -> str:
    status = data.get("status")
    if status in ALLOWED_CORE_STATUSES:
        return status
    nested = data.get("data", {}).get("status")
    if nested in ALLOWED_CORE_STATUSES:
        return nested
    return "error"


def core_entitlement_blocker_code(data: dict[str, Any]) -> str | None:
    findings = data.get("data", {}).get("findings", [])
    if not isinstance(findings, list):
        return None
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        code = str(finding.get("code") or "")
        if code in CORE_ENTITLEMENT_ERROR_MAP:
            return CORE_ENTITLEMENT_ERROR_MAP[code]
    return None
