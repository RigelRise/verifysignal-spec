from __future__ import annotations

import base64
import contextlib
import hashlib
import json
import os
import shutil
import stat
import sys
import tarfile
import threading
from pathlib import Path
from typing import Any
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from cryptography.hazmat.primitives.serialization import load_pem_private_key

# Trust the shipped TEST release key while these fixtures build signed distributions.
os.environ.setdefault("VERIFYSIGNAL_ALLOW_TEST_RELEASE_KEYS", "1")

_TEST_RELEASE_KEY_ID = "verifysignal-core-release-test-key"
# Matching private half of the TEST release key in runtime/release_signature.py. Test-only.
_TEST_RELEASE_PRIVATE_KEY_PEM = """-----BEGIN PRIVATE KEY-----
MC4CAQAwBQYDK2VwBCIEIHo4Do7CxUHugcTuwe6Jwiz1D8K8sBJ2GJ6HCnK059+d
-----END PRIVATE KEY-----
"""


def _sign_release_metadata(metadata: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Return (base64 of the exact signed bytes, detached Ed25519 signature record)."""
    metadata_bytes = json.dumps(metadata).encode("utf-8")
    private_key = load_pem_private_key(_TEST_RELEASE_PRIVATE_KEY_PEM.encode("utf-8"), password=None)
    signature_value = base64.b64encode(private_key.sign(metadata_bytes)).decode("ascii")
    return base64.b64encode(metadata_bytes).decode("ascii"), {
        "schema": "verifysignal.runtime-signature/v1",
        "schemaVersion": 1,
        "signedSchema": "verifysignal.runtime-release/v1",
        "algorithm": "ed25519",
        "keyId": _TEST_RELEASE_KEY_ID,
        "signature": signature_value,
    }

from helpers import FAKE_CORE


def core_contract_operation(name: str, schema: str, schema_version: int = 1, *, status: str = "stable") -> dict[str, Any]:
    return {"name": name, "schema": schema, "schemaVersion": schema_version, "status": status}


def unsupported_multi_skill_section() -> dict[str, Any]:
    return {"status": "unsupported", "multiSkillSupported": False, "mode": "single-main"}


def supported_multi_skill_section() -> dict[str, Any]:
    return {
        "status": "stable",
        "multiSkillSupported": True,
        "roles": [{"name": "main", "status": "stable"}, {"name": "precondition", "status": "stable"}],
        "ordering": "declared-list-order",
        "evidenceSemantics": "gateId-attributed-per-participant",
    }


def partial_multi_skill_section() -> dict[str, Any]:
    return {
        "status": "partial",
        "multiSkillSupported": False,
        "roles": [{"name": "precondition", "status": "stable"}],
        "ordering": "preconditions-before-main",
        "evidenceSemantics": None,
    }


def side_effect_guardrails_section() -> dict[str, Any]:
    return {
        "status": "supported",
        "policyClasses": ["none", "authenticated-read", "write", "external-notification", "unknown"],
        "policyModes": ["observe", "warn", "enforce"],
        "confirmationSignalTypes": ["finalUrl", "runtimeOutput", "allowedNetworkObservation"],
        "confirmationSignals": {
            "supportedTypes": ["finalUrl", "runtimeOutput", "allowedNetworkObservation"],
            "unsupportedTypes": ["dom"],
            "unsupportedSignalError": "unsupported-confirmation-signal",
        },
        "runtimeOutputSources": ["finalUrl", "location", "dom", "network"],
        "runtimeOutputStatuses": ["captured", "redacted", "missing", "invalid"],
        "sideEffectStatuses": [
            "not-applicable",
            "not-started",
            "not-observed",
            "possible",
            "likely-committed",
            "committed-confirmed",
            "violated",
            "unknown",
        ],
        "failurePhases": ["pre-commit", "during-commit", "post-commit", "post-verification", "unknown"],
        "rerunRisks": ["safe", "safe-with-new-inputs", "requires-confirmation", "blocked"],
        "resultClassification": {
            "executionStatuses": ["passed", "failed", "blocked", "error"],
            "verificationStatuses": ["passed", "failed", "not-run", "unknown"],
            "sideEffectStatuses": [
                "not-applicable",
                "not-started",
                "not-observed",
                "possible",
                "likely-committed",
                "committed-confirmed",
                "violated",
                "unknown",
            ],
            "failurePhases": ["pre-commit", "during-commit", "post-commit", "post-verification", "unknown"],
            "rerunRisks": ["safe", "safe-with-new-inputs", "requires-confirmation", "blocked"],
        },
        "reportFields": ["sideEffects.policy", "sideEffects.observations[]", "sideEffects.violations[]", "runtimeOutputs[]", "resultClassification"],
    }


def side_effect_guardrails_with_runtime_confirmation_support(*, dom_supported: bool) -> dict[str, Any]:
    section = side_effect_guardrails_section()
    section["runtimeConfirmationSupport"] = [
        {"type": "dom", "status": "supported" if dom_supported else "unsupported"},
        {"type": "runtimeOutput", "status": "supported"},
        {"type": "finalUrl", "status": "supported"},
    ]
    return section


def browser_authoring_warnings_section() -> list[dict[str, Any]]:
    return [
        {
            "code": "degenerate-text-target",
            "severity": "warning",
            "runtimeReadinessSeverity": "blocking",
            "message": "A text assertion must not search for the same text inside a text-only target.",
            "remediation": "Use a stable parent target and keep expected text in the step or assertion.",
            "appliesTo": ["waitForText", "checkText", "assertions.text"],
        },
        {
            "code": "unstable-generated-css-target",
            "severity": "warning",
            "runtimeReadinessSeverity": "blocking",
            "message": "Generated or positional CSS targets are unstable.",
            "remediation": "Use a stable semantic locator.",
            "appliesTo": ["targets"],
        },
    ]


def core_contract_fixture_payload(
    *,
    browser_actions: list[dict[str, Any]] | None = None,
    include_browser: bool = True,
    include_credentials: bool = True,
    include_report_coverage: bool = True,
    extra_sections: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a public Core contracts response for contract-driven authoring tests."""

    data: dict[str, Any] = {
        "operations": [
            core_contract_operation("version", "verifysignal.version/v1"),
            core_contract_operation("contracts", "verifysignal.contracts/v1"),
            core_contract_operation("authoring-check", "verifysignal.authoring-check/v1"),
            core_contract_operation("run", "verifysignal.run/v1"),
            core_contract_operation("report.inspect", "verifysignal.report-inspection/v1"),
        ],
        "runRequest": {
            "schemaVersion": "qa-run-request/v1",
            "fields": [
                {"name": "schemaVersion", "status": "stable", "required": True},
                {"name": "request", "status": "stable", "required": True},
                {"name": "target", "status": "stable", "required": True},
                {"name": "credentialRefs", "status": "stable", "required": False},
                {"name": "skills", "status": "stable", "required": True},
            ],
        },
        "skill": {
            "schemaVersion": "verifysignal-browser-skill/v1",
            "fields": [
                {"name": "browser.targets", "status": "stable", "required": True},
                {"name": "browser.steps", "status": "stable", "required": True},
                {"name": "browser.assertions", "status": "stable", "required": False},
            ],
        },
        "placeholders": {
            "credentialSyntax": "{{credentials.<group>.<field>}}",
            "supportedNamespaces": [{"name": "parameters", "status": "stable"}, {"name": "credentials", "status": "stable"}],
        },
        "publicRedactionPolicy": {
            "publicErrorShape": {
                "forbiddenFields": ["rawValue", "rawRequestBody", "rawResponseBody", "receipt", "receiptPayload", "privateKey", "signedUrl", "absolutePath", "rawPayload"],
            },
            "safeEvidenceReferences": {
                "forbiddenFields": ["rawPayload", "absolutePath", "signedUrl", "storageState", "sessionCookies", "tracePayload", "screenshotPayload"],
            },
        },
        "runtimeTrustHandoff": {
            "entitlementReceiptEnv": "VERIFYSIGNAL_ENTITLEMENT_RECEIPT",
            "verificationKeysEnv": "VERIFYSIGNAL_ENTITLEMENT_PUBLIC_KEYS_JSON",
        },
        "sideEffectGuardrails": side_effect_guardrails_section(),
    }
    if include_browser:
        data["browserWorkflow"] = {
            "actions": browser_actions
            or [
                {"name": "navigate", "status": "stable", "requiredFields": ["value"]},
                {"name": "click", "status": "stable", "requiredFields": ["target"]},
                {"name": "fill", "status": "stable", "requiredFields": ["target", "value"]},
                {"name": "awaitNetwork", "status": "stable", "requiredFields": ["match"]},
            ],
            "assertions": [
                {"name": "text", "status": "stable", "requiredFields": ["target", "expected"]},
                {"name": "visible", "status": "stable", "requiredFields": ["target"]},
            ],
            "targetSignals": [{"name": "testId", "status": "stable"}, {"name": "css", "status": "stable"}],
            "networkMatchKeys": [{"name": "method", "status": "stable"}, {"name": "urlContains", "status": "stable"}],
            "metadataKeys": [{"name": "operationName", "status": "stable"}, {"name": "expectedStatus", "status": "stable"}],
            "warnings": browser_authoring_warnings_section(),
        }
    if include_credentials:
        data["credentials"] = {
            "sources": [{"name": "environment", "status": "stable"}, {"name": "prompt-cache", "status": "experimental"}],
            "referenceShape": "credentialRefs.<group>.keys.<field>",
        }
    if include_report_coverage:
        data["reportCoverage"] = {
            "schemaVersion": "qa-report/v1",
            "gateIdFields": ["gateId"],
            "stepCollections": ["steps", "preconditions"],
            "evidenceCollections": ["evidence"],
        }
    if extra_sections:
        data.update(extra_sections)
    return {
        "schema": "verifysignal.contracts/v1",
        "schemaVersion": 1,
        "operation": "contracts",
        "status": "passed",
        "data": {"sections": data},
    }


def current_core_contract_fixture_payload(
    *,
    browser_actions: list[dict[str, Any]] | None = None,
    extra_sections: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a fixture matching the current Core public contracts shape."""

    data: dict[str, Any] = {
        "operations": [
            core_contract_operation("version", "verifysignal.version/v1", status="supported"),
            core_contract_operation("contracts", "verifysignal.contracts/v1", status="supported"),
            core_contract_operation("authoring-check", "verifysignal.authoring-check/v1", status="supported"),
            core_contract_operation("run", "verifysignal.run/v1", status="supported"),
            core_contract_operation("report.inspect", "verifysignal.report-inspection/v1", status="supported"),
        ],
        "runRequest": {
            "schemaVersion": 1,
            "status": "supported",
            "fields": [
                {"path": "schemaVersion", "status": "supported", "required": True, "allowedValues": ["qa-run-request/v1"]},
                {"path": "request.id", "status": "supported", "required": True},
                {"path": "request.name", "status": "supported", "required": True},
                {"path": "target.url", "status": "supported", "required": True},
                {"path": "credentialRefs", "status": "supported", "required": False},
                {"path": "skills.main", "status": "supported", "required": True},
            ],
        },
        "skill": {
            "schemaVersion": 1,
            "status": "supported",
            "fields": [
                {"path": "schemaVersion", "status": "supported", "required": True, "allowedValues": ["qa-skill/v1"]},
                {"path": "skill.id", "status": "supported", "required": True},
                {"path": "browser.targets", "status": "supported", "required": True},
                {"path": "browser.steps", "status": "supported", "required": True},
                {"path": "browser.assertions", "status": "supported", "required": False},
            ],
        },
        "browserWorkflow": {
            "actions": browser_actions
            or [
                {"name": "navigate", "status": "supported", "requiredFields": ["value"]},
                {"name": "click", "status": "supported", "requiredFields": ["target"]},
                {"name": "fill", "status": "supported", "requiredFields": ["target", "value"]},
                {
                    "name": "awaitNetwork",
                    "status": "supported",
                    "requiredFields": ["match"],
                    "match": {
                        "keys": [
                            {"name": "urlContains", "status": "supported"},
                            {"name": "method", "status": "supported"},
                            {"name": "status", "status": "supported"},
                            {"name": "requestBodyContains", "status": "supported"},
                            {"name": "responseBodyContains", "status": "supported"},
                        ]
                    },
                },
            ],
            "assertions": [
                {"name": "text", "status": "supported", "requiredFields": ["target", "expected"]},
                {"name": "visible", "status": "supported", "requiredFields": ["target"]},
            ],
            "targetSignals": ["testId", "label", "text", "css", "semanticLocator"],
            "targets": {"composition": {"supportedSignals": ["testId", "css"]}},
            "metadataKeys": [{"name": "operationName", "status": "supported"}, {"name": "expectedStatus", "status": "supported"}],
            "warnings": browser_authoring_warnings_section(),
        },
        "credentials": {
            "credentialRefs": {
                "supportedSources": [{"name": "environment", "status": "supported"}, {"name": "prompt-cache", "status": "experimental"}],
                "referenceShape": "credentialRefs.<group>.keys.<field>",
                "placeholderSyntax": "{{credentials.<group>.<field>}}",
            }
        },
        "placeholders": {
            "credentialSyntax": "{{credentials.<group>.<field>}}",
            "supportedNamespaces": [{"name": "parameters", "status": "supported"}, {"name": "credentials", "status": "supported"}],
        },
        "reportCoverage": {
            "schemaVersion": "qa-report/v1",
            "gateIdFields": ["gateId"],
            "stepCollections": ["steps", "preconditions"],
            "evidenceCollections": ["evidence"],
        },
        "publicRedactionPolicy": {
            "publicErrorShape": {
                "forbiddenFields": ["rawValue", "rawRequestBody", "rawResponseBody", "receipt", "receiptPayload", "privateKey", "signedUrl", "absolutePath", "rawPayload"],
            },
            "safeEvidenceReferences": {
                "forbiddenFields": ["rawPayload", "absolutePath", "signedUrl", "storageState", "sessionCookies", "tracePayload", "screenshotPayload"],
            },
        },
        "runtimeTrustHandoff": {
            "entitlementReceiptEnv": "VERIFYSIGNAL_ENTITLEMENT_RECEIPT",
            "verificationKeysEnv": "VERIFYSIGNAL_ENTITLEMENT_PUBLIC_KEYS_JSON",
        },
        "sideEffectGuardrails": side_effect_guardrails_section(),
    }
    if extra_sections:
        data.update(extra_sections)
    return {
        "schema": "verifysignal.contracts/v1",
        "schemaVersion": 1,
        "operation": "contracts",
        "status": "passed",
        "data": {"sections": data},
    }


def write_fake_core_executable(path: Path, *, mode: str = "ok") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                f"#!{sys.executable}",
                "import os, runpy, sys",
                f"os.environ['FAKE_VERIFYSIGNAL_MODE'] = {mode!r}",
                f"sys.argv = [{str(FAKE_CORE)!r}, *sys.argv[1:]]",
                f"runpy.run_path({str(FAKE_CORE)!r}, run_name='__main__')",
                "",
            ]
        ),
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def build_managed_runtime_distribution(root: Path, *, platform: str, core_version: str = "0.5.1", mode: str = "ok") -> dict[str, Path | str]:
    dist = root / "dist"
    staging = root / "staging"
    dist.mkdir(parents=True, exist_ok=True)
    staging.mkdir(parents=True, exist_ok=True)
    package_root = staging / "verifysignal-core"
    write_fake_core_executable(package_root / "bin" / "verifysignal-core", mode=mode)
    (package_root / "manifest.json").write_text(
        json.dumps(
            {
                "schema": "verifysignal.runtime-manifest/v1",
                "schemaVersion": 1,
                "coreVersion": core_version,
                "platform": platform,
                "executable": "bin/verifysignal-core",
            }
        ),
        encoding="utf-8",
    )
    (package_root / "package.json").write_text(
        json.dumps({"name": "verifysignal-core-runtime", "private": True, "type": "module"}),
        encoding="utf-8",
    )
    artifact = dist / f"verifysignal-core-{platform}.tar.gz"
    with tarfile.open(artifact, "w:gz") as archive:
        archive.add(package_root, arcname="verifysignal-core")
    sha256 = hashlib.sha256(artifact.read_bytes()).hexdigest()
    release_metadata = {
        "schema": "verifysignal.runtime-release/v1",
        "schemaVersion": 1,
        "coreVersion": core_version,
        "publicContractVersion": "verifysignal-public-cli-json/v1",
        "channel": "stable",
        "issuer": "https://verifysignal.io",
        "packages": [{"platform": platform, "filename": artifact.name, "sha256": sha256}],
    }
    metadata_bytes_b64, release_signature = _sign_release_metadata(release_metadata)
    manifest = {
        "entries": [
            {
                "coreVersion": core_version,
                "contractVersion": "verifysignal-public-cli-json/v1",
                "platform": platform,
                "artifactName": artifact.name,
                "url": artifact.as_uri(),
                "sha256": sha256,
                "releaseMetadataBytes": metadata_bytes_b64,
                "signature": release_signature,
            }
        ]
    }
    manifest_path = dist / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return {
        "manifest": manifest_path,
        "artifact": artifact,
        "sha256": sha256,
        "coreVersion": core_version,
        "platform": platform,
        "releaseMetadataBytes": metadata_bytes_b64,
        "releaseSignature": release_signature,
    }


def build_managed_runtime_distribution_from_artifact(
    root: Path,
    *,
    artifact_source: Path,
    platform: str,
    core_version: str,
) -> dict[str, Path | str]:
    """Wrap an already packaged public Core artifact in the test signed backend contract."""

    dist = root / "dist"
    dist.mkdir(parents=True, exist_ok=True)
    artifact = dist / f"verifysignal-core-{core_version}-{platform}.tar.gz"
    shutil.copy2(artifact_source, artifact)
    sha256 = hashlib.sha256(artifact.read_bytes()).hexdigest()
    release_metadata = {
        "schema": "verifysignal.runtime-release/v1",
        "schemaVersion": 1,
        "coreVersion": core_version,
        "publicContractVersion": "verifysignal-public-cli-json/v1",
        "channel": "stable",
        "issuer": "https://verifysignal.io",
        "packages": [
            {
                "platform": platform,
                "filename": artifact.name,
                "sha256": sha256,
            }
        ],
    }
    metadata_bytes_b64, release_signature = _sign_release_metadata(release_metadata)
    return {
        "artifact": artifact,
        "sha256": sha256,
        "coreVersion": core_version,
        "platform": platform,
        "releaseMetadataBytes": metadata_bytes_b64,
        "releaseSignature": release_signature,
    }


def public_free_token_policy() -> dict[str, Any]:
    return {
        "policyId": "public-free",
        "policyVersion": 1,
        "validationMode": "happy-path-only",
        "maxUseCases": 1,
        "maxExchanges": 1,
        "maxExchangesPerHour": 1,
        "defaultTokenTtlDays": 30,
        "defaultReceiptTtlDays": 7,
        "refresh": "silent-credential",
    }


def public_free_receipt_summary(*, token: str = "vs_valid", exchange_count: int = 1) -> dict[str, Any]:
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]
    return {
        "receiptId": f"rcpt_{digest}",
        "issuer": "https://verifysignal.io",
        "issuedAt": "2026-06-01T00:00:00Z",
        "expiresAt": "2099-01-01T00:00:00Z",
        "scopes": ["runtime.download", "runtime.local-use"],
        "keyId": "ps-entitlement-2026-06",
        "usePolicy": {
            "policyId": "public-free",
            "policyVersion": 1,
            "validationMode": "happy-path-only",
            "maxUseCases": 1,
        },
        "tokenPolicy": {
            "exchangeCount": exchange_count,
            "maxExchanges": 1,
            "hourlyExchangeCount": min(exchange_count, 1),
            "maxExchangesPerHour": 1,
            "refresh": "silent-credential",
        },
    }


def public_verification_keys(
    *,
    key_id: str = "ps-entitlement-2026-06",
    issuer: str | None = None,
    malformed: bool = False,
) -> dict[str, Any]:
    if malformed:
        return {
            "schema": "verifysignal.entitlement-keys/v1",
            "schemaVersion": 1,
            "keys": "not-a-list",
        }
    payload: dict[str, Any] = {
        "schema": "verifysignal.entitlement-keys/v1",
        "schemaVersion": 1,
        "keys": [
            {
                "keyId": key_id,
                "algorithm": "ed25519",
                "publicKeyPem": "-----BEGIN PUBLIC KEY-----\\nMCowBQYDK2VwAyEA9cu+k/slRJsVRXV7mGPjJYtsqNO6DFFUi8phMq3Hiqw=\\n-----END PUBLIC KEY-----\\n",
                "status": "active",
            }
        ],
    }
    if issuer:
        payload["issuer"] = issuer
    return payload


def token_delivery_response() -> dict[str, Any]:
    return {
        "schema": "verifysignal.entitlement-token-delivery/v1",
        "schemaVersion": 1,
        "status": "accepted",
        "delivery": "email",
        "tokenPolicy": public_free_token_policy(),
        "message": "If the address is eligible, an unlock token will be sent.",
    }


def token_exchange_response(*, token: str = "vs_valid", exchange_count: int = 1) -> dict[str, Any]:
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    summary = public_free_receipt_summary(token=token, exchange_count=exchange_count)
    receipt = {
        "schema": "verifysignal.entitlement-receipt/v1",
        "schemaVersion": 1,
        "claims": {
            "receiptId": summary["receiptId"],
            "issuer": summary["issuer"],
            "audience": "verifysignal-core",
            "subject": {"kind": "opaque-subject", "value": f"sub_{digest[:16]}"},
            "issuedAt": summary["issuedAt"],
            "expiresAt": summary["expiresAt"],
            "scopes": summary["scopes"],
            "usePolicy": summary["usePolicy"],
            "publicContractVersion": "verifysignal-public-cli-json/v1",
            "coreVersionConstraint": ">=0.1.0 <1.0.0",
        },
        "signature": {
            "algorithm": "ed25519",
            "keyId": summary["keyId"],
            "signedPayload": "canonical-claims-json/v1",
            "value": "fake-signature",
        },
    }
    return {
        "schema": "verifysignal.entitlement-exchange/v1",
        "schemaVersion": 1,
        "receipt": json.dumps(receipt, separators=(",", ":")),
        "refreshCredential": "vs_refresh_credential_fixture_0000000000",
        "receiptSummary": summary,
    }


def token_refresh_response(*, credential: str = "vs_refresh", replayed: bool = False) -> dict[str, Any]:
    digest = hashlib.sha256(credential.encode("utf-8")).hexdigest()
    summary = public_free_receipt_summary(token=credential)
    # The refresh receipt summary carries no tokenPolicy (renew ≠ re-exchange).
    summary = {key: value for key, value in summary.items() if key != "tokenPolicy"}
    receipt = {
        "schema": "verifysignal.entitlement-receipt/v1",
        "schemaVersion": 1,
        "claims": {
            "receiptId": summary["receiptId"],
            "issuer": summary["issuer"],
            "audience": "verifysignal-core",
            "subject": {"kind": "opaque-subject", "value": f"sub_{digest[:16]}"},
            "issuedAt": summary["issuedAt"],
            "expiresAt": summary["expiresAt"],
            "scopes": summary["scopes"],
            "usePolicy": summary["usePolicy"],
            "publicContractVersion": "verifysignal-public-cli-json/v1",
            "coreVersionConstraint": ">=0.1.0 <1.0.0",
        },
        "signature": {
            "algorithm": "ed25519",
            "keyId": summary["keyId"],
            "signedPayload": "canonical-claims-json/v1",
            "value": "fake-signature",
        },
    }
    return {
        "schema": "verifysignal.entitlement-refresh/v1",
        "schemaVersion": 1,
        "replayed": replayed,
        "receipt": json.dumps(receipt, separators=(",", ":")),
        "receiptSummary": summary,
    }


def runtime_authorization_response(distribution: dict[str, Path | str]) -> dict[str, Any]:
    return {
        "schema": "verifysignal.runtime-download/v1",
        "schemaVersion": 1,
        "coreVersion": distribution["coreVersion"],
        "platform": distribution["platform"],
        "releaseMetadata": {"schema": "verifysignal.runtime-release/v1"},
        "releaseSignature": distribution["releaseSignature"],
        "releaseMetadataBytes": distribution["releaseMetadataBytes"],
        "package": {
            "filename": Path(str(distribution["artifact"])).name,
            "byteSize": Path(str(distribution["artifact"])).stat().st_size,
            "sha256": distribution["sha256"],
            "downloadUrl": Path(str(distribution["artifact"])).as_uri(),
            "expiresAt": "2099-01-01T00:00:00Z",
        },
    }


class FakeBackendState:
    def __init__(self, distribution: dict[str, Path | str] | None = None) -> None:
        self.distribution = distribution
        self.delivery_status = "accepted"
        self.exchange_failures: dict[str, tuple[int, str]] = {
            "vs_invalid": (401, "entitlement.invalid-token"),
            "vs_expired": (403, "entitlement.expired-token"),
            "vs_exchange_limit": (403, "entitlement.exchange-limit"),
            "vs_exchange_throttled": (429, "entitlement.exchange-throttled"),
            "vs_rejected": (403, "entitlement.rejected"),
        }
        self.keys_status = "ok"
        self.keys_key_id = "ps-entitlement-2026-06"
        self.keys_issuer: str | None = None
        self.download_status = "ok"
        self.latest_status = "ok"
        self.requests: list[dict[str, Any]] = []
        self.exchange_count = 0
        self.refresh_count = 0
        self.usage_count = 0
        # Keyed by refresh credential → (status, code), like exchange_failures.
        self.refresh_failures: dict[str, tuple[int, str]] = {
            "vs_refresh_revoked": (403, "entitlement.rejected"),
        }

    def request_paths(self, path: str) -> list[str]:
        return [request["path"] for request in self.requests if request.get("path") == path]


class _FakeBackendHandler(BaseHTTPRequestHandler):
    server: ThreadingHTTPServer

    def log_message(self, _format: str, *args: Any) -> None:
        return

    @property
    def state(self) -> FakeBackendState:
        return self.server.state  # type: ignore[attr-defined]

    def do_POST(self) -> None:
        body = self.rfile.read(int(self.headers.get("Content-Length", "0") or "0"))
        try:
            payload = json.loads(body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            payload = {}
        self.state.requests.append({"method": "POST", "path": self.path, "payload": payload})
        if self.path == "/entitlements/request-token":
            if self.state.delivery_status == "throttled":
                self._json(429, {"schema": "verifysignal.error/v1", "code": "entitlement.delivery-throttled", "message": "Delivery throttled."})
                return
            if self.state.delivery_status == "unavailable":
                self._json(503, {"schema": "verifysignal.error/v1", "code": "entitlement.delivery-unavailable", "message": "Delivery unavailable."})
                return
            self._json(200, token_delivery_response())
            return
        if self.path == "/entitlements/exchange":
            token = str(payload.get("token", ""))
            failure = self.state.exchange_failures.get(token)
            if failure:
                status, code = failure
                self._json(status, {"schema": "verifysignal.error/v1", "code": code, "message": "Exchange refused."})
                return
            self.state.exchange_count += 1
            self._json(200, token_exchange_response(token=token, exchange_count=self.state.exchange_count))
            return
        if self.path == "/entitlements/refresh":
            credential = str(payload.get("credential", ""))
            failure = self.state.refresh_failures.get(credential)
            if failure:
                status, code = failure
                self._json(status, {"schema": "verifysignal.error/v1", "code": code, "message": "Refresh refused."})
                return
            self.state.refresh_count += 1
            self._json(200, token_refresh_response(credential=credential))
            return
        if self.path == "/entitlements/usage":
            self.state.usage_count += 1
            self._json(200, {"schema": "verifysignal.usage-ping-ack/v1", "schemaVersion": 1, "ok": True})
            return
        self._json(404, {"schema": "verifysignal.error/v1", "code": "not-found"})

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        self.state.requests.append({"method": "GET", "path": self.path, "query": parse_qs(parsed.query)})
        if parsed.path == "/entitlements/keys":
            if self.state.keys_status == "unavailable":
                self._json(503, {"schema": "verifysignal.error/v1", "code": "api.unavailable"})
                return
            if self.state.keys_status == "malformed":
                self._json(200, public_verification_keys(malformed=True))
                return
            key_id = "ps-entitlement-other" if self.state.keys_status == "mismatched" else self.state.keys_key_id
            self._json(200, public_verification_keys(key_id=key_id, issuer=self.state.keys_issuer))
            return
        # Must precede the generic /runtimes/ branch, which would otherwise swallow it and answer a
        # download authorization to a version-resolution request.
        if parsed.path.startswith("/runtimes/latest"):
            if not self.headers.get("Authorization", "").startswith("Bearer "):
                self._json(401, {"schema": "verifysignal.error/v1", "code": "entitlement.missing"})
                return
            if self.state.latest_status == "unavailable" or not self.state.distribution:
                self._json(404, {"schema": "verifysignal.error/v1", "code": "distribution.unavailable"})
                return
            self._json(
                200,
                {
                    "schema": "verifysignal.runtime-latest/v1",
                    "schemaVersion": 1,
                    "coreVersion": self.state.distribution["coreVersion"],
                    "publicContractVersion": "verifysignal-public-cli-json/v1",
                    "platform": self.state.distribution["platform"],
                    "channel": "stable",
                },
            )
            return
        if parsed.path.startswith("/runtimes/"):
            if self.state.download_status == "unauthorized" or not self.headers.get("Authorization", "").startswith("Bearer "):
                self._json(403, {"schema": "verifysignal.error/v1", "code": "distribution.unauthorized"})
                return
            if self.state.download_status == "unavailable" or not self.state.distribution:
                self._json(503, {"schema": "verifysignal.error/v1", "code": "distribution.unavailable"})
                return
            if self.state.download_status == "url-expired":
                payload = runtime_authorization_response(self.state.distribution)
                payload["package"]["expiresAt"] = "2000-01-01T00:00:00Z"
                self._json(200, payload)
                return
            self._json(200, runtime_authorization_response(self.state.distribution))
            return
        self._json(404, {"schema": "verifysignal.error/v1", "code": "not-found"})

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


@contextlib.contextmanager
def serve_fake_entitlement_backend(distribution: dict[str, Path | str] | None = None):
    state = FakeBackendState(distribution=distribution)
    server = ThreadingHTTPServer(("127.0.0.1", 0), _FakeBackendHandler)
    server.state = state  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", state
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


@contextlib.contextmanager
def managed_runtime_test_env(monkeypatch, tmp_path: Path, *, api_base_url: str | None = None, token: str = "vs_valid", core_version: str = "0.5.1"):
    cache_dir = tmp_path / "user-cache"
    monkeypatch.setenv("VERIFYSIGNAL_RUNTIME_CACHE_DIR", str(cache_dir))
    monkeypatch.setenv("VERIFYSIGNAL_EMAIL_UNLOCK_TOKEN", token)
    monkeypatch.setenv("VERIFYSIGNAL_CORE_VERSION", core_version)
    monkeypatch.delenv("VERIFYSIGNAL_CORE_CMD", raising=False)
    if api_base_url:
        monkeypatch.setenv("VERIFYSIGNAL_API_BASE_URL", api_base_url)
    try:
        yield cache_dir
    finally:
        for key in [
            "VERIFYSIGNAL_RUNTIME_CACHE_DIR",
            "VERIFYSIGNAL_EMAIL_UNLOCK_TOKEN",
            "VERIFYSIGNAL_API_BASE_URL",
            "VERIFYSIGNAL_RUNTIME_MANIFEST_PATH",
            "VERIFYSIGNAL_RUNTIME_MANIFEST_JSON",
            "VERIFYSIGNAL_CORE_VERSION",
        ]:
            os.environ.pop(key, None)
