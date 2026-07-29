from __future__ import annotations

import math
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlsplit

from . import layout
from .models import (
    ArtifactReference,
    CredentialReadinessHint,
    RerunPolicy,
    ResourceIdentity,
    SideEffectDeclaration,
    SideEffectLifecycleDeclaration,
    SupersedeReview,
    UseCaseRecord,
)
from .repository import load_document, load_registry, load_use_case

SECRET_FIELD_RE = re.compile(r"(password|secret|token|api[_-]?key|access[_-]?key|private[_-]?key|client[_-]?secret|authorization)", re.I)
BEARER_RE = re.compile(r"\b(Bearer|Basic)\s+[A-Za-z0-9._~+/=-]{12,}", re.I)
HIGH_ENTROPY_RE = re.compile(r"^[A-Za-z0-9_./+=-]{32,}$")
HEX_IDENTIFIER_RE = re.compile(r"^[a-f0-9]{7,64}$", re.I)
PUBLIC_DIGEST_RE = re.compile(r"^(sha256:)?[a-f0-9]{64}$", re.I)
DUMMY_VALUES = {"example", "dummy", "placeholder", "changeme", "test", "sample", "qa@example.com"}
SECRET_QUERY_PARAM_RE = re.compile(r"(token|secret|api[_-]?key|access[_-]?key|client[_-]?secret|authorization|auth|password|pwd)", re.I)
ENV_VAR_NAME_RE = re.compile(r"^[A-Z_][A-Z0-9_]*$")
LOCAL_CONFIG_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*$")
ENV_ASSIGNMENT_RE = re.compile(r"\b[A-Z_][A-Z0-9_]*\s*=\s*['\"]?[^'\"\s]+")


def looks_secret(value: Any, field_name: str = "") -> bool:
    if value is None:
        return False
    text = str(value).strip()
    if not text:
        return False
    if text.lower() in DUMMY_VALUES or text.startswith("${") or text.startswith("<"):
        return False
    normalized_field = field_name.lower()
    if field_name in {
        "schemaVersion",
        "version",
        "id",
        "path",
        "file",
        "route",
        "surface",
        "branch",
        "candidateAlias",
        "sourceInventoryItems",
        "recordPath",
        "reportPath",
        "evidenceDir",
        "planFingerprint",
        "sha256",
        "generatedGitHash",
        "tokenPolicy",
    }:
        return False
    if normalized_field == "hash" and HEX_IDENTIFIER_RE.match(text):
        return False
    if any(term in normalized_field for term in ["githash", "gitsha", "commithash", "commitsha", "revision", "sha256"]):
        return False
    if _url_contains_secret_locator(text):
        return True
    if SECRET_FIELD_RE.search(field_name) and text.lower() not in DUMMY_VALUES:
        return True
    if BEARER_RE.search(text):
        return True
    if HIGH_ENTROPY_RE.match(text) and not re.search(r"[-/\s]", text) and _entropy(text) > 3.5:
        return True
    return False


def runtime_input_name_looks_secret(name: str) -> bool:
    return bool(SECRET_FIELD_RE.search(name or ""))


def _url_contains_secret_locator(text: str) -> bool:
    if not re.match(r"^https?://", text, re.I):
        return False
    try:
        parsed = urlsplit(text)
    except ValueError:
        return False
    if parsed.username or parsed.password:
        return True
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        if SECRET_QUERY_PARAM_RE.search(key) and value and value.lower() not in DUMMY_VALUES:
            return True
    fragment = parsed.fragment or ""
    if fragment:
        if SECRET_QUERY_PARAM_RE.search(fragment):
            return True
        for key, value in parse_qsl(fragment, keep_blank_values=True):
            if SECRET_QUERY_PARAM_RE.search(key) and value and value.lower() not in DUMMY_VALUES:
                return True
    return False


def _entropy(text: str) -> float:
    if not text:
        return 0.0
    counts = {ch: text.count(ch) for ch in set(text)}
    return -sum((count / len(text)) * math.log2(count / len(text)) for count in counts.values())


