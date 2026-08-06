from __future__ import annotations

import json
import hashlib
import re
from dataclasses import asdict
from collections.abc import Callable
from typing import Any

from verifysignal_spec.workspace.models import (
    ConfirmationSignalSupport,
    PolicyCompatibilityFinding,
    RerunPolicy,
    SideEffectDeclaration,
    SupersedeReview,
)
from verifysignal_spec.workflows.repair_recommendations import combine_rerun_decision


PLACEHOLDER_RE = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")
CONFIRMATION_EXPECTED_VALUE_FIELDS = {
    "expected",
    "expectedContains",
    "expectedEquals",
    "contains",
    "equals",
    "pattern",
    "urlContains",
}
RERUN_CONFIRMATION_SCOPE = "rerun-after-commit"
UNKNOWN_RERUN_CONFIRMATION_SCOPE = "rerun-after-unknown"


def normalize_side_effect_policy(policy: dict[str, Any] | None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Return Core-runtime-compatible side-effect policy plus compatibility findings.

    Legacy Spec artifacts used sideEffectPolicy.rules[].effect/match. Core runtime
    consumes sideEffectPolicy.allowed[] and sideEffectPolicy.forbidden[] with match
    keys at the rule top level. This helper accepts the legacy shape only as an
    input compatibility format and never emits `rules`.
    """

    if not isinstance(policy, dict):
        return {}, []

    canonical = {key: value for key, value in policy.items() if key != "rules"}
    side_effect_class = str(
        canonical.get("class")
        or canonical.get("sideEffectClass")
        or "none"
    )
    if not canonical.get("mode"):
        canonical["mode"] = (
            "enforce"
            if side_effect_class in {"write", "external-notification"}
            else "observe"
        )
    findings: list[dict[str, Any]] = []
    existing_allowed, allowed_findings = _normalize_rule_list(canonical.get("allowed"), "sideEffects.allowed")
    existing_forbidden, forbidden_findings = _normalize_rule_list(canonical.get("forbidden"), "sideEffects.forbidden")
    findings.extend(allowed_findings)
    findings.extend(forbidden_findings)
    if "allowed" in canonical:
        canonical["allowed"] = existing_allowed
    if "forbidden" in canonical:
        canonical["forbidden"] = existing_forbidden
    legacy_rules = policy.get("rules")
    if not isinstance(legacy_rules, list) or not legacy_rules:
        _ensure_canonical_lists(canonical)
        return canonical, findings

    migrated_allowed: list[dict[str, Any]] = []
    migrated_forbidden: list[dict[str, Any]] = []
    ambiguous = False
    for index, item in enumerate(legacy_rules):
        migrated, target = _migrate_legacy_rule(item)
        if migrated is None or target is None:
            ambiguous = True
            findings.append(
                PolicyCompatibilityFinding(
                    code="legacy-side-effect-rule-ambiguous",
                    severity="blocking",
                    path=f"sideEffects.rules[{index}]",
                    message="Legacy side-effect rule cannot be migrated safely because its effect or match envelope is ambiguous.",
                    migrationAvailable=False,
                    guidedChoices=_policy_guided_choices(),
                    blocksExecution=True,
                ).to_dict()
            )
            continue
        if target == "allowed":
            migrated_allowed.append(migrated)
        else:
            migrated_forbidden.append(migrated)

    existing_allowed = list(canonical.get("allowed", [])) if isinstance(canonical.get("allowed"), list) else []
    existing_forbidden = list(canonical.get("forbidden", [])) if isinstance(canonical.get("forbidden"), list) else []
    if ambiguous:
        _ensure_canonical_lists(canonical)
        return canonical, findings

    conflict = False
    if existing_allowed and migrated_allowed and not _same_rules(existing_allowed, migrated_allowed):
        conflict = True
    if existing_forbidden and migrated_forbidden and not _same_rules(existing_forbidden, migrated_forbidden):
        conflict = True
    if conflict:
        findings.append(
            PolicyCompatibilityFinding(
                code="conflicting-side-effect-policy",
                severity="blocking",
                path="sideEffects",
                message="Legacy side-effect policy conflicts with canonical allowed/forbidden policy. Choose which policy represents owner intent before running.",
                migrationAvailable=False,
                guidedChoices=_policy_guided_choices(),
                blocksExecution=True,
            ).to_dict()
        )
        _ensure_canonical_lists(canonical)
        return canonical, findings

    if migrated_allowed and not existing_allowed:
        canonical["allowed"] = migrated_allowed
    if migrated_forbidden and not existing_forbidden:
        canonical["forbidden"] = migrated_forbidden
    findings.append(
        PolicyCompatibilityFinding(
            code="legacy-side-effect-rules",
            severity="warning",
            path="sideEffects.rules",
            message="Legacy side-effect rules were migrated to Core-compatible allowed/forbidden policy fields.",
            migrationAvailable=True,
            guidedChoices=[],
            blocksExecution=False,
        ).to_dict()
    )
    _ensure_canonical_lists(canonical)
    return canonical, findings


def policy_compatibility_findings(policy: dict[str, Any] | None) -> list[dict[str, Any]]:
    _canonical, findings = normalize_side_effect_policy(policy)
    return findings


def canonical_side_effect_policy_snapshot(policy: dict[str, Any] | None) -> dict[str, Any]:
    """Return the secret-safe semantic policy shape used to reconcile runs.

    Ordering and owner-facing notes do not change runtime policy semantics, so
    they cannot be used to bypass a prior observation review.
    """

    normalized, _findings = normalize_side_effect_policy(policy)
    snapshot = SideEffectDeclaration.from_dict(normalized).to_dict()
    snapshot.pop("notes", None)
    for key in ("allowed", "forbidden", "confirmationSignals"):
        values = snapshot.get(key)
        if isinstance(values, list):
            snapshot[key] = sorted(
                (item for item in values if isinstance(item, dict)),
                key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":")),
            )
    return snapshot


def resolve_confirmation_signal_placeholders(
    signals: list[dict[str, Any]],
    parameters: dict[str, Any],
    *,
    path_prefix: str = "sideEffects.confirmationSignals",
    secret_checker: Callable[[Any, str], bool] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Resolve safe Spec placeholders in confirmation expected-value fields.

    Core-facing run requests compare concrete values. This accepts only
    `{{parameters.<name>}}` placeholders in expected-value fields and reports
    blocking findings for missing values, unsupported namespaces, or resolved
    secret-looking values.
    """

    resolved_signals: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    for index, signal in enumerate(signals):
        if not isinstance(signal, dict):
            resolved_signals.append(signal)
            continue
        next_signal = dict(signal)
        signal_id = str(signal.get("id") or f"confirmation-{index}")
        for field in sorted(CONFIRMATION_EXPECTED_VALUE_FIELDS):
            raw_value = next_signal.get(field)
            if not isinstance(raw_value, str) or "{{" not in raw_value:
                continue
            path = f"{path_prefix}[{index}].{field}"
            resolved_value, field_findings = _resolve_confirmation_expected_value(
                raw_value,
                parameters,
                path=path,
                signal_id=signal_id,
                field=field,
                secret_checker=secret_checker,
            )
            findings.extend(field_findings)
            if not field_findings:
                next_signal[field] = resolved_value
        resolved_signals.append(next_signal)
    return resolved_signals, findings


def confirmation_placeholder_findings(
    signals: list[dict[str, Any]],
    parameters: dict[str, Any],
    *,
    path_prefix: str = "sideEffects.confirmationSignals",
    secret_checker: Callable[[Any, str], bool] | None = None,
) -> list[dict[str, Any]]:
    _resolved, findings = resolve_confirmation_signal_placeholders(
        signals,
        parameters,
        path_prefix=path_prefix,
        secret_checker=secret_checker,
    )
    return findings


def _resolve_confirmation_expected_value(
    raw_value: str,
    parameters: dict[str, Any],
    *,
    path: str,
    signal_id: str,
    field: str,
    secret_checker: Callable[[Any, str], bool] | None,
) -> tuple[str, list[dict[str, Any]]]:
    matches = list(PLACEHOLDER_RE.finditer(raw_value))
    if not matches:
        return raw_value, []

    findings: list[dict[str, Any]] = []
    replacements: dict[str, str] = {}
    for match in matches:
        placeholder = match.group(0)
        expression = match.group(1).strip()
        namespace, separator, name = expression.partition(".")
        if separator != "." or namespace != "parameters":
            findings.append(
                _confirmation_placeholder_finding(
                    code="confirmation-placeholder-unsupported-namespace",
                    path=path,
                    message=f"Confirmation {signal_id} uses unsupported placeholder namespace {namespace or expression}.",
                    placeholder=placeholder,
                    signal_id=signal_id,
                    namespace=namespace or expression,
                )
            )
            continue
        if name not in parameters or parameters.get(name) in {None, ""}:
            findings.append(
                _confirmation_placeholder_finding(
                    code="confirmation-placeholder-unresolved",
                    path=path,
                    message=f"Confirmation {signal_id} references unresolved placeholder {placeholder}.",
                    placeholder=placeholder,
                    signal_id=signal_id,
                    parameter=name,
                )
            )
            continue
        replacements[placeholder] = str(parameters[name])

    if findings:
        return raw_value, findings

    resolved = raw_value
    for placeholder, value in replacements.items():
        resolved = resolved.replace(placeholder, value)
    if secret_checker and secret_checker(resolved, field):
        return raw_value, [
            _confirmation_placeholder_finding(
                code="confirmation-placeholder-secret-value",
                path=path,
                message=f"Confirmation {signal_id} resolves to a secret-looking value and cannot be persisted in a prepared run request.",
                placeholder=matches[0].group(0),
                signal_id=signal_id,
            )
        ]
    return resolved, []


def _confirmation_placeholder_finding(
    *,
    code: str,
    path: str,
    message: str,
    placeholder: str,
    signal_id: str,
    namespace: str | None = None,
    parameter: str | None = None,
) -> dict[str, Any]:
    finding: dict[str, Any] = {
        "severity": "blocking",
        "code": code,
        "category": "side-effect-confirmation",
        "path": path,
        "message": message,
        "placeholder": placeholder,
        "signalId": signal_id,
        "blocksExecution": True,
        "nextAction": _confirmation_placeholder_next_action(code),
        "recoveryCommand": "verifysignal workflow check validate --alias <alias> --json",
    }
    if namespace:
        finding["namespace"] = namespace
    if parameter:
        finding["parameter"] = parameter
    return finding


def _confirmation_placeholder_next_action(code: str) -> str:
    if code == "confirmation-placeholder-unsupported-namespace":
        return "Use a non-secret runtime parameter or a literal expected value in the confirmation signal."
    if code == "confirmation-placeholder-secret-value":
        return "Replace the confirmation with a non-secret runtime parameter or a safe literal expected value."
    return "Declare or provide the runtime input before running this write use case."


def effective_confirmation_support(
    signal_type: str,
    *,
    core_contract: dict[str, Any] | None = None,
    runtime_outcomes: list[dict[str, Any] | None] | None = None,
) -> ConfirmationSignalSupport:
    static_types = set(_confirmation_signal_types(core_contract))
    static_support = signal_type in static_types if static_types else signal_type in {"finalUrl", "runtimeOutput", "allowedNetworkObservation"}
    explicit_runtime = _explicit_runtime_confirmation_support(core_contract, signal_type)
    unsupported_evidence = _runtime_unsupported_confirmation_evidence(runtime_outcomes or [], signal_type)
    if explicit_runtime is not None:
        runtime_support = explicit_runtime
        evidence = "public runtime capability data proves support" if explicit_runtime else "public runtime capability data marks unsupported"
    elif unsupported_evidence:
        runtime_support = False
        evidence = unsupported_evidence
    else:
        runtime_support = None
        evidence = "static public contract projection"
    return ConfirmationSignalSupport(
        signalType=signal_type,
        staticSupport=static_support,
        runtimeSupport=runtime_support,
        effectiveSupport=bool(static_support and runtime_support is not False),
        evidence=evidence,
    )


def confirmation_support_findings(
    signals: list[dict[str, Any]],
    *,
    core_contract: dict[str, Any] | None = None,
    runtime_outcomes: list[dict[str, Any] | None] | None = None,
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for index, signal in enumerate(signals):
        signal_type = str(signal.get("type") or signal.get("source") or "")
        if not signal_type:
            continue
        support = effective_confirmation_support(signal_type, core_contract=core_contract, runtime_outcomes=runtime_outcomes)
        if support.effectiveSupport:
            continue
        findings.append(
            {
                "severity": "blocking",
                "code": "unsupported-confirmation-signal",
                "path": f"sideEffects.confirmationSignals[{index}].type",
                "message": (
                    f"Confirmation signal type '{signal_type}' is not proven runtime-supported; "
                    f"runtime outcome or capability evidence: {support.evidence}."
                ),
                "signalType": signal_type,
                "support": support.to_dict(),
            }
        )
    return findings


def evaluate_rerun_decision(record: Any, *, supersede_reviews: list[Any] | None = None) -> dict[str, Any]:
    classification = _classify_previous_run(record)
    outcome_class = classification["outcomeClass"]
    policy_branch = classification["policyBranch"]
    source_run_id = classification.get("sourceRunId")
    policy = RerunPolicy.from_dict(record.rerunPolicy)
    if policy_branch == "none":
        return {
            "decision": "allowed",
            "outcomeClass": "none",
            "policyBranch": "none",
            "reason": "No previous real run or later run attempt requires rerun policy evaluation.",
            "refreshRuntimeInputs": [],
            "nextAction": "Proceed with run.",
        }

    last_run = record.lastRun if isinstance(record.lastRun, dict) else {}
    interpretation = last_run.get("postCommitInterpretation") if isinstance(last_run.get("postCommitInterpretation"), dict) else {}
    result_classification = last_run.get("resultClassification") if isinstance(last_run.get("resultClassification"), dict) else {}
    if policy_branch == "afterCommit":
        spec_decision = policy.afterCommit
        core_risk = str(interpretation.get("rerunRisk") or result_classification.get("rerunRisk") or "requires-confirmation")
    elif policy_branch == "afterUnknown":
        spec_decision = policy.afterUnknown
        core_risk = "requires-confirmation"
    else:
        spec_decision = policy.afterNoCommit
        core_risk = "safe"

    supersede = (
        _matching_supersede_review(last_run, supersede_reviews or [])
        if source_run_id
        else _matching_attempt_review(record, supersede_reviews or [])
        if outcome_class == "unknown-write"
        else None
    )
    if supersede is not None:
        resulting = getattr(supersede, "resultingClassification", None)
        if not isinstance(resulting, dict) and isinstance(supersede, dict):
            resulting = supersede.get("resultingClassification")
        if isinstance(resulting, dict) and resulting.get("rerunRisk"):
            core_risk = str(resulting["rerunRisk"])
            if spec_decision == "requires-confirmation":
                spec_decision = "allowed"

    decision = combine_rerun_decision(core_risk, spec_decision)
    refreshable = {item.name for item in record.runtimeInputs if item.source == "generated" and item.refreshOnRerunAfterCommit}
    refresh_names = [name for name in policy.refreshRuntimeInputs if name in refreshable]
    if decision == "allowed-with-new-inputs" and not refresh_names:
        return {
            "decision": "blocked",
            "outcomeClass": outcome_class,
            "policyBranch": policy_branch,
            "coreRisk": core_risk,
            "specDecision": spec_decision,
            "reason": "Rerun requires refreshed generated inputs, but no declared refreshable generated input is available.",
            "refreshRuntimeInputs": [],
            "nextAction": f"Update rerunPolicy.refreshRuntimeInputs for {record.alias} before rerunning.",
        }
    if decision == "blocked":
        reason = f"Rerun is blocked by the {outcome_class} outcome and declared {policy_branch} policy."
        next_action = f"verifysignal workflow supersede-write-outcome --alias {record.alias} --json"
    elif decision == "requires-confirmation":
        reason = (
            "Rerun requires explicit owner confirmation because the latest write attempt has unknown execution state."
            if outcome_class == "unknown-write"
            else "Rerun requires explicit owner confirmation because the previous write may have crossed the commit boundary."
        )
        confirmation_scope = (
            UNKNOWN_RERUN_CONFIRMATION_SCOPE
            if outcome_class == "unknown-write"
            else RERUN_CONFIRMATION_SCOPE
        )
        confirmation_id = (
            f"confirm.{_path_safe(record.alias)}.{confirmation_scope}.{_path_safe(_attempt_review_source(record))}"
            if not source_run_id
            else rerun_confirmation_id(record.alias, str(source_run_id))
        )
        next_action = f"verifysignal workflow approve-rerun --alias {record.alias} --confirm-risk {confirmation_id} --json"
    elif decision == "allowed-with-new-inputs":
        reason = "Rerun is allowed only with refreshed generated runtime inputs."
        next_action = "Proceed with run."
    else:
        reason = "Rerun is allowed by Core risk and Spec rerun policy."
        next_action = "Proceed with run."
    result = {
        "decision": decision,
        "outcomeClass": outcome_class,
        "policyBranch": policy_branch,
        "coreRisk": core_risk,
        "specDecision": spec_decision,
        "reason": reason,
        "refreshRuntimeInputs": refresh_names,
        "nextAction": next_action,
        **({"supersededBy": getattr(supersede, "reviewId", None) or (supersede.get("reviewId") if isinstance(supersede, dict) else None)} if supersede is not None else {}),
    }
    if decision == "requires-confirmation":
        result.update(
            {
                "confirmationId": confirmation_id,
                "confirmationScope": confirmation_scope,
            }
        )
        if source_run_id:
            result["sourceRunId"] = str(source_run_id)
    elif source_run_id:
        result["sourceRunId"] = str(source_run_id)
    return result


def _classify_previous_run(record: Any) -> dict[str, Any]:
    """Select one rerun-policy branch from real-run and later-attempt evidence."""

    last_run = record.lastRun if isinstance(record.lastRun, dict) else None
    attempt_model = getattr(record, "lastCoreAttempt", None)
    attempt = (
        attempt_model.to_dict()
        if hasattr(attempt_model, "to_dict")
        else attempt_model
        if isinstance(attempt_model, dict)
        else None
    )
    if isinstance(attempt, dict) and attempt.get("operation") == "run" and _attempt_is_later(attempt, last_run):
        explicitly_safe = (
            attempt.get("executionState") == "not-started"
            or attempt.get("sideEffectMayExist") is False
        )
        if explicitly_safe:
            return {"outcomeClass": "no-commit", "policyBranch": "afterNoCommit"}
        if _has_write_evidence(record, last_run):
            return {"outcomeClass": "unknown-write", "policyBranch": "afterUnknown"}
        return {"outcomeClass": "no-commit", "policyBranch": "afterNoCommit"}

    if not last_run:
        return {"outcomeClass": "none", "policyBranch": "none"}

    interpretation = last_run.get("postCommitInterpretation") if isinstance(last_run.get("postCommitInterpretation"), dict) else {}
    result_classification = last_run.get("resultClassification") if isinstance(last_run.get("resultClassification"), dict) else {}
    evidence = {**result_classification, **interpretation}
    source = {"sourceRunId": str(last_run.get("runId"))} if last_run.get("runId") else {}
    explicitly_safe = (
        evidence.get("postCommit") is False
        and evidence.get("sideEffectMayExist") is False
    ) or (
        evidence.get("sideEffectMayExist") is False
        and str(evidence.get("sideEffectStatus") or "").lower() in {"not-started", "none", "not-committed"}
    )
    if explicitly_safe:
        return {"outcomeClass": "no-commit", "policyBranch": "afterNoCommit", **source}
    if not evidence:
        return (
            {"outcomeClass": "unknown-write", "policyBranch": "afterUnknown", **source}
            if _has_write_evidence(record, last_run)
            else {"outcomeClass": "no-commit", "policyBranch": "afterNoCommit", **source}
        )
    committed_statuses = {"possible", "inferred", "likely-committed", "committed", "committed-confirmed", "violated"}
    if _has_write_evidence(record, last_run) and (
        evidence.get("postCommit") is True
        or evidence.get("sideEffectMayExist") is True
        or str(evidence.get("sideEffectStatus") or "").lower() in committed_statuses
    ):
        return {"outcomeClass": "commit", "policyBranch": "afterCommit", **source}
    if _has_write_evidence(record, last_run):
        return {"outcomeClass": "unknown-write", "policyBranch": "afterUnknown", **source}
    return {"outcomeClass": "no-commit", "policyBranch": "afterNoCommit", **source}


def _has_write_evidence(record: Any, last_run: dict[str, Any] | None) -> bool:
    current = record.sideEffects if isinstance(record.sideEffects, dict) else {}
    if str(current.get("class") or current.get("sideEffectClass") or "none") in {"write", "external-notification"}:
        return True
    if not isinstance(last_run, dict):
        return False
    for field in ("sideEffectPolicy", "sideEffects"):
        value = last_run.get(field)
        if isinstance(value, dict) and str(value.get("class") or value.get("sideEffectClass") or "") in {"write", "external-notification"}:
            return True
    interpretation = (
        last_run.get("postCommitInterpretation")
        if isinstance(last_run.get("postCommitInterpretation"), dict)
        else {}
    )
    classification = (
        last_run.get("resultClassification")
        if isinstance(last_run.get("resultClassification"), dict)
        else {}
    )
    evidence = {**classification, **interpretation}
    if evidence.get("postCommit") is True or evidence.get("sideEffectMayExist") is True:
        return True
    return str(evidence.get("sideEffectStatus") or "").lower() in {
        "possible",
        "inferred",
        "likely-committed",
        "committed",
        "committed-confirmed",
    }


def _attempt_is_later(attempt: dict[str, Any], last_run: dict[str, Any] | None) -> bool:
    if not last_run:
        return True
    attempt_at = _parse_evidence_time(attempt.get("attemptedAt"))
    run_at = _parse_evidence_time(last_run.get("completedAt") or last_run.get("startedAt"))
    # The marker is cleared after every valid persisted run, so absent legacy
    # timestamps still make a present run marker the latest relevant evidence.
    if run_at is None:
        return True
    if attempt_at is None:
        return False
    return attempt_at > run_at


def _attempt_review_source(record: Any) -> str:
    attempt_model = getattr(record, "lastCoreAttempt", None)
    attempt = attempt_model.to_dict() if hasattr(attempt_model, "to_dict") else attempt_model
    projection = _attempt_identity_projection(attempt)
    encoded = json.dumps(
        projection,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return f"core-attempt-{hashlib.sha256(encoded).hexdigest()[:24]}"


def _legacy_attempt_review_source(record: Any) -> str:
    attempt_model = getattr(record, "lastCoreAttempt", None)
    attempt = attempt_model.to_dict() if hasattr(attempt_model, "to_dict") else attempt_model
    attempted_at = attempt.get("attemptedAt") if isinstance(attempt, dict) else None
    return f"core-attempt-{_path_safe(str(attempted_at or 'unknown'))}"


def _attempt_identity_projection(attempt: Any) -> dict[str, Any]:
    value = attempt if isinstance(attempt, dict) else {}
    return {
        "attemptedAt": str(value.get("attemptedAt") or ""),
        "operation": str(value.get("operation") or ""),
        "schema": value.get("schema") if isinstance(value.get("schema"), str) else None,
        "status": str(value.get("status") or ""),
        "errorCode": value.get("errorCode") if isinstance(value.get("errorCode"), str) else None,
        "executionState": str(value.get("executionState") or "unknown"),
        "sideEffectMayExist": (
            value.get("sideEffectMayExist")
            if isinstance(value.get("sideEffectMayExist"), bool)
            else None
        ),
    }


def _matching_attempt_review(record: Any, reviews: list[Any]) -> Any | None:
    expected = _attempt_review_source(record)
    legacy_expected = _legacy_attempt_review_source(record)
    for review in reviews:
        source_run_id = getattr(review, "sourceRunId", None)
        if source_run_id is None and isinstance(review, dict):
            source_run_id = review.get("sourceRunId")
        if str(source_run_id or "") == expected:
            return review
        if (
            str(source_run_id or "") == legacy_expected
            and _legacy_attempt_review_matches(record, review)
        ):
            return review
    return None


def _legacy_attempt_review_matches(record: Any, review: Any) -> bool:
    """Accept an old timestamp-scoped review only with exact conservative evidence."""

    attempt_model = getattr(record, "lastCoreAttempt", None)
    attempt = attempt_model.to_dict() if hasattr(attempt_model, "to_dict") else attempt_model
    if not isinstance(attempt, dict):
        return False
    previous = getattr(review, "previousClassification", None)
    if not isinstance(previous, dict) and isinstance(review, dict):
        previous = review.get("previousClassification")
    owner_decision = getattr(review, "ownerDecision", None)
    created_at = getattr(review, "createdAt", None)
    if isinstance(review, dict):
        owner_decision = owner_decision or review.get("ownerDecision")
        created_at = created_at or review.get("createdAt")
    if not isinstance(previous, dict) or owner_decision != "approved-rerun-after-write":
        return False
    if previous.get("executionState") != str(attempt.get("executionState") or "unknown"):
        return False
    if previous.get("sideEffectMayExist") is not attempt.get("sideEffectMayExist"):
        return False
    review_time = _parse_evidence_time(created_at)
    attempt_time = _parse_evidence_time(attempt.get("attemptedAt"))
    return bool(review_time is not None and attempt_time is not None and review_time > attempt_time)


def _parse_evidence_time(value: Any) -> Any | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        from datetime import UTC, datetime

        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
    except ValueError:
        return None


def rerun_confirmation_id(alias: str, source_run_id: str) -> str:
    return f"confirm.{_path_safe(alias)}.{RERUN_CONFIRMATION_SCOPE}.{_path_safe(source_run_id)}"


def build_rerun_approval_review(
    record: Any,
    rerun_decision: dict[str, Any],
    *,
    created_at: str,
    created_by: str | None = None,
) -> SupersedeReview:
    last_run = record.lastRun if isinstance(record.lastRun, dict) else {}
    attempt_model = getattr(record, "lastCoreAttempt", None)
    attempt = attempt_model.to_dict() if hasattr(attempt_model, "to_dict") else attempt_model
    latest_is_attempt = bool(
        rerun_decision.get("outcomeClass") == "unknown-write"
        and isinstance(attempt, dict)
        and attempt.get("operation") == "run"
        and _attempt_is_later(attempt, last_run)
    )
    source_run_id = str(
        _attempt_review_source(record)
        if latest_is_attempt
        else last_run.get("runId") or rerun_decision.get("sourceRunId") or _attempt_review_source(record)
    )
    previous = _classification_from_last_run(last_run) if not latest_is_attempt else {}
    if not previous and isinstance(attempt, dict):
        previous = {
            "executionState": str(attempt.get("executionState") or "unknown"),
            "sideEffectMayExist": attempt.get("sideEffectMayExist"),
            "rerunRisk": "requires-confirmation",
        }
    resulting = dict(previous)
    resulting["rerunRisk"] = "safe-with-new-inputs" if rerun_decision.get("refreshRuntimeInputs") else "safe"
    resulting.setdefault("sideEffectStatus", previous.get("sideEffectStatus") or "unknown")
    resulting.setdefault("postCommit", previous.get("postCommit", False))
    resulting.setdefault("sideEffectMayExist", previous.get("sideEffectMayExist"))
    return SupersedeReview(
        reviewId=f"approve-rerun-{_path_safe(record.alias)}-{_path_safe(source_run_id)}-{_path_safe(created_at)}",
        sourceRunId=source_run_id,
        ownerDecision="approved-rerun-after-write",
        evidenceSummary="Owner approved rerun after reviewing that the previous write may have crossed the commit boundary.",
        previousClassification=previous,
        resultingClassification=resulting,
        reason="Owner approved rerun under the declared rerun policy; prior run history is preserved and the next run must refresh generated inputs when required.",
        createdAt=created_at,
        createdBy=created_by,
    )


def _classification_from_last_run(last_run: dict[str, Any]) -> dict[str, Any]:
    interpretation = last_run.get("postCommitInterpretation") if isinstance(last_run.get("postCommitInterpretation"), dict) else {}
    classification = last_run.get("resultClassification") if isinstance(last_run.get("resultClassification"), dict) else {}
    previous: dict[str, Any] = {}
    for key in ["sideEffectStatus", "rerunRisk", "postCommit", "sideEffectMayExist", "failurePhase"]:
        if key in interpretation:
            previous[key] = interpretation[key]
        elif key in classification:
            previous[key] = classification[key]
    return previous


def _path_safe(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9._-]+", "-", str(value).strip().lower()).strip(".-_")
    return cleaned or "unknown"


def _migrate_legacy_rule(item: Any) -> tuple[dict[str, Any] | None, str | None]:
    if not isinstance(item, dict):
        return None, None
    effect = str(item.get("effect") or "").lower()
    if effect in {"allow", "allowed"}:
        target = "allowed"
    elif effect in {"forbid", "forbidden", "deny", "block"}:
        target = "forbidden"
    else:
        return None, None
    match = item.get("match") if isinstance(item.get("match"), dict) else {}
    if not match:
        return None, None
    migrated_input: dict[str, Any] = {}
    if item.get("id"):
        migrated_input["id"] = str(item["id"])
    for key, value in match.items():
        if value is not None:
            migrated_input[str(key)] = value
    migrated, rule_findings = _normalize_rule(migrated_input, "sideEffects.rules[]")
    if rule_findings:
        return None, None
    return migrated, target


def _ensure_canonical_lists(policy: dict[str, Any]) -> None:
    if "allowed" in policy and not isinstance(policy.get("allowed"), list):
        policy["allowed"] = []
    if "forbidden" in policy and not isinstance(policy.get("forbidden"), list):
        policy["forbidden"] = []


def _normalize_rule_list(value: Any, path: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not isinstance(value, list):
        return [], []
    normalized: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        rule, rule_findings = _normalize_rule(item, f"{path}[{index}]")
        findings.extend(rule_findings)
        normalized.append(rule if rule is not None else dict(item) if isinstance(item, dict) else {})
    return normalized, findings


def _normalize_rule(item: Any, path: str) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    if not isinstance(item, dict):
        return None, [
            PolicyCompatibilityFinding(
                code="side-effect-rule-invalid",
                severity="blocking",
                path=path,
                message="Side-effect rule must be an object in the Core-compatible allowed/forbidden rule shape.",
                migrationAvailable=False,
                guidedChoices=_policy_guided_choices(),
                blocksExecution=True,
            ).to_dict()
        ]
    if not item.get("id"):
        return None, [
            PolicyCompatibilityFinding(
                code="side-effect-rule-missing-id",
                severity="blocking",
                path=f"{path}.id",
                message="Side-effect rule requires an explicit id; Spec will not generate write-safety rule identities automatically.",
                migrationAvailable=False,
                guidedChoices=_policy_guided_choices(),
                blocksExecution=True,
            ).to_dict()
        ]
    if not item.get("urlContains") and not item.get("urlPattern"):
        return None, [
            PolicyCompatibilityFinding(
                code="side-effect-rule-missing-url-match",
                severity="blocking",
                path=f"{path}.urlContains",
                message="Side-effect rule requires urlContains or urlPattern so Core can match the observed request.",
                migrationAvailable=False,
                guidedChoices=_policy_guided_choices(),
                blocksExecution=True,
            ).to_dict()
        ]

    normalized: dict[str, Any] = {"id": str(item["id"])}
    normalized["kind"] = str(item.get("kind") or "network")
    normalized["methods"] = _normalize_methods(item)
    for key, value in item.items():
        if key in {"id", "kind", "method", "methods"}:
            continue
        if value is not None:
            normalized[str(key)] = value
    return normalized, []


def _normalize_methods(item: dict[str, Any]) -> list[str]:
    raw_methods = item.get("methods")
    if isinstance(raw_methods, list):
        return [str(method).upper() for method in raw_methods if str(method or "").strip()]
    method = item.get("method")
    if method is None:
        return []
    value = str(method).strip()
    return [value.upper()] if value else []


def _same_rules(left: list[dict[str, Any]], right: list[dict[str, Any]]) -> bool:
    return _normalized_rules(left) == _normalized_rules(right)


def _normalized_rules(rules: list[dict[str, Any]]) -> list[str]:
    return sorted(json.dumps(item, sort_keys=True, separators=(",", ":")) for item in rules)


def _policy_guided_choices() -> list[dict[str, str]]:
    return [
        {"id": "keep-canonical", "label": "Keep canonical policy", "description": "Use allowed/forbidden as already authored and discard legacy rules."},
        {"id": "migrate-legacy", "label": "Migrate legacy rules", "description": "Replace canonical entries with the migrated legacy rule intent."},
        {"id": "ask-owner", "label": "Ask owner", "description": "Pause for an explicit owner decision before readiness or run."},
    ]


def confirmation_support_to_dict(support: ConfirmationSignalSupport) -> dict[str, Any]:
    return {key: value for key, value in asdict(support).items() if value is not None}


def _confirmation_signal_types(core_contract: dict[str, Any] | None) -> list[str]:
    guardrails = _side_effect_guardrails(core_contract)
    values = guardrails.get("confirmationSignalTypes")
    return [str(item) for item in values] if isinstance(values, list) else []


def _explicit_runtime_confirmation_support(core_contract: dict[str, Any] | None, signal_type: str) -> bool | None:
    guardrails = _side_effect_guardrails(core_contract)
    candidates = guardrails.get("runtimeConfirmationSupport") or guardrails.get("confirmationRuntimeSupport")
    if isinstance(candidates, dict):
        raw = candidates.get(signal_type)
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, str):
            return raw.lower() == "supported"
    if isinstance(candidates, list):
        for item in candidates:
            if not isinstance(item, dict):
                continue
            if str(item.get("type") or item.get("signalType") or "") != signal_type:
                continue
            status = item.get("status")
            if isinstance(status, bool):
                return status
            if isinstance(status, str):
                return status.lower() in {"supported", "stable", "ready"}
    return None


def _runtime_unsupported_confirmation_evidence(outcomes: list[dict[str, Any] | None], signal_type: str) -> str:
    for outcome in outcomes:
        for item in _iter_dicts(outcome):
            code = str(item.get("code") or item.get("reason") or "")
            status = str(item.get("status") or "").lower()
            observed_type = str(item.get("type") or item.get("signalType") or item.get("source") or "")
            if observed_type and observed_type != signal_type:
                continue
            if code == "unsupported-confirmation-signal" or status == "unsupported":
                return f"runtime outcome reported unsupported-confirmation-signal for {signal_type}"
    return ""


def _iter_dicts(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _iter_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_dicts(child)


def _side_effect_guardrails(core_contract: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(core_contract, dict):
        return {}
    sections = core_contract.get("sections") if isinstance(core_contract.get("sections"), dict) else {}
    guardrails = sections.get("sideEffectGuardrails") if isinstance(sections.get("sideEffectGuardrails"), dict) else {}
    return guardrails if isinstance(guardrails, dict) else {}


def _matching_supersede_review(last_run: dict[str, Any], reviews: list[Any]) -> Any | None:
    run_id = str(last_run.get("runId") or "")
    if not run_id:
        return None
    for review in reviews:
        source_run_id = getattr(review, "sourceRunId", None)
        if source_run_id is None and isinstance(review, dict):
            source_run_id = review.get("sourceRunId")
        if str(source_run_id or "") == run_id:
            return review
    return None
