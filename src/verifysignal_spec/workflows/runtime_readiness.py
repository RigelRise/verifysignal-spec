from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from verifysignal_spec.workspace.repository import (
    credential_readiness_hints_for_record,
    credential_runtime_requirements,
    load_document,
    load_use_case,
)
from verifysignal_spec.workspace.validation import validate_side_effect_declaration

from .models import RuntimeReadinessCheck


ReachabilityChecker = Callable[[str], bool]


def evaluate_runtime_readiness(
    project: Path,
    alias: str,
    *,
    authoring_result: dict[str, Any] | None = None,
    reachability_checker: ReachabilityChecker | None = None,
    core_contract: dict[str, Any] | None = None,
    environment_values: dict[str, str] | None = None,
) -> RuntimeReadinessCheck:
    """Evaluate bounded runtime readiness without executing the browser flow."""

    record = load_use_case(project, alias)
    locator = _resolved_target_locator(project, record)
    findings: list[str] = []

    target_resolution = "resolved" if locator else "unresolved"
    if not locator:
        findings.append("runtime.target-unresolved")

    missing_inputs = _missing_required_parameter_inputs(project, record)
    credential_readiness = _credential_readiness(
        project,
        record,
        environment_values=environment_values,
    )
    missing_credentials = [
        item
        for item in credential_readiness
        if item.get("status") == "missing"
    ]
    prerequisite_status = "missing" if missing_inputs else "complete"
    if missing_credentials:
        prerequisite_status = "missing"
    findings.extend(f"runtime.prerequisite-missing.{name}" for name in missing_inputs)
    for item in missing_credentials:
        findings.append(f"runtime.credential-missing.{item['credentialGroup']}")
    if locator:
        findings.extend(
            f"runtime.stage-handoff-defect.{name}-empty-after-resolution"
            for name in missing_inputs
            if name.lower() in {"baseurl", "targeturl", "url"}
        )

    reachability_status = "unchecked"
    if locator:
        reachable = (reachability_checker or _syntactic_reachability)(locator)
        reachability_status = "reachable" if reachable else "unreachable"
        if not reachable:
            findings.append("runtime.target-unreachable")

    authoring_status = _authoring_status(authoring_result)
    if authoring_status in {"failed", "blocked"}:
        findings.append("runtime.authoring-readiness-blocked")

    side_effect_findings = validate_side_effect_declaration(
        record.sideEffects,
        record.rerunPolicy,
        record.runtimeOutputs,
        [item.to_dict() for item in record.runtimeInputs],
        core_contract=core_contract,
    )
    findings.extend(f"runtime.{item.get('code')}" for item in side_effect_findings if item.get("severity") == "blocking")

    status = "passed"
    if target_resolution != "resolved" or prerequisite_status != "complete" or reachability_status == "unreachable":
        status = "blocked"
    elif authoring_status in {"failed", "blocked"}:
        status = "blocked"
    elif any(item.get("severity") == "blocking" for item in side_effect_findings):
        status = "blocked"

    return RuntimeReadinessCheck(
        useCaseAlias=alias,
        targetResolutionStatus=target_resolution,
        targetReachabilityStatus=reachability_status,
        requiredPrerequisiteStatus=prerequisite_status,
        authoringReadinessStatus=authoring_status,
        fullBrowserFlowExecuted=False,
        status=status,
        findingIds=findings,
        targetLocator=locator,
        message=_message(status, findings),
        credentialReadiness=credential_readiness,
    )


def _resolved_target_locator(project: Path, record: Any) -> str | None:
    run_request = _run_request_document(project, record)
    parameters = run_request.get("parameters") if isinstance(run_request, dict) else {}
    if isinstance(parameters, dict):
        for key in ["baseUrl", "targetUrl", "url"]:
            value = parameters.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

    workflow = record.workflow if isinstance(record.workflow, dict) else {}
    for decision in workflow.get("stageHandoffDecisions", []):
        if not isinstance(decision, dict):
            continue
        key = decision.get("key") or decision.get("id") or decision.get("kind")
        status = str(decision.get("status", "active"))
        if key in {"browserTargetEnvironment", "browser-target-environment"} and status in {"active", "resolved"}:
            value = str(decision.get("valueSummary") or decision.get("locator") or "").strip()
            nested = decision.get("value") if isinstance(decision.get("value"), dict) else {}
            value = value or str(nested.get("locator") or nested.get("url") or "").strip()
            if value:
                return value
    return None


def _missing_required_parameter_inputs(project: Path, record: Any) -> list[str]:
    run_request = _run_request_document(project, record)
    parameters = run_request.get("parameters") if isinstance(run_request, dict) else {}
    parameters = parameters if isinstance(parameters, dict) else {}
    missing: list[str] = []
    for item in record.runtimeInputs:
        if not item.required or item.kind != "parameter":
            continue
        if item.source == "generated":
            continue
        value = parameters.get(item.name)
        if value is None or value == "":
            missing.append(item.name)
    return missing


def _credential_readiness(
    project: Path,
    record: Any,
    *,
    environment_values: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    hints = {
        item["credentialGroup"]: item
        for item in credential_readiness_hints_for_record(project, record)
    }
    readiness: list[dict[str, Any]] = []
    for group in credential_runtime_requirements(record):
        provided = environment_values or {}
        missing = [
            name
            for name in group["runtimeNames"]
            if not (provided.get(name) if name in provided else os.environ.get(name))
        ]
        hint = hints.get(group["group"], {})
        readiness.append(
            {
                "credentialGroup": group["group"],
                "expectedSource": group["source"],
                "requiredRuntimeNames": group["runtimeNames"],
                "missingRuntimeNames": missing,
                "status": "missing" if missing else "available",
                "preparationHint": hint.get("preparationHint", ""),
                "valuesIncluded": False,
            }
        )
    return readiness


def _run_request_document(project: Path, record: Any) -> dict[str, Any]:
    if not record.runRequest:
        return {}
    try:
        data = load_document(project / record.runRequest.path, default={})
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _syntactic_reachability(locator: str) -> bool:
    parsed = urlparse(locator)
    if parsed.scheme in {"http", "https"}:
        return bool(parsed.netloc)
    return bool(locator.strip())


def _authoring_status(authoring_result: dict[str, Any] | None) -> str:
    if not authoring_result:
        return "unchecked"
    status = authoring_result.get("status") or authoring_result.get("data", {}).get("status")
    if status == "passed":
        return "passed"
    if status == "blocked":
        return "blocked"
    if status in {"failed", "error"}:
        return "failed"
    return "failed"


def _message(status: str, findings: list[str]) -> str:
    if status == "passed":
        return "Runtime readiness passed without executing the full browser flow."
    if "runtime.target-unreachable" in findings:
        return "Target environment is not reachable; recover the environment before rewriting artifacts."
    if "runtime.target-unresolved" in findings:
        return "Browser target environment is unresolved."
    if any(item.startswith("runtime.credential-missing.") for item in findings):
        return "Credential values are missing from the current validation process."
    return "Runtime readiness is blocked."