def validate_no_secret_values(data: Any, path: str = "") -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    if isinstance(data, dict):
        for key, value in data.items():
            child_path = f"{path}.{key}" if path else str(key)
            if isinstance(value, (dict, list)):
                findings.extend(validate_no_secret_values(value, child_path))
            elif _is_public_credential_ref_key_name(child_path, value):
                continue
            elif _is_public_session_ref_key_name(child_path, value):
                continue
            elif _is_public_artifact_fingerprint(child_path, value):
                continue
            elif looks_secret(value, str(key)):
                findings.append({"severity": "blocking", "code": "secret-looking-value", "path": child_path, "message": "Secret-looking value must not be persisted."})
    elif isinstance(data, list):
        for index, value in enumerate(data):
            findings.extend(validate_no_secret_values(value, f"{path}[{index}]"))
    return findings


def validate_credential_readiness_hint(hint: CredentialReadinessHint | dict[str, Any]) -> list[dict[str, str]]:
    model = hint if isinstance(hint, CredentialReadinessHint) else CredentialReadinessHint.from_dict(hint)
    findings: list[dict[str, str]] = []
    if model.valuesIncluded:
        findings.append(
            {
                "severity": "blocking",
                "code": "credential-hint-values-included",
                "path": "valuesIncluded",
                "message": "Credential readiness hints must not include credential values.",
            }
        )
    for name in model.requiredRuntimeNames:
        if not ENV_VAR_NAME_RE.match(name):
            findings.append(
                {
                    "severity": "blocking",
                    "code": "credential-hint-invalid-runtime-name",
                    "path": "requiredRuntimeNames",
                    "message": f"Credential runtime name is not a valid public env-style name: {name}",
                }
            )
    if ENV_ASSIGNMENT_RE.search(model.preparationHint):
        findings.append(
            {
                "severity": "blocking",
                "code": "credential-hint-secret-looking-value",
                "path": "preparationHint",
                "message": "Credential readiness hints may name runtime variables but must not include KEY=value content.",
            }
        )
    findings.extend(validate_no_secret_values(model.to_dict(), "credentialReadinessHint"))
    return findings


def _is_public_credential_ref_key_name(path: str, value: Any) -> bool:
    marker_path = f".{path}"
    if ".credentialRefs." not in marker_path or ".keys." not in marker_path:
        return False
    return isinstance(value, str) and bool(ENV_VAR_NAME_RE.match(value.strip()))


def _is_public_session_ref_key_name(path: str, value: Any) -> bool:
    marker_path = f".{path}"
    if not marker_path.endswith(".sessionRef.key"):
        return False
    return isinstance(value, str) and bool(LOCAL_CONFIG_KEY_RE.match(value.strip()))


def _is_public_artifact_fingerprint(path: str, value: Any) -> bool:
    marker_path = f".{path}"
    if ".artifactFingerprints." not in marker_path:
        return False
    return isinstance(value, str) and bool(PUBLIC_DIGEST_RE.match(value.strip()))


