from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from verifysignal_spec.core.contracts import PUBLIC_CONTRACT_VERSION, REQUIRED_OPERATION_METADATA

MANAGED_RUNTIME_READINESS_SCHEMA = "verifysignal-spec-managed-runtime-readiness/v1"

RuntimeSource = Literal["explicit", "workspace", "env", "path", "ancestor-sibling", "managed-cache", "managed-download", "none"]
RuntimeStatus = Literal["ready", "blocked", "incompatible", "error"]
RuntimeAttemptStatus = Literal["skipped", "missing", "available", "compatible", "incompatible", "blocked", "error"]
RuntimeApiSource = Literal["default", "environment", "flag", "workspace", "test"]

REQUIRED_RUNTIME_BLOCKER_CODES = {
    "api.unavailable",
    "api.incompatible",
    "api.misconfigured",
    "network.missing",
    "manifest.unavailable",
    "manifest.invalid",
    "platform.unsupported",
    "artifact.integrity-failed",
    "artifact.authenticity-failed",
    "cache.permission-denied",
    "credentials.unavailable",
    "entitlement.unlock-required",
    "entitlement.delivery-unavailable",
    "entitlement.delivery-throttled",
    "entitlement.invalid-token",
    "entitlement.expired-token",
    "entitlement.exchange-limit",
    "entitlement.exchange-throttled",
    "entitlement.expired",
    "entitlement.revoked",
    "entitlement.malformed",
    "entitlement.unverifiable",
    "entitlement.rejected",
    "entitlement.key-unknown",
    "entitlement.keys-unavailable",
    "entitlement.keys-incompatible",
    "core.missing",
    "core.incompatible",
    "distribution.unauthorized",
    "distribution.unavailable",
    "distribution.url-expired",
    "distribution.version-unspecified",
}

BLOCKER_CATEGORY_BY_PREFIX = {
    "api.": "environment",
    "network.": "environment",
    "manifest.": "distribution",
    "platform.": "distribution",
    "artifact.": "security",
    "cache.": "environment",
    "credentials.": "distribution",
    "entitlement.": "entitlement",
    "distribution.": "distribution",
}

SECRET_KEY_MARKERS = (
    "token",
    "email",
    "secret",
    "password",
    "credential",
    "receiptpayload",
    "receipt_payload",
    "signedurl",
    "signed_url",
    "downloadurl",
    "download_url",
    "authorization",
    "backenderrorbody",
    "backend_error_body",
    "bearer",
    "cookie",
    "screenshot",
    "browserstorage",
    "browser_storage",
    "localstorage",
    "sessionstorage",
    "sourcecode",
    "source_code",
    "private_runtime",
)
SECRET_VALUE_MARKERS = (
    "x-amz-signature=",
    "signature=",
    "token=",
    "access_key=",
    "password=",
    "bearer ",
    "raw-email-token",
    "email-token",
    "signed-receipt",
)