def validate_workspace(project: Path) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    root = layout.workspace_root(project)
    if not root.exists():
        return [{"severity": "blocking", "code": "workspace-missing", "path": str(root), "message": "Workspace does not exist."}]

    registry = load_registry(project)
    aliases: set[str] = set()
    for item in registry.get("useCases", []):
        alias = item.get("alias", "")
        if alias in aliases:
            findings.append({"severity": "blocking", "code": "duplicate-alias", "path": layout.REGISTRY_FILE, "message": f"Duplicate alias: {alias}"})
        aliases.add(alias)
        record_path = item.get("recordPath", "")
        if not record_path:
            findings.append({"severity": "blocking", "code": "missing-record-path", "path": layout.REGISTRY_FILE, "message": f"Registry entry for {alias or '<unknown>'} is missing recordPath."})
            continue
        try:
            path = layout.project_relative_path(project, record_path)
        except Exception:
            findings.append({"severity": "blocking", "code": "invalid-record-path", "path": record_path, "message": "Record path escapes the project."})
            continue
        if not path.exists():
            findings.append({"severity": "blocking", "code": "missing-record", "path": record_path, "message": "Registry entry points to a missing use case record."})
            continue
        try:
            record = UseCaseRecord.from_dict(load_document(path))
            findings.extend(validate_use_case(project, record))
            findings.extend(validate_no_secret_values(record.to_dict(), record_path))
        except Exception as exc:
            findings.append({"severity": "blocking", "code": "invalid-record", "path": record_path, "message": str(exc)})

    findings.extend(validate_no_secret_values(load_document(layout.product_context_path(project), default={}), layout.PRODUCT_CONTEXT_FILE))
    for directory in [
        layout.READINESS_DIR,
        layout.CREDENTIAL_HINTS_DIR,
        layout.CONFIRMATIONS_DIR,
        layout.REFRESH_IMPACT_DIR,
        layout.CAPABILITY_POLICIES_DIR,
        layout.SUPERSEDE_REVIEWS_DIR,
    ]:
        root_dir = root / directory
        if not root_dir.exists():
            continue
        for path in root_dir.rglob("*.yaml"):
            data = load_document(path, default={})
            rel = f"{layout.WORKSPACE_DIR}/{directory}/{path.relative_to(root_dir)}"
            findings.extend(validate_no_secret_values(data, rel))
            if directory == layout.CREDENTIAL_HINTS_DIR and isinstance(data, dict):
                findings.extend(validate_credential_readiness_hint(data))
            if directory == layout.SUPERSEDE_REVIEWS_DIR and isinstance(data, dict):
                findings.extend(SupersedeReview.from_dict(data).validate())
    return findings


def validate_use_case(project: Path, record: UseCaseRecord) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    if not record.runRequest:
        findings.append({"severity": "blocking", "code": "missing-run-request", "path": record.alias, "message": "Use case must reference exactly one run request."})
    else:
        findings.extend(_validate_artifact(project, record.runRequest, generated_dir=layout.RUN_REQUESTS_DIR))
    if not record.mainSkill:
        findings.append({"severity": "blocking", "code": "missing-main-skill", "path": record.alias, "message": "Use case must reference a main skill."})
    else:
        findings.extend(_validate_artifact(project, record.mainSkill, generated_dir=layout.SKILLS_DIR))
    seen_skills: set[str] = set()
    for skill in [*record.skills, *record.sourceOnlySkills]:
        if skill.path in seen_skills:
            continue
        seen_skills.add(skill.path)
        findings.extend(_validate_artifact(project, skill, generated_dir=layout.SKILLS_DIR))
    for question in record.authoringQuestions:
        if question.status == "deferred" and record.status == "ready":
            findings.append({"severity": "blocking", "code": "deferred-question-ready", "path": record.alias, "message": "Ready use cases cannot have deferred blocking questions."})
    for profile in record.profiles:
        if profile.slowMoMs < 0:
            findings.append({"severity": "blocking", "code": "invalid-profile-slowmo", "path": record.alias, "message": f"Profile {profile.name} has negative slowMoMs."})
        findings.extend(validate_no_secret_values(profile.to_dict(), f"{record.alias}.profiles.{profile.name}"))
    findings.extend(validate_session_ref(record.sessionRef, f"{record.alias}.sessionRef"))
    if record.lastRun:
        findings.extend(validate_no_secret_values(record.lastRun, f"{record.alias}.lastRun"))
    if record.sideEffectLifecycle:
        findings.extend(validate_no_secret_values(record.sideEffectLifecycle, f"{record.alias}.sideEffectLifecycle"))
    if record.artifactCapabilities:
        findings.extend(validate_no_secret_values(record.artifactCapabilities, f"{record.alias}.artifactCapabilities"))
    findings.extend(_validate_generated_runtime_inputs(record))
    findings.extend(_validate_named_output_declarations(record))
    findings.extend(
        validate_side_effect_declaration(
            record.sideEffects,
            record.rerunPolicy,
            record.runtimeOutputs,
            [item.to_dict() for item in record.runtimeInputs],
        )
    )
    side_effect_data = record.sideEffects if isinstance(record.sideEffects, dict) else {}
    side_effect_class = str(side_effect_data.get("class") or side_effect_data.get("sideEffectClass") or "none")
    if record.resourceIdentity or "resource-identity" in _capability_names(record):
        findings.extend(
            ResourceIdentity.from_dict(record.resourceIdentity).validate(
                side_effect_class=side_effect_class,
                runtime_inputs=record.runtimeInputs,
            )
        )
    legacy = not bool(record.artifactCapabilities)
    findings.extend(validate_side_effect_lifecycle(record.sideEffectLifecycle or side_effect_data.get("lifecycle"), side_effect_class=side_effect_class, legacy=legacy))
    return findings


def validate_session_ref(session_ref: dict[str, Any] | None, path: str = "sessionRef") -> list[dict[str, str]]:
    if session_ref is None:
        return []
    findings: list[dict[str, str]] = []
    source = session_ref.get("source")
    key = session_ref.get("key")
    if source not in {"environment", "local-config"}:
        findings.append(
            {
                "severity": "blocking",
                "code": "session-ref-source-unsupported",
                "path": f"{path}.source",
                "message": "Session references must use the public environment or local-config source.",
            }
        )
    key_pattern = ENV_VAR_NAME_RE if source == "environment" else LOCAL_CONFIG_KEY_RE
    if not isinstance(key, str) or not key_pattern.match(key.strip()):
        findings.append(
            {
                "severity": "blocking",
                "code": "session-ref-key-invalid",
                "path": f"{path}.key",
                "message": "Session references must name an environment variable without including session material.",
            }
        )
    extra_fields = sorted(set(session_ref) - {"source", "key"})
    if extra_fields:
        findings.append(
            {
                "severity": "blocking",
                "code": "session-ref-material-forbidden",
                "path": path,
                "message": f"Session references cannot persist session material or extra fields: {', '.join(extra_fields)}.",
            }
        )
    findings.extend(validate_no_secret_values(session_ref, path))
    return findings