def clean(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [clean(v) for v in value]
    return value


def blocker_category(code: str) -> str:
    if code == "core.missing":
        return "environment"
    if code.startswith("core."):
        return "compatibility"
    for prefix, category in BLOCKER_CATEGORY_BY_PREFIX.items():
        if code.startswith(prefix):
            return category
    return "environment"


def redact_runtime_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        lower = value.lower()
        if any(marker in lower for marker in SECRET_VALUE_MARKERS):
            return "[redacted]"
        if re.search(r"[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}", value):
            return "[redacted]"
        if re.search(r"https?://\S+\?\S*(sig|signature|token|credential|x-amz-)", lower):
            return "[redacted]"
        return value
    if isinstance(value, dict):
        return redact_runtime_payload(value)
    if isinstance(value, list):
        return [redact_runtime_value(item) for item in value]
    return value


def redact_runtime_payload(payload: dict[str, Any]) -> dict[str, Any]:
    redacted: dict[str, Any] = {}
    for key, value in payload.items():
        normalized = str(key).replace("-", "").replace("_", "").lower()
        if normalized == "tokenpolicy":
            redacted[key] = redact_runtime_value(value)
            continue
        if normalized in {"receipt", "rawreceipt", "signedreceipt", "downloadurl", "signedurl"} or any(marker.replace("_", "") in normalized for marker in SECRET_KEY_MARKERS):
            redacted[key] = "[redacted]"
        else:
            redacted[key] = redact_runtime_value(value)
    return redacted


@dataclass(slots=True)
class RuntimeSetupBlocker:
    code: str
    message: str
    severity: Literal["blocker"] = "blocker"
    category: str | None = None
    recoveryCommand: str | None = None
    suggestedAction: str | None = None
    repairable: bool = False
    documentationRef: str | None = None

    def __post_init__(self) -> None:
        if self.category is None:
            self.category = blocker_category(self.code)
        if self.recoveryCommand is None:
            self.recoveryCommand = "verifysignal core setup --core-cmd <path>"
        if self.suggestedAction is None:
            self.suggestedAction = self.recoveryCommand

    def to_dict(self) -> dict[str, Any]:
        return redact_runtime_payload(clean(asdict(self)))


@dataclass(slots=True)
class RuntimeSourceAttempt:
    source: RuntimeSource
    status: RuntimeAttemptStatus
    terminal: bool = False
    command: str | None = None
    platform: str | None = None
    runtimeVersion: str | None = None
    contractVersion: str | None = None
    message: str = ""
    blockerCode: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return redact_runtime_payload(clean(asdict(self)))


@dataclass(slots=True)
class RuntimeEntitlementStatus:
    status: Literal[
        "valid",
        "required",
        "token-delivery-pending",
        "expired",
        "revoked",
        "rejected",
        "malformed",
        "unverifiable",
        "not-required",
        "not-checked",
    ] = "not-checked"
    receiptId: str | None = None
    issuer: str | None = None
    expiresAt: str | None = None
    scopes: list[str] = field(default_factory=list)
    keyId: str | None = None
    usePolicy: dict[str, Any] = field(default_factory=dict)
    tokenPolicy: dict[str, Any] = field(default_factory=dict)
    message: str | None = None
    blockerCode: str | None = None
    receiptPath: str | None = field(default=None, repr=False, compare=False)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("receiptPath", None)
        return redact_runtime_payload(clean(data))


@dataclass(slots=True)
class RuntimeCacheStatus:
    status: Literal["hit", "miss", "corrupt", "incompatible", "not-checked"] = "not-checked"
    platform: str | None = None
    coreVersion: str | None = None
    message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return redact_runtime_payload(clean(asdict(self)))


@dataclass(slots=True)
class RuntimeVerificationKeyStatus:
    status: Literal["ready", "blocked", "not-required", "not-checked"] = "not-checked"
    source: Literal["manual-override", "cache", "fetched", "none", "not-required"] = "none"
    matchedKeyId: str | None = None
    sourceApiBaseUrl: str | None = None
    issuer: str | None = None
    message: str | None = None
    blockerCode: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return redact_runtime_payload(clean(asdict(self)))


@dataclass(slots=True)
class RuntimeCacheEntry:
    coreVersion: str
    contractVersion: str
    platform: str
    runtimeCommand: str
    cachePath: str
    sha256: str
    verifiedAt: str
    lastUsedAt: str
    source: str = "managed-download"
    verificationStatus: str = "verified"
    entitlementReceiptId: str | None = None
    metadataPath: Any | None = field(default=None, repr=False, compare=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, metadata_path: Any | None = None) -> "RuntimeCacheEntry":
        return cls(
            coreVersion=str(data.get("coreVersion", "")),
            contractVersion=str(data.get("contractVersion", PUBLIC_CONTRACT_VERSION)),
            platform=str(data.get("platform", "")),
            runtimeCommand=str(data.get("runtimeCommand", "")),
            cachePath=str(data.get("cachePath", "")),
            sha256=str(data.get("sha256", "")),
            verifiedAt=str(data.get("verifiedAt", "")),
            lastUsedAt=str(data.get("lastUsedAt", "")),
            source=str(data.get("source", "managed-download")),
            verificationStatus=str(data.get("verificationStatus", "verified")),
            entitlementReceiptId=data.get("entitlementReceiptId"),
            metadataPath=metadata_path,
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("metadataPath", None)
        return redact_runtime_payload(clean(data))


@dataclass(slots=True)
class RuntimeEntitlementReceipt:
    receiptId: str
    status: str
    issuedAt: str | None = None
    expiresAt: str | None = None
    issuer: str | None = None
    scopes: list[str] = field(default_factory=list)
    keyId: str | None = None
    usePolicy: dict[str, Any] = field(default_factory=dict)
    tokenPolicy: dict[str, Any] = field(default_factory=dict)
    signatureStatus: str = "verified"
    receiptPayload: str | None = field(default=None, repr=False, compare=False)
    path: str | None = field(default=None, repr=False, compare=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RuntimeEntitlementReceipt":
        if isinstance(data.get("receipt"), str) and not isinstance(data.get("receiptSummary"), dict):
            return cls.from_raw_receipt_payload(data["receipt"])
        summary = data.get("receiptSummary") if isinstance(data.get("receiptSummary"), dict) else data
        return cls(
            receiptId=str(summary.get("receiptId", "")),
            status=str(summary.get("status", data.get("status", "valid" if summary.get("receiptId") else "malformed"))),
            issuedAt=summary.get("issuedAt"),
            expiresAt=summary.get("expiresAt"),
            issuer=summary.get("issuer"),
            scopes=[str(item) for item in summary.get("scopes", summary.get("scope", []))],
            keyId=summary.get("keyId"),
            usePolicy=dict(summary.get("usePolicy", {})) if isinstance(summary.get("usePolicy"), dict) else {},
            tokenPolicy=dict(summary.get("tokenPolicy", {})) if isinstance(summary.get("tokenPolicy"), dict) else {},
            signatureStatus=str(summary.get("signatureStatus", data.get("signatureStatus", "not-checked"))),
            receiptPayload=data.get("receipt") if isinstance(data.get("receipt"), str) else data.get("receiptPayload"),
            path=data.get("path"),
        )

    @classmethod
    def from_raw_receipt_payload(cls, payload: str) -> "RuntimeEntitlementReceipt":
        try:
            envelope = json.loads(payload)
        except Exception:
            return cls(receiptId="", status="malformed", receiptPayload=payload)
        claims = envelope.get("claims") if isinstance(envelope, dict) else {}
        signature = envelope.get("signature") if isinstance(envelope, dict) else {}
        if not isinstance(claims, dict) or not isinstance(signature, dict):
            return cls(receiptId="", status="malformed", receiptPayload=payload)
        return cls(
            receiptId=str(claims.get("receiptId", "")),
            status="valid" if claims.get("receiptId") else "malformed",
            issuedAt=claims.get("issuedAt"),
            expiresAt=claims.get("expiresAt"),
            issuer=claims.get("issuer"),
            scopes=[str(item) for item in claims.get("scopes", [])] if isinstance(claims.get("scopes"), list) else [],
            keyId=signature.get("keyId"),
            usePolicy=dict(claims.get("usePolicy", {})) if isinstance(claims.get("usePolicy"), dict) else {},
            receiptPayload=payload,
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("receiptPayload", None)
        data.pop("path", None)
        return redact_runtime_payload(clean(data))

    def to_file_dict(self) -> dict[str, Any]:
        data = {
            "schema": "verifysignal.entitlement-receipt-file/v1",
            "schemaVersion": 1,
            "receipt": self.receiptPayload,
            "receiptSummary": self.to_dict(),
        }
        return clean(data)

    def to_status(self) -> RuntimeEntitlementStatus:
        return RuntimeEntitlementStatus(
            status=self.status if self.status in {"valid", "expired", "revoked", "rejected", "malformed", "unverifiable"} else "rejected",  # type: ignore[arg-type]
            receiptId=self.receiptId,
            issuer=self.issuer,
            expiresAt=self.expiresAt,
            scopes=list(self.scopes),
            keyId=self.keyId,
            usePolicy=dict(self.usePolicy),
            tokenPolicy=dict(self.tokenPolicy),
            receiptPath=self.path,
        )


@dataclass(slots=True)
class EntitlementClientConfig:
    apiBaseUrl: str
    source: RuntimeApiSource = "default"
    timeoutSeconds: int = 30
    cliVersion: str = ""
    platform: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return redact_runtime_payload(clean(asdict(self)))


@dataclass(slots=True)
class RuntimeApiStatus:
    baseUrl: str
    source: RuntimeApiSource = "default"
    status: Literal["not-checked", "reachable", "unreachable", "misconfigured"] = "not-checked"
    message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return redact_runtime_payload(clean(asdict(self)))


@dataclass(slots=True)
class MetadataConsentDecision:
    status: Literal["granted", "declined", "not-asked"] = "not-asked"
    decidedAt: str | None = None
    summaryId: str | None = None
    categories: list[str] = field(default_factory=list)
    blocksRuntimeUnlock: bool = False

    def to_dict(self) -> dict[str, Any]:
        return redact_runtime_payload(clean(asdict(self)))


@dataclass(slots=True)
class ManagedRuntimeReadinessResult:
    status: RuntimeStatus
    source: RuntimeSource = "none"
    commandCompatibilityStatus: Literal["not-checked", "passed", "blocked"] = "not-checked"
    trustMaterialStatus: Literal["not-checked", "ready", "blocked"] = "not-checked"
    protectedOperationStatus: Literal["not-checked", "passed", "blocked"] = "not-checked"
    readinessScope: Literal["command-and-trust-inputs", "protected-operation"] = "command-and-trust-inputs"
    runtimeCommand: str | None = None
    runtimeVersion: str | None = None
    contractVersion: str | None = PUBLIC_CONTRACT_VERSION
    missingOperations: list[str] = field(default_factory=list)
    incompatibleOperations: list[dict[str, Any]] = field(default_factory=list)
    attempts: list[RuntimeSourceAttempt] = field(default_factory=list)
    api: RuntimeApiStatus = field(default_factory=lambda: RuntimeApiStatus(baseUrl="https://www.verifysignal.io/api"))
    entitlement: RuntimeEntitlementStatus = field(default_factory=RuntimeEntitlementStatus)
    cache: RuntimeCacheStatus = field(default_factory=RuntimeCacheStatus)
    verificationKeys: RuntimeVerificationKeyStatus = field(default_factory=RuntimeVerificationKeyStatus)
    blockers: list[RuntimeSetupBlocker] = field(default_factory=list)
    message: str = ""
    nextAction: str = "Continue with validation or run."
    schemaVersion: str = MANAGED_RUNTIME_READINESS_SCHEMA

    def __post_init__(self) -> None:
        if self.commandCompatibilityStatus == "not-checked":
            if self.status == "ready" or any(item.status == "compatible" for item in self.attempts):
                self.commandCompatibilityStatus = "passed"
            elif any(item.status in {"missing", "incompatible", "error"} for item in self.attempts):
                self.commandCompatibilityStatus = "blocked"

        if self.trustMaterialStatus == "not-checked":
            entitlement_ready = self.entitlement.status in {"valid", "not-required"}
            keys_ready = self.verificationKeys.status in {"ready", "not-required"}
            if self.status == "ready" or (entitlement_ready and keys_ready):
                self.trustMaterialStatus = "ready"
            elif self.commandCompatibilityStatus == "passed" and (
                self.entitlement.status not in {"not-checked", "valid", "not-required"}
                or self.verificationKeys.status == "blocked"
            ):
                self.trustMaterialStatus = "blocked"

    @classmethod
    def blocked(
        cls,
        blocker: RuntimeSetupBlocker,
        *,
        attempts: list[RuntimeSourceAttempt] | None = None,
        entitlement: RuntimeEntitlementStatus | None = None,
        cache: RuntimeCacheStatus | None = None,
        verification_keys: RuntimeVerificationKeyStatus | None = None,
        message: str | None = None,
    ) -> "ManagedRuntimeReadinessResult":
        return cls(
            status="blocked",
            source="none",
            attempts=attempts or [],
            entitlement=entitlement or RuntimeEntitlementStatus(),
            cache=cache or RuntimeCacheStatus(),
            verificationKeys=verification_keys or RuntimeVerificationKeyStatus(),
            blockers=[blocker],
            message=message or blocker.message,
            nextAction=blocker.recoveryCommand or "Resolve runtime setup blocker.",
        )

    def to_dict(self) -> dict[str, Any]:
        data = {
            "schemaVersion": self.schemaVersion,
            "status": self.status,
            "source": self.source,
            "commandCompatibilityStatus": self.commandCompatibilityStatus,
            "trustMaterialStatus": self.trustMaterialStatus,
            "protectedOperationStatus": self.protectedOperationStatus,
            "readinessScope": self.readinessScope,
            "runtimeCommand": redact_runtime_value(self.runtimeCommand),
            "runtimeVersion": self.runtimeVersion,
            "contractVersion": self.contractVersion,
            "requiredOperations": REQUIRED_OPERATION_METADATA,
            "requiredOperationsByName": {item["operationName"]: item for item in REQUIRED_OPERATION_METADATA},
            "missingOperations": self.missingOperations,
            "incompatibleOperations": self.incompatibleOperations,
            "attempts": [item.to_dict() for item in self.attempts],
            "api": self.api.to_dict(),
            "entitlement": self.entitlement.to_dict(),
            "cache": self.cache.to_dict(),
            "verificationKeys": self.verificationKeys.to_dict(),
            "blockers": [item.to_dict() for item in self.blockers],
            "message": self.message,
            "nextAction": self.nextAction,
        }
        return redact_runtime_payload(clean(data))