def validate_side_effect_declaration(
    declaration: dict[str, Any] | SideEffectDeclaration | None,
    rerun_policy: dict[str, Any] | RerunPolicy | None = None,
    runtime_outputs: list[dict[str, Any]] | None = None,
    runtime_inputs: list[dict[str, Any]] | None = None,
    *,
    core_contract: dict[str, Any] | None = None,
    runtime_outcomes: list[dict[str, Any] | None] | None = None,
) -> list[dict[str, str]]:
    from verifysignal_spec.workflows.write_safety import (
        canonical_side_effect_policy_snapshot,
        confirmation_placeholder_findings,
        confirmation_support_findings,
        normalize_side_effect_policy,
    )

    if isinstance(declaration, SideEffectDeclaration):
        side_effect = declaration
        compatibility_findings: list[dict[str, Any]] = []
    else:
        normalized, compatibility_findings = normalize_side_effect_policy(declaration if isinstance(declaration, dict) else None)
        side_effect = SideEffectDeclaration.from_dict(normalized)
    findings: list[dict[str, str]] = [
        {
            "severity": str(item.get("severity", "warning")),
            "code": str(item.get("code", "side-effect-policy-compatibility")),
            "path": str(item.get("path", "sideEffects")),
            "message": str(item.get("message", "")),
            **({"guidedChoices": item["guidedChoices"]} if item.get("guidedChoices") else {}),
            **({"migrationAvailable": item["migrationAvailable"]} if "migrationAvailable" in item else {}),
            **({"blocksExecution": item["blocksExecution"]} if "blocksExecution" in item else {}),
        }
        for item in compatibility_findings
    ]
    side_effect_class = side_effect.sideEffectClass
    findings.extend(
        _side_effect_observation_review_findings(
            canonical_side_effect_policy_snapshot(side_effect.to_dict()),
            runtime_outcomes or [],
            canonicalize=canonical_side_effect_policy_snapshot,
        )
    )
    if side_effect_class == "none":
        return findings
    supported = _side_effect_guardrails(core_contract)
    if core_contract is not None and not supported.get("supported", False):
        findings.append(_side_effect_finding("side-effect-core-contract-missing", "sideEffects", "Core does not expose sideEffectGuardrails; write readiness is blocked."))
        return findings
    if supported.get("supported", False):
        if side_effect_class not in set(supported.get("classes", [])):
            findings.append(_side_effect_finding("side-effect-class-unsupported", "sideEffects.class", f"Core does not support side-effect class '{side_effect_class}'."))
        if side_effect.policyMode not in set(supported.get("modes", [])):
            findings.append(_side_effect_finding("side-effect-mode-unsupported", "sideEffects.mode", f"Core does not support side-effect policy mode '{side_effect.policyMode}'."))
    if side_effect_class == "unknown":
        findings.append(_side_effect_finding("side-effect-class-unknown", "sideEffects.class", "Side-effect class must be resolved before executable readiness."))
    if side_effect_class in {"write", "external-notification"}:
        if not side_effect.commitStepId:
            findings.append(_side_effect_finding("side-effect-commit-step-missing", "sideEffects.commitStepId", "Write and external-notification use cases require the commit step id."))
        if not _has_local_envelope(side_effect):
            findings.append(_side_effect_finding("side-effect-envelope-missing", "sideEffects.allowed", "Write and external-notification use cases require at least one local side-effect envelope rule or confirmation signal."))
        if rerun_policy is None:
            findings.append(_side_effect_finding("rerun-policy-missing", "rerunPolicy", "Write and external-notification use cases require explicit rerun policy."))
    confirmation_types = set(supported.get("confirmationSignalTypes", [])) if supported.get("supported", False) else _default_confirmation_signal_types()
    for index, signal in enumerate(side_effect.confirmationSignals):
        signal_type = str(signal.get("type") or signal.get("source") or "")
        if signal_type and signal_type not in confirmation_types:
            findings.append(
                _side_effect_finding(
                    "side-effect-confirmation-signal-unsupported",
                    f"sideEffects.confirmationSignals[{index}].type",
                    f"Unsupported side-effect confirmation signal type: {signal_type}",
                )
            )
    if core_contract is not None or runtime_outcomes:
        findings.extend(
            [
                {
                    "severity": str(item.get("severity", "blocking")),
                    "code": str(item.get("code", "unsupported-confirmation-signal")),
                    "path": str(item.get("path", "sideEffects.confirmationSignals")),
                    "message": str(item.get("message", "")),
                    "signalType": str(item.get("signalType", "")),
                }
                for item in confirmation_support_findings(
                    side_effect.confirmationSignals,
                    core_contract=core_contract,
                    runtime_outcomes=runtime_outcomes or [],
                )
            ]
        )
    findings.extend(
        [
            {
                "severity": str(item.get("severity", "blocking")),
                "code": str(item.get("code", "confirmation-placeholder-unresolved")),
                "category": str(item.get("category", "side-effect-confirmation")),
                "path": str(item.get("path", "sideEffects.confirmationSignals")),
                "message": str(item.get("message", "")),
                "placeholder": str(item.get("placeholder", "")),
                "signalId": str(item.get("signalId", "")),
                "nextAction": str(item.get("nextAction", "")),
                "recoveryCommand": str(item.get("recoveryCommand", "")),
                **({"namespace": str(item["namespace"])} if item.get("namespace") else {}),
                **({"parameter": str(item["parameter"])} if item.get("parameter") else {}),
                **({"blocksExecution": item["blocksExecution"]} if "blocksExecution" in item else {}),
            }
            for item in confirmation_placeholder_findings(
                side_effect.confirmationSignals,
                _runtime_input_static_values(runtime_inputs or []),
                secret_checker=looks_secret,
            )
        ]
    )
    runtime_output_sources = set(supported.get("runtimeOutputSources", [])) if supported.get("supported", False) else _default_runtime_output_sources()
    for index, output in enumerate(runtime_outputs or []):
        source = str(output.get("source") or "")
        if source and source not in runtime_output_sources:
            findings.append(_side_effect_finding("runtime-output-source-unsupported", f"runtimeOutputs[{index}].source", f"Unsupported runtime output source: {source}"))
    if rerun_policy is not None:
        policy = rerun_policy if isinstance(rerun_policy, RerunPolicy) else RerunPolicy.from_dict(rerun_policy)
        refreshable_inputs = [
            str(item.get("name"))
            for item in (runtime_inputs or [])
            if isinstance(item, dict) and item.get("name") and (item.get("source") == "generated" or item.get("refreshOnRerunAfterCommit"))
        ]
        findings.extend(policy.validate(refreshable_inputs=refreshable_inputs))  # type: ignore[arg-type]
    return findings


def validate_side_effect_lifecycle(
    declaration: dict[str, Any] | SideEffectLifecycleDeclaration | None,
    *,
    side_effect_class: str,
    legacy: bool = False,
) -> list[dict[str, str]]:
    lifecycle = declaration if isinstance(declaration, SideEffectLifecycleDeclaration) else SideEffectLifecycleDeclaration.from_dict(declaration)
    findings: list[dict[str, str]] = []
    if side_effect_class not in {"write", "external-notification"}:
        return findings
    if lifecycle.cleanupPolicy == "not-declared":
        findings.append(
            {
                "severity": "warning" if legacy else "blocking",
                "code": "side-effect-lifecycle-missing",
                "path": "sideEffectLifecycle",
                "message": (
                    "Legacy write/external-notification use case has no cleanup lifecycle declaration."
                    if legacy
                    else "Write and external-notification use cases require cleanup lifecycle declaration."
                ),
            }
        )
    if lifecycle.cleanupPolicy in {"manual", "external"} and not lifecycle.instructions.strip():
        findings.append(
            {
                "severity": "blocking",
                "code": "side-effect-lifecycle-instructions-missing",
                "path": "sideEffectLifecycle.instructions",
                "message": "Manual or external cleanup lifecycle requires cleanup instructions.",
            }
        )
    findings.extend(validate_no_secret_values(lifecycle.to_dict(), "sideEffectLifecycle"))
    return findings


def _side_effect_guardrails(core_contract: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(core_contract, dict):
        return {"supported": False}
    sections = core_contract.get("sections") if isinstance(core_contract.get("sections"), dict) else {}
    guardrails = sections.get("sideEffectGuardrails") if isinstance(sections.get("sideEffectGuardrails"), dict) else {}
    if not guardrails:
        return {"supported": False}
    return {
        **guardrails,
        "supported": True if "supported" not in guardrails else bool(guardrails.get("supported")),
        "classes": _list_values(guardrails.get("classes") or guardrails.get("policyClasses") or guardrails.get("sideEffectClasses")),
        "modes": _list_values(guardrails.get("modes") or guardrails.get("policyModes")),
        "confirmationSignalTypes": _list_values(guardrails.get("confirmationSignalTypes")),
        "runtimeOutputSources": _list_values(guardrails.get("runtimeOutputSources")),
    }


def _has_local_envelope(side_effect: SideEffectDeclaration) -> bool:
    return bool(side_effect.allowed or side_effect.confirmationSignals)


def _side_effect_finding(code: str, path: str, message: str) -> dict[str, str]:
    return {"severity": "blocking", "code": code, "path": path, "message": message}


def _side_effect_observation_review_findings(
    current_policy: dict[str, Any],
    runtime_outcomes: list[dict[str, Any] | None],
    *,
    canonicalize,
) -> list[dict[str, str]]:
    latest = next(
        (item for item in reversed(runtime_outcomes) if isinstance(item, dict)),
        None,
    )
    if latest is None or not _runtime_side_effect_policy_violated(latest):
        return []

    observed = latest.get("sideEffects") if isinstance(latest.get("sideEffects"), dict) else {}
    previous_policy = latest.get("sideEffectPolicy")
    if not isinstance(previous_policy, dict):
        previous_policy = observed.get("policy") if isinstance(observed.get("policy"), dict) else None
    policy_changed = isinstance(previous_policy, dict) and canonicalize(previous_policy) != current_policy
    run_id = str(latest.get("runId") or "the latest run")
    if policy_changed:
        return [
            {
                "severity": "warning",
                "code": "side-effect-policy-changed-rerun-required",
                "path": "sideEffects",
                "message": (
                    f"Side-effect policy changed after {run_id} reported a violation. "
                    "A new clean run is required before strict pass."
                ),
            }
        ]
    return [
        {
            "severity": "blocking",
            "code": "side-effect-observation-review-required",
            "path": "sideEffects",
            "message": (
                f"{run_id} reported a side-effect policy violation under the current policy. "
                "Review the observed requests and update the policy explicitly when justified before rerunning."
            ),
        }
    ]


def _runtime_side_effect_policy_violated(outcome: dict[str, Any]) -> bool:
    side_effects = outcome.get("sideEffects") if isinstance(outcome.get("sideEffects"), dict) else {}
    violations = side_effects.get("violations")
    if isinstance(violations, list) and any(isinstance(item, dict) for item in violations):
        return True
    for field in ("postCommitInterpretation", "resultClassification"):
        classification = outcome.get(field) if isinstance(outcome.get(field), dict) else {}
        if str(classification.get("sideEffectStatus") or "") == "violated":
            return True
    return str(side_effects.get("status") or "") == "violated"


def _default_confirmation_signal_types() -> set[str]:
    return {"finalUrl", "runtimeOutput", "allowedNetworkObservation"}


def _default_runtime_output_sources() -> set[str]:
    return {"finalUrl", "location", "dom", "network"}


def _runtime_input_static_values(runtime_inputs: list[dict[str, Any]]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for item in runtime_inputs:
        if not isinstance(item, dict):
            continue
        if item.get("kind") == "credential":
            continue
        name = item.get("name")
        if not name:
            continue
        value = item.get("value")
        if value is None or value == "":
            value = item.get("default")
        if value is not None and value != "":
            values[str(name)] = value
    return values


def _list_values(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        if isinstance(item, str) and item:
            result.append(item)
        elif isinstance(item, dict):
            name = item.get("name")
            if name:
                result.append(str(name))
    return result


def _validate_generated_runtime_inputs(record: UseCaseRecord) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for item in record.runtimeInputs:
        if item.source != "generated":
            continue
        path = f"{record.alias}.runtimeInputs.{item.name}"
        if runtime_input_name_looks_secret(item.name):
            findings.append(
                {
                    "severity": "blocking",
                    "code": "generated-runtime-input-secret-name",
                    "path": path,
                    "message": f"Generated runtime input name looks secret-bearing: {item.name}",
                }
            )
        for field_name, value in {"template": item.template, "default": item.default, "value": item.value}.items():
            if value and looks_secret(value, field_name):
                findings.append(
                    {
                        "severity": "blocking",
                        "code": "generated-runtime-input-secret-value",
                        "path": f"{path}.{field_name}",
                        "message": f"Generated runtime input {item.name} contains a secret-looking {field_name}.",
                    }
                )
    return findings


def _validate_named_output_declarations(record: UseCaseRecord) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for index, item in enumerate(record.runtimeOutputs):
        if not isinstance(item, dict) or not item.get("publishAsNamedOutput"):
            continue
        path = f"{record.alias}.runtimeOutputs[{index}]"
        name = str(item.get("name") or "")
        if not name:
            findings.append({"severity": "blocking", "code": "named-output-name-missing", "path": path, "message": "Published named outputs require a name."})
        if runtime_input_name_looks_secret(name):
            findings.append(
                {
                    "severity": "blocking",
                    "code": "named-output-secret-name",
                    "path": f"{path}.name",
                    "message": f"Named output name looks secret-bearing: {name}",
                }
            )
        source = str(item.get("source") or "")
        if source in {"credential", "credentialValue", "env"}:
            findings.append(
                {
                    "severity": "blocking",
                    "code": "named-output-secret-source",
                    "path": f"{path}.source",
                    "message": "Credential or environment secret values cannot be published as named outputs.",
                }
            )
    return findings


def refresh_collision_finding(*, input_name: str, runtime_input: Any | None = None) -> dict[str, Any]:
    repairability = "owner-action-required"
    suggested_replacement: dict[str, Any] | None = None
    if (
        runtime_input is not None
        and getattr(runtime_input, "source", "") == "generated"
        and (
            getattr(runtime_input, "template", None)
            or getattr(runtime_input, "default", None)
            or getattr(runtime_input, "value", None)
            or getattr(runtime_input, "refreshOnRerunAfterCommit", False)
        )
    ):
        repairability = "ai-repairable"
        suggested_replacement = {"input": input_name, "action": "adjust-generation-template-or-seed"}
    finding: dict[str, Any] = {
        "severity": "blocking",
        "code": "generated-binding-collision",
        "category": "generated-binding",
        "path": f"runtimeInputs.{input_name}",
        "message": f"Generated runtime input {input_name} repeats a committed binding for this use case and target.",
        "repairability": repairability,
    }
    if suggested_replacement:
        finding["suggestedReplacement"] = suggested_replacement
    return finding


def _validate_artifact(project: Path, artifact: ArtifactReference, generated_dir: str) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    try:
        path = layout.project_relative_path(project, artifact.path)
    except Exception:
        return [{"severity": "blocking", "code": "artifact-path-escapes-project", "path": artifact.path, "message": "Artifact path escapes target project."}]
    if not path.exists():
        findings.append({"severity": "blocking", "code": "missing-artifact", "path": artifact.path, "message": "Referenced artifact does not exist."})
    expected_prefix = f"{layout.WORKSPACE_DIR}/{generated_dir}/"
    if artifact.generated and artifact.kind == "skill":
        remainder = artifact.path.removeprefix(f"{layout.WORKSPACE_DIR}/{layout.SKILLS_DIR}/")
        if (
            not artifact.path.startswith(f"{layout.WORKSPACE_DIR}/{layout.SKILLS_DIR}/")
            or not artifact.path.endswith(".browser.md")
            or "/" in remainder
        ):
            findings.append(
                {
                    "severity": "blocking",
                    "code": "non-canonical-generated-skill",
                    "path": artifact.path,
                    "message": "Generated browser skills must be single markdown files at .verifysignal/skills/<name>.browser.md.",
                }
            )
    if artifact.generated and artifact.kind == "run-request":
        if not artifact.path.startswith(f"{layout.WORKSPACE_DIR}/{layout.RUN_REQUESTS_DIR}/"):
            findings.append(
                {
                    "severity": "blocking",
                    "code": "non-canonical-generated-run-request",
                    "path": artifact.path,
                    "message": "Generated run requests must be under .verifysignal/run-requests/.",
                }
            )
    if artifact.generated and not artifact.path.startswith(expected_prefix):
        findings.append({"severity": "blocking", "code": "generated-artifact-outside-canonical-dir", "path": artifact.path, "message": "Generated artifact is outside the canonical directory."})
    if not artifact.generated and artifact.path.startswith(f"{layout.WORKSPACE_DIR}/"):
        findings.append({"severity": "warning", "code": "external-artifact-in-managed-workspace", "path": artifact.path, "message": "External artifact is inside the managed workspace."})
    return findings


def status_from_findings(findings: Iterable[dict[str, Any]]) -> str:
    return "blocked" if any(item.get("severity") == "blocking" for item in findings) else "passed"


def _capability_names(record: UseCaseRecord) -> set[str]:
    raw = record.artifactCapabilities if isinstance(record.artifactCapabilities, dict) else {}
    if isinstance(raw.get("capabilities"), list):
        return {str(item) for item in raw.get("capabilities", [])}
    stamp = raw.get("stamp") if isinstance(raw.get("stamp"), dict) else {}
    if isinstance(stamp.get("capabilities"), list):
        return {str(item) for item in stamp.get("capabilities", [])}
    return set()
