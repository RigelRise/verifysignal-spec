from __future__ import annotations

import json
import time
import hashlib
import subprocess
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from verifysignal_spec import __version__ as SPEC_VERSION

from . import layout
from ..process import run_text
from .path_safety import (
    ensure_no_casefold_sibling_collision,
    ensure_unredirected_project_path,
)
from .secret_safety import validate_no_secret_values
from .textio import (
    atomic_write_text_lf,
    durable_atomic_write_text_lf,
    durable_create_text_lf,
)
from .time_ordering import format_utc_ns, parse_utc_iso_ns
from .models import (
    ArtifactCapabilityPolicy,
    ArtifactCapabilityStamp,
    ArtifactReference,
    ConfirmationRequirement,
    CredentialReadinessHint,
    LastCoreAttempt,
    NamedOutput,
    ReadinessSnapshot,
    RefreshImpactResult,
    RerunPolicy,
    RunHistoryEntry,
    SideEffectLifecycleDeclaration,
    SupersedeReview,
    UseCaseRecord,
)


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def core_attempt_iso() -> str:
    """Return a local nanosecond-resolution timestamp for attempt identity."""

    return format_utc_ns(time.time_ns())


def core_attempt_iso_after(previous: str) -> str:
    """Return an attempt timestamp that is strictly later than ``previous``."""

    previous_ns = parse_utc_iso_ns(previous)
    if previous_ns is None:
        raise ValueError(f"Invalid Core attempt timestamp: {previous}")
    return format_utc_ns(max(time.time_ns(), previous_ns + 1))


def core_attempt_iso_after_record(
    record: UseCaseRecord,
    *,
    candidate: str | None = None,
) -> str:
    """Return a new attempt identity after every durable record projection."""

    candidate_text = candidate or core_attempt_iso()
    candidate_ns = parse_utc_iso_ns(candidate_text)
    if candidate_ns is None:
        raise ValueError(f"Invalid Core attempt timestamp: {candidate_text}")
    evidence: list[Any] = []
    if isinstance(record.lastRun, dict):
        evidence.extend(
            [record.lastRun.get("completedAt"), record.lastRun.get("startedAt")]
        )
    if record.lastCoreAttempt is not None:
        evidence.append(record.lastCoreAttempt.attemptedAt)
    for value in evidence:
        parsed = parse_utc_iso_ns(value)
        if parsed is not None:
            candidate_ns = max(candidate_ns, parsed + 1)
    return format_utc_ns(candidate_ns)


def load_document(path: Path, default: Any | None = None) -> Any:
    if not path.exists():
        return default
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return default
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return _load_simple_yaml(text)


def save_document(path: Path, data: Any) -> None:
    # LF regardless of host: artifact_fingerprints below hashes these files' BYTES, so a CRLF
    # translation on Windows would make the same workspace fingerprint differently there.
    atomic_write_text_lf(path, json.dumps(data, indent=2, sort_keys=False) + "\n")


def save_document_durable(path: Path, data: Any) -> None:
    """Persist a safety authority with crash-durable replacement ordering."""

    durable_atomic_write_text_lf(
        path,
        json.dumps(data, indent=2, sort_keys=False) + "\n",
    )


def create_document_durable(path: Path, data: Any) -> None:
    """Create immutable safety authority without replacing an existing file."""

    durable_create_text_lf(
        path,
        json.dumps(data, indent=2, sort_keys=False) + "\n",
    )


def _named_outputs_path(project: Path) -> Path:
    return layout.workspace_root(project) / "named-outputs.yaml"


def _load_simple_yaml(text: str) -> Any:
    """Parse a small YAML subset used by old/manual workspace files.

    JSON is the writer format because JSON is valid YAML. This reader only
    handles simple key/value and one-level list files to keep the CLI usable
    without PyYAML in minimal environments.
    """
    result: dict[str, Any] = {}
    current_key: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith("  - ") and current_key:
            result.setdefault(current_key, []).append(_parse_scalar(line[4:]))
            continue
        if ":" in line and not line.startswith(" "):
            key, value = line.split(":", 1)
            current_key = key.strip()
            value = value.strip()
            if value == "":
                result[current_key] = []
            elif value.startswith("[") and value.endswith("]"):
                items = [item.strip() for item in value[1:-1].split(",") if item.strip()]
                result[current_key] = [_parse_scalar(item) for item in items]
            else:
                result[current_key] = _parse_scalar(value)
    return result


def _parse_scalar(value: str) -> Any:
    value = value.strip().strip('"').strip("'")
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    if value.lower() in {"null", "none"}:
        return None
    try:
        return int(value)
    except ValueError:
        return value


def init_workspace(project: Path, force: bool = False, core_cmd: str | None = None, api_base_url: str | None = None) -> dict[str, Any]:
    root = layout.workspace_root(project)
    workspace_path = root / layout.WORKSPACE_FILE
    is_new_workspace = not workspace_path.exists()
    for directory in layout.workspace_dirs(project):
        directory.mkdir(parents=True, exist_ok=True)

    created = now_iso()
    workspace = load_document(workspace_path, default={}) or {}
    workspace.setdefault("workspaceVersion", "verifysignal-spec-workspace/v1")
    workspace.setdefault("createdAt", created)
    if is_new_workspace:
        workspace["coreResolutionMode"] = "managed-only"
    workspace["updatedAt"] = now_iso()
    workspace.update(
        {
            "productContextPath": f"{layout.WORKSPACE_DIR}/{layout.PRODUCT_CONTEXT_FILE}",
            "registryPath": f"{layout.WORKSPACE_DIR}/{layout.REGISTRY_FILE}",
            "useCasesDir": f"{layout.WORKSPACE_DIR}/{layout.USE_CASES_DIR}",
            "runRequestsDir": f"{layout.WORKSPACE_DIR}/{layout.RUN_REQUESTS_DIR}",
            "skillsDir": f"{layout.WORKSPACE_DIR}/{layout.SKILLS_DIR}",
            "runsDir": f"{layout.WORKSPACE_DIR}/{layout.RUNS_DIR}",
            "repairsDir": f"{layout.WORKSPACE_DIR}/{layout.REPAIRS_DIR}",
            "readinessDir": f"{layout.WORKSPACE_DIR}/{layout.READINESS_DIR}",
            "credentialHintsDir": f"{layout.WORKSPACE_DIR}/{layout.CREDENTIAL_HINTS_DIR}",
            "confirmationsDir": f"{layout.WORKSPACE_DIR}/{layout.CONFIRMATIONS_DIR}",
            "refreshImpactDir": f"{layout.WORKSPACE_DIR}/{layout.REFRESH_IMPACT_DIR}",
            "supersedeReviewsDir": f"{layout.WORKSPACE_DIR}/{layout.SUPERSEDE_REVIEWS_DIR}",
            "integrationsDir": f"{layout.WORKSPACE_DIR}/{layout.INTEGRATIONS_DIR}",
            "workflowsDir": f"{layout.WORKSPACE_DIR}/{layout.WORKFLOWS_DIR}",
        }
    )
    if core_cmd:
        workspace["coreCommand"] = core_cmd
        workspace["coreResolutionMode"] = "development-override"
    if api_base_url:
        workspace["entitlementApiBaseUrl"] = api_base_url
    save_document(workspace_path, workspace)

    product_context_path = layout.product_context_path(project)
    if force or not product_context_path.exists():
        product_context = {
            "schemaVersion": "verifysignal-spec-product-context/v1",
            "productName": project.name,
            "workspaceKind": "repository",
            "understandingMode": "repository",
            "repositorySummary": "",
            "localStartInstructions": "",
            "safeInspectionPaths": ["README.md", "src/", "app/", "tests/"],
            "sensitivePathPatterns": [
                ".env",
                ".env.*",
                "**/.env",
                "**/.env.*",
                "*secret*",
                "*credentials*",
                "*.pem",
                "*.key",
            ],
            "validationGoals": [],
            "knownRuntimeRequirements": [],
        }
        save_document(product_context_path, product_context)

    registry = load_registry(project)
    save_registry(project, registry)

    workflow_definition = layout.workflow_definition_path(project, "verifysignal-use-case")
    if force or not workflow_definition.exists():
        save_document(
            workflow_definition,
            {
                "workflowId": "verifysignal-use-case",
                "name": "VerifySignal Use Case",
                "version": "1.0.0",
                "stages": ["understand", "specify", "clarify", "plan", "tasks", "implement", "validate", "run", "repair"],
                "requiredInputs": ["goal", "alias"],
            },
        )
    return workspace


def get_core_command(project: Path) -> str | None:
    workspace = load_document(layout.workspace_root(project) / layout.WORKSPACE_FILE, default={}) or {}
    return workspace.get("coreCommand")


def get_core_resolution_mode(project: Path) -> str:
    workspace = load_document(layout.workspace_root(project) / layout.WORKSPACE_FILE, default={}) or {}
    mode = workspace.get("coreResolutionMode")
    if mode in {"legacy-auto", "managed-only", "development-override"}:
        return str(mode)
    return "legacy-auto"


def get_entitlement_api_base_url(project: Path) -> str | None:
    workspace = load_document(layout.workspace_root(project) / layout.WORKSPACE_FILE, default={}) or {}
    return workspace.get("entitlementApiBaseUrl")


def get_core_configuration(project: Path) -> dict[str, Any]:
    workspace = load_document(layout.workspace_root(project) / layout.WORKSPACE_FILE, default={}) or {}
    return {
        key: workspace.get(key)
        for key in [
            "coreCommand",
            "coreCommandSource",
            "coreConfiguredAt",
            "coreLastVerifiedAt",
            "coreVersion",
            "coreResolutionMode",
            "managedCoreVersion",
            "managedCoreUpdatedAt",
            "managedCoreCheckedAt",
        ]
        if workspace.get(key) is not None
    }


def save_core_configuration(
    project: Path,
    core_cmd: str,
    *,
    source: str | None = None,
    version: str | None = None,
    api_base_url: str | None = None,
) -> dict[str, Any]:
    root = layout.workspace_root(project)
    workspace_path = root / layout.WORKSPACE_FILE
    if not workspace_path.exists():
        workspace = init_workspace(project)
    else:
        workspace = load_document(workspace_path, default={}) or {}
    timestamp = now_iso()
    if workspace.get("coreCommand") != core_cmd or not workspace.get("coreConfiguredAt"):
        workspace["coreConfiguredAt"] = timestamp
    workspace["coreCommand"] = core_cmd
    workspace["coreResolutionMode"] = "development-override"
    if source:
        workspace["coreCommandSource"] = source
    workspace["coreLastVerifiedAt"] = timestamp
    if version:
        workspace["coreVersion"] = version
    if api_base_url:
        workspace["entitlementApiBaseUrl"] = api_base_url
    workspace["updatedAt"] = timestamp
    save_document(workspace_path, workspace)
    return workspace


def reset_core_configuration(project: Path) -> dict[str, Any]:
    root = layout.workspace_root(project)
    workspace_path = root / layout.WORKSPACE_FILE
    workspace = (
        load_document(workspace_path, default={}) or {}
        if workspace_path.exists()
        else init_workspace(project)
    )
    removed: list[str] = []
    for key in [
        "coreCommand",
        "coreCommandSource",
        "coreConfiguredAt",
        "coreLastVerifiedAt",
        "coreVersion",
    ]:
        if key in workspace:
            removed.append(key)
            workspace.pop(key, None)
    workspace["coreResolutionMode"] = "managed-only"
    workspace["updatedAt"] = now_iso()
    save_document(workspace_path, workspace)
    return {"workspace": workspace, "removedFields": removed}


def save_managed_core_configuration(
    project: Path,
    version: str,
    *,
    successful_update: bool,
) -> dict[str, Any]:
    root = layout.workspace_root(project)
    workspace_path = root / layout.WORKSPACE_FILE
    workspace = (
        load_document(workspace_path, default={}) or {}
        if workspace_path.exists()
        else init_workspace(project)
    )
    timestamp = now_iso()
    workspace["coreResolutionMode"] = "managed-only"
    workspace["managedCoreVersion"] = version
    workspace["managedCoreCheckedAt"] = timestamp
    if successful_update:
        workspace["managedCoreUpdatedAt"] = timestamp
    workspace["updatedAt"] = timestamp
    save_document(workspace_path, workspace)
    return workspace


def mark_managed_core_checked(project: Path) -> dict[str, Any]:
    root = layout.workspace_root(project)
    workspace_path = root / layout.WORKSPACE_FILE
    workspace = (
        load_document(workspace_path, default={}) or {}
        if workspace_path.exists()
        else init_workspace(project)
    )
    timestamp = now_iso()
    workspace["coreResolutionMode"] = "managed-only"
    workspace["managedCoreCheckedAt"] = timestamp
    workspace["updatedAt"] = timestamp
    save_document(workspace_path, workspace)
    return workspace


def load_registry(project: Path) -> dict[str, Any]:
    return load_document(
        layout.registry_path(project),
        default={"schemaVersion": "verifysignal-spec-registry/v1", "useCases": [], "lastUpdatedAt": now_iso()},
    )


def save_registry(project: Path, registry: dict[str, Any]) -> None:
    registry.setdefault("schemaVersion", "verifysignal-spec-registry/v1")
    registry.setdefault("useCases", [])
    registry["lastUpdatedAt"] = now_iso()
    save_document(layout.registry_path(project), registry)


def load_use_case(project: Path, alias: str) -> UseCaseRecord:
    layout.ensure_path_safe_alias(alias)
    path = _safe_use_case_path(project, alias)
    if not path.exists():
        raise FileNotFoundError(f"Use case not found: {alias}")
    if not path.is_file():
        raise ValueError("Use-case authority must be a regular file.")
    data = load_document(path)
    if not data:
        raise FileNotFoundError(f"Use case not found: {alias}")
    _validate_base_run_evidence(data, alias)
    record = UseCaseRecord.from_dict(data)
    if record.alias != alias:
        raise ValueError(
            "Use-case authority identity does not match its requested filename."
        )
    authority = _load_run_authority(project, alias)
    if authority is None:
        # Read-only legacy compatibility retains an unorderable YAML-only run,
        # while any durable history is recovered now so preflight cannot act on
        # a stale projection after an older writer crashed between its writes.
        histories = _load_run_history_documents(project, alias)
        if histories:
            record.lastRun = _recover_legacy_last_run(
                alias,
                record.lastRun,
                histories,
                require_history_for_unorderable=False,
            )
        return record
    histories = _load_run_history_documents(project, alias)
    _assert_base_projection_reconciles(record, authority, histories)
    _assert_run_history_reconciles(alias, authority, histories)
    # Explicit nulls are tombstones. They must overwrite stale generic
    # projections instead of being interpreted as absent values.
    attempt = authority["lastCoreAttempt"]
    record.lastCoreAttempt = (
        LastCoreAttempt.from_dict(attempt) if attempt is not None else None
    )
    record.lastRun = deepcopy(authority["lastRun"])
    return record


class LastCoreAttemptOwnershipError(RuntimeError):
    """Raised when an invocation no longer owns the durable attempt marker."""


_ATTEMPT_OWNERSHIP_UNCHECKED = object()


def save_last_core_attempt(
    project: Path,
    alias: str,
    attempt: LastCoreAttempt,
    *,
    expected_attempted_at: str | None | object = _ATTEMPT_OWNERSHIP_UNCHECKED,
) -> UseCaseRecord:
    """Replace the canonical redacted attempt before invoking Core."""

    observed_authority = _load_run_authority(project, alias)
    record = load_use_case(project, alias)
    _assert_run_authority_snapshot(project, alias, observed_authority)
    _assert_last_core_attempt_owner(record, expected_attempted_at)
    if observed_authority is None:
        record.lastRun = _recover_legacy_last_run(
            alias,
            record.lastRun,
            _load_run_history_documents(project, alias),
            require_history_for_unorderable=True,
        )
    current_attempted_at = (
        record.lastCoreAttempt.attemptedAt
        if record.lastCoreAttempt is not None
        else None
    )
    if attempt.attemptedAt != current_attempted_at:
        ordered_attempted_at = core_attempt_iso_after_record(
            record,
            candidate=attempt.attemptedAt,
        )
        if ordered_attempted_at != attempt.attemptedAt:
            attempt = LastCoreAttempt.from_dict(
                {
                    **attempt.to_dict(),
                    "attemptedAt": ordered_attempted_at,
                }
            )
    record.lastCoreAttempt = attempt
    _assert_run_authority_snapshot(project, alias, observed_authority)
    _save_run_authority(project, record)
    save_document_durable(_safe_use_case_path(project, alias), record.to_dict())
    return record


def clear_last_core_attempt(
    project: Path,
    alias: str,
    *,
    expected_attempted_at: str | None | object = _ATTEMPT_OWNERSHIP_UNCHECKED,
) -> UseCaseRecord:
    """Tombstone an owned attempt only after its real run is durable."""

    observed_authority = _load_run_authority(project, alias)
    record = load_use_case(project, alias)
    _assert_run_authority_snapshot(project, alias, observed_authority)
    _assert_last_core_attempt_owner(record, expected_attempted_at)
    if record.lastCoreAttempt is not None:
        record.lastCoreAttempt = None
        # The tombstone is canonical and durable before the generic use-case
        # projection. A crash or stale writer can therefore never resurrect
        # or erase safety authority.
        _assert_run_authority_snapshot(project, alias, observed_authority)
        _save_run_authority(project, record)
        save_document_durable(_safe_use_case_path(project, alias), record.to_dict())
    return record


_RUN_AUTHORITY_SCHEMA = "verifysignal-spec-run-authority/v1"
_RUN_AUTHORITY_KEYS = {
    "schemaVersion",
    "useCaseAlias",
    "lastCoreAttempt",
    "lastRun",
}
_LAST_CORE_ATTEMPT_KEYS = {
    "attemptedAt",
    "operation",
    "schema",
    "status",
    "errorCode",
    "executionState",
    "sideEffectMayExist",
}
_LAST_RUN_FIELDS = (
    "runId",
    "status",
    "startedAt",
    "completedAt",
    "coreStatus",
    "coverageStatus",
    "profile",
    "profileSettings",
    "selectedMainSkill",
    "executedSkill",
    "skillSelectionStatus",
    "gateCoverage",
    "missingRequiredGates",
    "partialCoverage",
    "runtimeContradictions",
    "repairRecommendations",
    "sideEffectPolicy",
    "sideEffects",
    "runtimeOutputs",
    "resolvedRuntimeInputs",
    "postCommitInterpretation",
    "rerunDecision",
    "sideEffectLifecycle",
    "reportPath",
    "evidenceDir",
)
_LAST_RUN_KEYS = set(_LAST_RUN_FIELDS)
_LAST_RUN_LIST_FIELDS = {
    "gateCoverage",
    "missingRequiredGates",
    "partialCoverage",
    "runtimeContradictions",
    "repairRecommendations",
    "runtimeOutputs",
    "resolvedRuntimeInputs",
}
_LAST_RUN_MAPPING_FIELDS = {
    "profileSettings",
    "sideEffectPolicy",
    "sideEffects",
    "postCommitInterpretation",
    "rerunDecision",
    "sideEffectLifecycle",
}
_LAST_RUN_TEXT_FIELDS = {
    "status",
    "coreStatus",
    "coverageStatus",
    "profile",
    "skillSelectionStatus",
    "reportPath",
    "evidenceDir",
}
_RISK_BOOLEAN_FIELDS = {
    "postCommit",
    "sideEffectMayExist",
    "cleanupRequired",
    "declared",
    "requiresConfirmationBeforeRun",
}
_RISK_TEXT_FIELDS = {
    "class",
    "sideEffectClass",
    "mode",
    "executionStatus",
    "verificationStatus",
    "sideEffectStatus",
    "failurePhase",
    "rerunRisk",
    "status",
    "decision",
    "outcomeClass",
    "policyBranch",
    "coreRisk",
    "specDecision",
}
_SAFE_SIDE_EFFECT_STATUSES = {"not-started", "none", "not-committed"}
_RESTRICTIVE_SIDE_EFFECT_STATUSES = {
    "possible",
    "inferred",
    "likely-committed",
    "committed",
    "committed-confirmed",
    "violated",
}
_CANONICAL_SIDE_EFFECT_STATUSES = _SAFE_SIDE_EFFECT_STATUSES | _RESTRICTIVE_SIDE_EFFECT_STATUSES | {
    "not-applicable",
    "not-observed",
    "unknown",
}
_CANONICAL_RERUN_RISKS = {
    "safe",
    "safe-with-new-inputs",
    "requires-confirmation",
    "blocked",
}


def _load_run_authority(project: Path, alias: str) -> dict[str, Any] | None:
    path = _safe_run_authority_path(project, alias)
    if not path.exists():
        return None
    if not path.is_file():
        raise ValueError("Canonical run authority must be a regular file.")
    data = load_document(path, default=None)
    _validate_run_authority(data, alias)
    return data


def _validate_run_authority(data: Any, alias: str) -> None:
    if not isinstance(data, dict) or set(data) != _RUN_AUTHORITY_KEYS:
        raise ValueError("Canonical run authority has an invalid document shape.")
    if data.get("schemaVersion") != _RUN_AUTHORITY_SCHEMA:
        raise ValueError("Canonical run authority has an unsupported schema.")
    if data.get("useCaseAlias") != alias:
        raise ValueError("Canonical run authority belongs to another use case.")
    attempt = data.get("lastCoreAttempt")
    if attempt is not None:
        _validate_last_core_attempt(attempt, exact_shape=True)
    last_run = data.get("lastRun")
    if last_run is not None:
        _validate_last_run(
            last_run,
            alias,
            require_comparable=True,
        )
    _validate_run_authority_cross_slot(attempt, last_run)


def _validate_base_run_evidence(data: Any, alias: str) -> None:
    """Reject malformed generic safety slots before permissive model decoding."""

    if not isinstance(data, dict):
        raise ValueError("Use-case authority must be a structured document.")
    attempt = data.get("lastCoreAttempt")
    if attempt is not None:
        _validate_last_core_attempt(attempt, exact_shape=False)
    last_run = data.get("lastRun")
    if last_run is not None:
        _validate_last_run(last_run, alias, require_comparable=False)


def _validate_last_core_attempt(
    attempt: Any,
    *,
    exact_shape: bool,
) -> None:
    if not isinstance(attempt, dict):
        raise ValueError("Canonical run authority has an invalid attempt marker.")
    keys = set(attempt)
    required = {"attemptedAt", "operation", "status", "executionState"}
    if (
        (exact_shape and keys != _LAST_CORE_ATTEMPT_KEYS)
        or not required <= keys
        or not keys <= _LAST_CORE_ATTEMPT_KEYS
    ):
        raise ValueError("Canonical run authority has an invalid attempt marker.")
    secret_findings = validate_no_secret_values(attempt, "lastCoreAttempt")
    if secret_findings:
        raise ValueError("Canonical run authority contains a secret-looking value.")
    if parse_utc_iso_ns(attempt.get("attemptedAt")) is None:
        raise ValueError("Canonical run authority has an invalid attempt timestamp.")
    if attempt.get("operation") != "run":
        raise ValueError("Canonical run authority has an invalid operation.")
    if attempt.get("executionState") not in {"not-started", "unknown"}:
        raise ValueError("Canonical run authority has an invalid execution state.")
    if not isinstance(attempt.get("status"), str) or not attempt["status"]:
        raise ValueError("Canonical run authority has an invalid attempt status.")
    side_effect_may_exist = attempt.get("sideEffectMayExist")
    if side_effect_may_exist is not None and not isinstance(
        side_effect_may_exist,
        bool,
    ):
        raise ValueError("Canonical run authority has invalid side-effect authority.")
    if (
        attempt.get("executionState") == "not-started"
        and side_effect_may_exist is not False
    ):
        raise ValueError(
            "Canonical not-started authority requires sideEffectMayExist false."
        )
    for optional_text in ("schema", "errorCode"):
        value = attempt.get(optional_text)
        if value is not None and not isinstance(value, str):
            raise ValueError(
                f"Canonical run authority has invalid {optional_text}."
            )


def _validate_last_run(
    last_run: Any,
    alias: str,
    *,
    require_comparable: bool,
) -> None:
    if not isinstance(last_run, dict):
        raise ValueError("Canonical run authority has an invalid lastRun.")
    secret_findings = validate_no_secret_values(last_run, f"{alias}.lastRun")
    if secret_findings:
        raise ValueError("Canonical run authority contains a secret-looking value.")
    if not set(last_run) <= _LAST_RUN_KEYS:
        raise ValueError("Canonical run authority has an invalid lastRun allowlist.")
    try:
        layout.ensure_path_safe_run_id(last_run.get("runId"))
    except (TypeError, ValueError) as exc:
        raise ValueError("Canonical run authority has an invalid run id.") from exc
    if not isinstance(last_run.get("status"), str) or not last_run["status"]:
        raise ValueError("Canonical run authority has an invalid lastRun status.")
    started_at = parse_utc_iso_ns(last_run.get("startedAt"))
    completed_at = parse_utc_iso_ns(last_run.get("completedAt"))
    for field, parsed in (
        ("startedAt", started_at),
        ("completedAt", completed_at),
    ):
        if last_run.get(field) is not None and parsed is None:
            raise ValueError(
                f"Canonical run authority has an invalid {field} timestamp."
            )
    if require_comparable and started_at is None and completed_at is None:
        raise ValueError(
            "Canonical run authority lastRun requires a comparable timestamp."
        )
    if (
        started_at is not None
        and completed_at is not None
        and completed_at < started_at
    ):
        raise ValueError(
            "Canonical run authority completion timestamp precedes its start."
        )
    for field in _LAST_RUN_TEXT_FIELDS:
        value = last_run.get(field)
        if value is not None and not isinstance(value, str):
            raise ValueError(
                f"Canonical run authority has an invalid lastRun {field}."
            )
    for field in _LAST_RUN_LIST_FIELDS:
        value = last_run.get(field)
        if value is not None and not isinstance(value, list):
            raise ValueError(
                f"Canonical run authority has an invalid lastRun {field}."
            )
    for field in _LAST_RUN_MAPPING_FIELDS:
        value = last_run.get(field)
        if value is not None and not isinstance(value, dict):
            raise ValueError(
                f"Canonical run authority has an invalid lastRun {field}."
            )
    for field in ("selectedMainSkill", "executedSkill"):
        value = last_run.get(field)
        if value is not None and not isinstance(value, (dict, str)):
            raise ValueError(
                f"Canonical run authority has an invalid lastRun {field}."
            )
    for field in _LAST_RUN_MAPPING_FIELDS:
        value = last_run.get(field)
        if isinstance(value, dict):
            _validate_risk_authority_fields(value, field)
    _validate_cross_mapping_risk_authority(last_run)


def _validate_risk_authority_fields(value: dict[str, Any], field: str) -> None:
    """Reject values whose coercion could weaken persisted rerun authority."""

    for key in _RISK_BOOLEAN_FIELDS:
        item = value.get(key)
        if item is not None and not isinstance(item, bool):
            raise ValueError(
                f"Canonical run authority has invalid boolean risk field {field}.{key}."
            )
    for key in _RISK_TEXT_FIELDS:
        item = value.get(key)
        if item is not None and (
            not isinstance(item, str)
            or not item.strip()
            or item != item.strip()
        ):
            raise ValueError(
                f"Canonical run authority has invalid text risk field {field}.{key}."
            )
        allowed_values = (
            _CANONICAL_SIDE_EFFECT_STATUSES
            if key == "sideEffectStatus" or (field == "sideEffects" and key == "status")
            else _CANONICAL_RERUN_RISKS
            if key == "rerunRisk"
            else None
        )
        if item is not None and allowed_values is not None and item not in allowed_values:
            raise ValueError(
                f"Canonical run authority has invalid risk token {field}.{key}."
            )
    commit_step = value.get("commitStep")
    if commit_step is not None:
        if not isinstance(commit_step, dict):
            raise ValueError(
                f"Canonical run authority has invalid risk field {field}.commitStep."
            )
        reached = commit_step.get("reached")
        if reached is not None and not isinstance(reached, bool):
            raise ValueError(
                f"Canonical run authority has invalid boolean risk field {field}.commitStep.reached."
            )
    else:
        reached = None

    post_commit = value.get("postCommit")
    side_effect_may_exist = value.get("sideEffectMayExist")
    side_effect_status = str(value.get("sideEffectStatus") or "").strip().lower()
    raw_side_effect_status = str(value.get("status") or "").strip().lower()
    rerun_risk = str(value.get("rerunRisk") or "").strip().lower()
    explicitly_safe = (
        post_commit is False and side_effect_may_exist is False
    ) or (
        side_effect_may_exist is False
        and side_effect_status in _SAFE_SIDE_EFFECT_STATUSES
    )
    restrictive_evidence = (
        reached is True
        or side_effect_status in _RESTRICTIVE_SIDE_EFFECT_STATUSES
        or raw_side_effect_status in _RESTRICTIVE_SIDE_EFFECT_STATUSES
    )
    explicitly_risky = post_commit is True or side_effect_may_exist is True
    claims_safe = (
        side_effect_status in _SAFE_SIDE_EFFECT_STATUSES
        or rerun_risk == "safe"
    )
    if (
        (explicitly_safe and restrictive_evidence)
        or (explicitly_risky and claims_safe)
        or (post_commit is True and side_effect_may_exist is False)
    ):
        raise ValueError(
            f"Canonical run authority has contradictory risk evidence in {field}."
        )


def _validate_cross_mapping_risk_authority(last_run: dict[str, Any]) -> None:
    """Reject a safe claim contradicted by another persisted risk mapping."""

    mappings = [
        value
        for field in _LAST_RUN_MAPPING_FIELDS
        if isinstance((value := last_run.get(field)), dict)
    ]
    has_explicit_safe = any(_mapping_claims_no_commit(value) for value in mappings)
    has_restrictive_evidence = any(
        _mapping_has_restrictive_evidence(value) for value in mappings
    )
    if has_explicit_safe and has_restrictive_evidence:
        raise ValueError(
            "Canonical run authority has contradictory risk evidence across lastRun mappings."
        )


def _mapping_claims_no_commit(value: dict[str, Any]) -> bool:
    post_commit = value.get("postCommit")
    side_effect_may_exist = value.get("sideEffectMayExist")
    status = str(value.get("sideEffectStatus") or "").strip().lower()
    return (
        post_commit is False and side_effect_may_exist is False
    ) or (
        side_effect_may_exist is False
        and status in _SAFE_SIDE_EFFECT_STATUSES
    )


def _mapping_has_restrictive_evidence(value: dict[str, Any]) -> bool:
    commit_step = value.get("commitStep")
    reached = (
        commit_step.get("reached")
        if isinstance(commit_step, dict)
        else None
    )
    statuses = {
        str(value.get("sideEffectStatus") or "").strip().lower(),
        str(value.get("status") or "").strip().lower(),
    }
    return (
        reached is True
        or value.get("postCommit") is True
        or value.get("sideEffectMayExist") is True
        or bool(statuses & _RESTRICTIVE_SIDE_EFFECT_STATUSES)
    )


def _validate_run_authority_cross_slot(
    attempt: Any,
    last_run: Any,
) -> None:
    if not isinstance(attempt, dict) or not isinstance(last_run, dict):
        return
    attempt_stamp = _attempt_stamp(attempt)
    started_at = parse_utc_iso_ns(last_run.get("startedAt"))
    run_stamp = _last_run_stamp(last_run)
    if attempt_stamp is None or run_stamp is None:
        return
    # record_run deliberately retains its marker until the same-start real run
    # is durable. Any other active attempt must be strictly newer than the
    # completed real-run evidence.
    if attempt_stamp == started_at or attempt_stamp > run_stamp:
        return
    raise ValueError(
        "Canonical run and attempt authority have an invalid temporal relationship."
    )


def _validate_run_history_document(
    data: Any,
    alias: str,
    expected_run_id: str,
    *,
    strict_completion: bool = False,
) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("RunHistory authority must be a structured document.")
    secret_findings = validate_no_secret_values(data, f"{alias}.RunHistory")
    if secret_findings:
        first = secret_findings[0]
        raise ValueError(
            "RunHistory authority contains a secret-looking value at "
            f"{first.get('path', '<unknown>')}."
        )
    try:
        run_id = layout.ensure_path_safe_run_id(data.get("runId"))
    except (TypeError, ValueError) as exc:
        raise ValueError("RunHistory authority has an invalid run id.") from exc
    if run_id != expected_run_id:
        raise ValueError("RunHistory identity does not match its filename.")
    if data.get("useCaseAlias") != alias:
        raise ValueError("RunHistory authority belongs to another use case.")
    started_at = parse_utc_iso_ns(data.get("startedAt"))
    if started_at is None:
        raise ValueError("RunHistory authority has an invalid startedAt timestamp.")
    completed_value = data.get("completedAt")
    completed_at = parse_utc_iso_ns(completed_value)
    if completed_value is not None and completed_at is None:
        raise ValueError("RunHistory authority has an invalid completedAt timestamp.")
    if strict_completion and completed_at is None:
        raise ValueError("A newly recorded RunHistory requires completedAt.")
    if completed_at is not None and (
        completed_at < started_at
        or (strict_completion and completed_at == started_at)
    ):
        raise ValueError("RunHistory completion must follow its start timestamp.")
    projection = _project_run_history(data)
    _validate_last_run(projection, alias, require_comparable=True)
    return projection


def _project_run_history(data: dict[str, Any]) -> dict[str, Any]:
    return {
        field: deepcopy(data.get(field))
        for field in _LAST_RUN_FIELDS
    }


def _load_run_history_documents(
    project: Path,
    alias: str,
) -> list[dict[str, Any]]:
    directory = _safe_run_history_dir(project, alias)
    if not directory.exists():
        return []
    if not directory.is_dir():
        raise ValueError("RunHistory authority path must be a directory.")
    try:
        siblings = sorted(
            directory.iterdir(),
            key=lambda candidate: (candidate.name.casefold(), candidate.name),
        )
    except OSError as exc:
        raise ValueError(
            "RunHistory authority sibling names cannot be verified safely."
        ) from exc
    histories: list[dict[str, Any]] = []
    for sibling in siblings:
        if sibling.suffix.casefold() != ".yaml":
            continue
        # The suffix spelling is canonical too. A `.YAML` sibling must not be
        # hidden on POSIX and then silently selected as `.yaml` on Windows.
        path = ensure_no_casefold_sibling_collision(
            sibling.with_suffix(".yaml"),
            authority="RunHistory authority",
        )
        ensure_unredirected_project_path(
            project,
            path,
            authority="RunHistory authority",
        )
        if not path.is_file():
            raise ValueError("RunHistory authority must be a regular file.")
        data = load_document(path, default=None)
        histories.append(
            _validate_run_history_document(data, alias, path.stem)
        )
    return histories


def _recover_legacy_last_run(
    alias: str,
    base_run: Any,
    histories: list[dict[str, Any]],
    *,
    require_history_for_unorderable: bool,
) -> dict[str, Any] | None:
    """Recover main-era timestamp-less projections before first sidecar write."""

    if base_run is not None:
        _validate_last_run(base_run, alias, require_comparable=False)
    if not histories:
        if (
            require_history_for_unorderable
            and base_run is not None
            and _last_run_stamp(base_run) is None
        ):
            raise ValueError(
                "Legacy lastRun requires matching comparable RunHistory authority."
            )
        return deepcopy(base_run)
    newest_stamp = max(_last_run_stamp(history) for history in histories)
    newest = [
        history
        for history in histories
        if _last_run_stamp(history) == newest_stamp
    ]
    if len(newest) != 1:
        raise ValueError("RunHistory authority is ambiguous at the newest timestamp.")
    if base_run is not None:
        matching = [
            history
            for history in histories
            if history.get("runId") == base_run.get("runId")
        ]
        base_stamp = _last_run_stamp(base_run)
        if matching and (
            len(matching) != 1
            or not _projection_is_compatible_subset(base_run, matching[0])
        ):
            raise ValueError(
                "Legacy lastRun conflicts with its RunHistory authority."
            )
        if not matching and (
            base_stamp is None
            or newest_stamp is None
            or newest_stamp <= base_stamp
        ):
            raise ValueError(
                "Legacy lastRun conflicts with its RunHistory authority."
            )
    return deepcopy(newest[0])


def _assert_base_projection_reconciles(
    record: UseCaseRecord,
    authority: dict[str, Any],
    histories: list[dict[str, Any]],
) -> None:
    base_run = record.lastRun if isinstance(record.lastRun, dict) else None
    canonical_run = (
        authority.get("lastRun")
        if isinstance(authority.get("lastRun"), dict)
        else None
    )
    base_run_stamp = _last_run_stamp(base_run)
    canonical_run_stamp = _last_run_stamp(canonical_run)
    if base_run is not None:
        if canonical_run is None:
            canonical_attempt_stamp = _attempt_stamp(authority.get("lastCoreAttempt"))
            if (
                base_run_stamp is None
                or canonical_attempt_stamp is None
                or base_run_stamp >= canonical_attempt_stamp
            ):
                raise ValueError(
                    "Base run projection is newer than or conflicts with canonical authority; downgrade recovery is required."
                )
        elif _projection_is_compatible_subset(base_run, canonical_run):
            pass
        elif base_run_stamp is None or canonical_run_stamp is None:
            raise ValueError(
                "Base and canonical run projections cannot be ordered safely."
            )
        elif base_run_stamp > canonical_run_stamp:
            raise ValueError(
                "Base run projection is newer than canonical authority; downgrade recovery is required."
            )
        elif (
            base_run_stamp == canonical_run_stamp
            and _without_none(base_run) != _without_none(canonical_run)
        ):
            raise ValueError(
                "Base and canonical run projections conflict at the same timestamp."
            )

    base_attempt = record.lastCoreAttempt
    canonical_attempt = authority.get("lastCoreAttempt")
    if base_attempt is None:
        return
    base_attempt_stamp = _attempt_stamp(base_attempt)
    canonical_attempt_stamp = _attempt_stamp(canonical_attempt)
    if canonical_attempt is not None:
        if base_attempt_stamp is None or canonical_attempt_stamp is None:
            raise ValueError(
                "Base attempt projection cannot be ordered safely."
            )
        if base_attempt_stamp > canonical_attempt_stamp:
            raise ValueError(
                "Base attempt projection is newer than canonical authority; downgrade recovery is required."
            )
        # Equal attemptedAt is the exact attempt identity. Canonical refinement
        # legitimately precedes its generic projection and therefore wins even
        # if a crash left the same-identity base marker stale.
        return

    # A canonical tombstone intentionally outranks the stale base marker when
    # the completed canonical run proves that marker was already resolved.
    if (
        base_attempt_stamp is None
        or canonical_run_stamp is None
        or base_attempt_stamp >= canonical_run_stamp
    ):
        raise ValueError(
            "Base attempt projection conflicts with the canonical tombstone."
        )


def _assert_run_history_reconciles(
    alias: str,
    authority: dict[str, Any],
    histories: list[dict[str, Any]],
) -> None:
    canonical_run = (
        authority.get("lastRun")
        if isinstance(authority.get("lastRun"), dict)
        else None
    )
    canonical_run_stamp = _last_run_stamp(canonical_run)
    canonical_attempt_stamp = _attempt_stamp(authority.get("lastCoreAttempt"))
    if canonical_run is None:
        for history in histories:
            history_stamp = _last_run_stamp(history)
            if (
                history_stamp is None
                or canonical_attempt_stamp is None
                or history_stamp >= canonical_attempt_stamp
            ):
                raise ValueError(
                    "RunHistory conflicts with canonical lastRun tombstone."
                )
        return

    matching = [
        history
        for history in histories
        if history.get("runId") == canonical_run.get("runId")
    ]
    if len(matching) > 1:
        raise ValueError("RunHistory identity is ambiguous.")
    if matching:
        if _without_none(matching[0]) != _without_none(canonical_run):
            raise ValueError(
                "RunHistory diverges from canonical run authority."
            )
        if canonical_run_stamp is None:
            canonical_run_stamp = _last_run_stamp(matching[0])
    for history in histories:
        if matching and history is matching[0]:
            continue
        history_stamp = _last_run_stamp(history)
        if (
            history_stamp is None
            or canonical_run_stamp is None
            or history_stamp >= canonical_run_stamp
        ):
            raise ValueError(
                "RunHistory is newer than or conflicts with canonical run authority; downgrade recovery is required."
            )


def _last_run_stamp(last_run: dict[str, Any] | None) -> int | None:
    if not isinstance(last_run, dict):
        return None
    completed_at = parse_utc_iso_ns(last_run.get("completedAt"))
    if completed_at is not None:
        return completed_at
    return parse_utc_iso_ns(last_run.get("startedAt"))


def _attempt_stamp(attempt: Any) -> int | None:
    if isinstance(attempt, LastCoreAttempt):
        return parse_utc_iso_ns(attempt.attemptedAt)
    if isinstance(attempt, dict):
        return parse_utc_iso_ns(attempt.get("attemptedAt"))
    return None


def _without_none(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _without_none(item)
            for key, item in value.items()
            if item is not None
        }
    if isinstance(value, list):
        return [_without_none(item) for item in value]
    return value


def _projection_is_compatible_subset(
    projection: dict[str, Any],
    authority: dict[str, Any],
) -> bool:
    return all(
        value is None
        or (
            key in authority
            and _without_none(value) == _without_none(authority.get(key))
        )
        for key, value in projection.items()
    )


def _run_authority_document(record: UseCaseRecord) -> dict[str, Any]:
    return {
        "schemaVersion": _RUN_AUTHORITY_SCHEMA,
        "useCaseAlias": record.alias,
        "lastCoreAttempt": (
            record.lastCoreAttempt.to_dict()
            if record.lastCoreAttempt is not None
            else None
        ),
        "lastRun": deepcopy(record.lastRun),
    }


def _save_run_authority(project: Path, record: UseCaseRecord) -> None:
    document = _run_authority_document(record)
    _validate_run_authority(document, record.alias)
    save_document_durable(
        _safe_run_authority_path(project, record.alias),
        document,
    )


def _assert_last_core_attempt_owner(
    record: UseCaseRecord,
    expected_attempted_at: str | None | object,
) -> None:
    if expected_attempted_at is _ATTEMPT_OWNERSHIP_UNCHECKED:
        return
    current = (
        record.lastCoreAttempt.attemptedAt
        if record.lastCoreAttempt is not None
        else None
    )
    if current != expected_attempted_at:
        raise LastCoreAttemptOwnershipError(
            "LastCoreAttempt ownership changed before persistence completed."
        )


def _assert_run_authority_snapshot(
    project: Path,
    alias: str,
    expected: dict[str, Any] | None,
) -> None:
    if _load_run_authority(project, alias) != expected:
        raise LastCoreAttemptOwnershipError(
            "Canonical run authority changed before persistence completed."
        )


def save_use_case(project: Path, record: UseCaseRecord) -> None:
    layout.ensure_path_safe_alias(record.alias)
    save_document(_safe_use_case_path(project, record.alias), record.to_dict())
    upsert_registry_entry(project, record)


def _safe_use_case_path(project: Path, alias: str) -> Path:
    return ensure_unredirected_project_path(
        project,
        layout.use_case_path(project, alias),
        authority="Use-case authority",
    )


def _safe_run_authority_path(project: Path, alias: str) -> Path:
    return ensure_unredirected_project_path(
        project,
        layout.run_authority_path(project, alias),
        authority="Canonical run authority",
    )


def _safe_run_history_dir(project: Path, alias: str) -> Path:
    return ensure_unredirected_project_path(
        project,
        layout.workspace_root(project)
        / layout.RUNS_DIR
        / layout.ensure_path_safe_alias(alias),
        authority="RunHistory authority",
    )


def _safe_run_history_path(project: Path, alias: str, run_id: str) -> Path:
    path = ensure_unredirected_project_path(
        project,
        layout.run_history_path(project, alias, run_id),
        authority="RunHistory authority",
    )
    return ensure_no_casefold_sibling_collision(
        path,
        authority="RunHistory authority",
    )


def update_use_case_workflow_reference(project: Path, alias: str, workflow: dict[str, Any]) -> UseCaseRecord:
    record = load_use_case(project, alias)
    record.workflow = workflow
    save_use_case(project, record)
    return record


def upsert_registry_entry(project: Path, record: UseCaseRecord) -> None:
    registry = load_registry(project)
    entry = {
        "alias": record.alias,
        "title": record.title,
        "targetSurface": record.targetSurface,
        "recordPath": f"{layout.WORKSPACE_DIR}/{layout.USE_CASES_DIR}/{record.alias}.yaml",
        "runnableStatus": record.status,
        "requiredRuntimeInputs": [item.name for item in record.runtimeInputs if item.kind != "credential"],
        "credentialGroups": [
            item.get("name", item) if isinstance(item, dict) else item for item in record.credentialGroups
        ],
        "lastResult": record.lastRun,
    }
    if record.workflow:
        entry["workflow"] = {
            "currentStage": record.workflow.get("currentStage"),
            "workflowStatus": record.workflow.get("workflowStatus"),
            "lastWorkflowRunId": record.workflow.get("lastWorkflowRunId"),
        }
    entries = [item for item in registry.get("useCases", []) if item.get("alias") != record.alias]
    entries.append(entry)
    entries.sort(key=lambda item: item.get("alias", ""))
    registry["useCases"] = entries
    save_registry(project, registry)


def list_use_cases(project: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    registry = load_registry(project)
    rows: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    for item in registry.get("useCases", []):
        row = dict(item)
        try:
            record_path = layout.project_relative_path(project, row["recordPath"])
            if not record_path.exists():
                raise FileNotFoundError(row["recordPath"])
            record = load_use_case(project, str(row["alias"]))
            current = readiness_current_state(project, record)
            row.update(
                {
                    "alias": record.alias,
                    "title": record.title,
                    "status": record.status,
                    "targetSurface": record.targetSurface,
                    "requiredRuntimeInputs": [entry.name for entry in record.runtimeInputs if entry.kind != "credential"],
                    "credentialGroups": [
                        cg.get("name", cg) if isinstance(cg, dict) else cg for cg in record.credentialGroups
                    ],
                    "lastResult": record.lastRun,
                    "lastRun": _last_run_summary(record.lastRun),
                    "current": current,
                    "requirements": list_requirements(record),
                    "risk": list_risk(project, record),
                }
            )
        except Exception as exc:  # keep list tolerant
            row["status"] = "invalid"
            warnings.append({"alias": item.get("alias"), "message": str(exc)})
        rows.append(row)
    return rows, warnings


def _last_run_summary(last_run: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(last_run, dict):
        return {"status": "never-run", "runId": None}
    return {
        "status": last_run.get("status", "unknown"),
        "runId": last_run.get("runId"),
        "coreStatus": last_run.get("coreStatus"),
        "coverageStatus": last_run.get("coverageStatus"),
        "profile": last_run.get("profile"),
    }


def create_default_use_case(project: Path, alias: str, description: str) -> UseCaseRecord:
    layout.ensure_path_safe_alias(alias)
    title = alias.replace("-", " ").replace("_", " ").title()
    run_request_rel = f"{layout.WORKSPACE_DIR}/{layout.RUN_REQUESTS_DIR}/{alias}.yaml"
    skill_rel = f"{layout.WORKSPACE_DIR}/{layout.SKILLS_DIR}/{alias}.browser.md"
    return UseCaseRecord(
        alias=alias,
        title=title,
        description=description,
        runRequest=ArtifactReference(path=run_request_rel, kind="run-request", generated=True, id=f"request.{alias}", version="1.0.0"),
        mainSkill=ArtifactReference(path=skill_rel, kind="skill", generated=True, id=f"skill.{alias}", version="1.0.0"),
        skills=[ArtifactReference(path=skill_rel, kind="skill", generated=True, id=f"skill.{alias}", version="1.0.0")],
        runtimeInputs=[],
        credentialGroups=[],
    )


def resolve_artifacts(project: Path, alias: str, *, core_contract: dict[str, Any] | None = None) -> tuple[UseCaseRecord, Path, Path, list[Path]]:
    record = load_use_case(project, alias)
    if not record.runRequest:
        raise ValueError(f"Use case {alias} does not reference a run request.")
    if not record.mainSkill:
        raise ValueError(f"Use case {alias} does not reference a main skill.")
    run_request = layout.project_relative_path(project, record.runRequest.path)
    main_skill = layout.project_relative_path(project, record.mainSkill.path)
    from verifysignal_spec.workflows.skill_execution_boundary import executable_skill_refs

    executable_refs = executable_skill_refs(record, core_contract=core_contract)
    skills = [layout.project_relative_path(project, skill.path) for skill in executable_refs]
    authored = [layout.project_relative_path(project, skill.path) for skill in [*record.skills, *record.sourceOnlySkills]]
    for path in [run_request, main_skill, *authored]:
        if not path.exists():
            raise FileNotFoundError(path)
    return record, run_request, main_skill, skills


def update_validation(project: Path, alias: str, result: dict[str, Any]) -> UseCaseRecord:
    record = load_use_case(project, alias)
    status = result.get("status") or result.get("data", {}).get("status")
    record.validation = result
    record.status = "ready" if status == "passed" else "blocked"
    _canonicalize_unambiguous_rerun_policy(record)
    save_use_case(project, record)
    return record


def record_run(project: Path, entry: RunHistoryEntry) -> None:
    use_case_path = _safe_use_case_path(project, entry.useCaseAlias)
    history_path = _safe_run_history_path(
        project,
        entry.useCaseAlias,
        entry.runId,
    )
    history_document = entry.to_dict()
    try:
        history_path.lstat()
    except FileNotFoundError:
        pass
    except OSError as exc:
        raise ValueError("RunHistory identity cannot be inspected safely.") from exc
    else:
        raise ValueError("RunHistory identity already exists and cannot be reused.")
    projection = _validate_run_history_document(
        history_document,
        entry.useCaseAlias,
        entry.runId,
        strict_completion=True,
    )
    observed_authority = _load_run_authority(project, entry.useCaseAlias)
    record = load_use_case(project, entry.useCaseAlias)
    _assert_run_authority_snapshot(
        project,
        entry.useCaseAlias,
        observed_authority,
    )
    prior_run = record.lastRun
    if observed_authority is None:
        prior_run = _recover_legacy_last_run(
            entry.useCaseAlias,
            record.lastRun,
            _load_run_history_documents(project, entry.useCaseAlias),
            require_history_for_unorderable=True,
        )
    prior_stamp = _last_run_stamp(prior_run)
    new_stamp = _last_run_stamp(projection)
    if prior_stamp is not None and (new_stamp is None or new_stamp <= prior_stamp):
        raise ValueError(
            "New RunHistory does not follow the prior real-run authority."
        )
    record.lastRun = projection
    record.status = "ready" if entry.status == "passed" else "failed"
    _canonicalize_unambiguous_rerun_policy(record)
    authority_document = _run_authority_document(record)
    # Validate every byte-bearing document before the first durable write. An
    # invalid/secret result must not leave a rejected RunHistory artifact.
    _validate_run_authority(authority_document, record.alias)
    _assert_run_authority_snapshot(project, record.alias, observed_authority)
    try:
        create_document_durable(history_path, history_document)
    except FileExistsError as exc:
        raise ValueError(
            "RunHistory identity already exists and cannot be reused."
        ) from exc
    # RunHistory is durable first; the canonical authority then records both
    # the completed run and the still-owned attempt. Clearing the attempt is a
    # separate, later tombstone write by the invocation that owns it.
    _assert_run_authority_snapshot(project, record.alias, observed_authority)
    save_document_durable(
        _safe_run_authority_path(project, record.alias),
        authority_document,
    )
    save_document_durable(
        use_case_path,
        record.to_dict(),
    )
    upsert_registry_entry(project, record)
    _publish_outputs_from_run(project, record, entry)


def _canonicalize_unambiguous_rerun_policy(record: UseCaseRecord) -> None:
    if not isinstance(record.rerunPolicy, dict):
        return
    policy = RerunPolicy.from_dict(record.rerunPolicy)
    if policy.legacyFindings:
        return
    canonical = policy.to_dict()
    if canonical:
        record.rerunPolicy = canonical


def committed_binding_values(
    project: Path,
    *,
    use_case_alias: str,
    target_scope: str | None,
    binding_name: str,
) -> set[str]:
    values: set[str] = set()
    for run in _iter_run_binding_sources(project, use_case_alias):
        if not _run_has_committed_binding(run):
            continue
        for binding in run.get("resolvedRuntimeInputs", []):
            if not isinstance(binding, dict):
                continue
            if str(binding.get("name") or "") != binding_name:
                continue
            if target_scope and binding.get("targetScope") and str(binding.get("targetScope")) != str(target_scope):
                continue
            value = binding.get("value")
            if value is not None:
                values.add(str(value))
    return values


def refresh_collision_findings(
    project: Path,
    *,
    use_case_alias: str,
    target_scope: str | None,
    bindings: dict[str, str],
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    try:
        record = load_use_case(project, use_case_alias)
        runtime_inputs = {item.name: item for item in record.runtimeInputs}
    except Exception:
        runtime_inputs = {}
    for name, value in bindings.items():
        committed = committed_binding_values(
            project,
            use_case_alias=use_case_alias,
            target_scope=target_scope,
            binding_name=name,
        )
        if value in committed:
            from verifysignal_spec.workspace.validation import refresh_collision_finding

            findings.append(refresh_collision_finding(input_name=name, runtime_input=runtime_inputs.get(name)))
    return findings


def publish_named_outputs(project: Path, outputs: list[dict[str, Any] | NamedOutput]) -> list[dict[str, Any]]:
    existing = load_document(_named_outputs_path(project), default={"schemaVersion": "verifysignal-spec-named-outputs/v1", "outputs": []}) or {}
    rows = [item for item in existing.get("outputs", []) if isinstance(item, dict)]
    for output in outputs:
        model = output if isinstance(output, NamedOutput) else NamedOutput.from_dict(output)
        rows.append(model.to_dict())
    existing["schemaVersion"] = "verifysignal-spec-named-outputs/v1"
    existing["outputs"] = rows
    save_document(_named_outputs_path(project), existing)
    return rows


def resolve_named_output(
    project: Path,
    name: str,
    *,
    use_case_alias: str | None = None,
    target_scope: str | None = None,
) -> dict[str, Any]:
    document = load_document(_named_outputs_path(project), default={"outputs": []}) or {}
    matches: list[dict[str, Any]] = []
    for item in document.get("outputs", []):
        if not isinstance(item, dict) or item.get("name") != name:
            continue
        if use_case_alias and item.get("useCaseAlias") != use_case_alias:
            continue
        if target_scope and item.get("targetScope") != target_scope:
            continue
        matches.append(item)
    if not matches:
        raise ValueError(f"Named output not found: {name}")
    if len(matches) > 1:
        raise ValueError(f"Named output reference is ambiguous: {name}")
    return matches[0]


def _iter_run_binding_sources(project: Path, use_case_alias: str) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    try:
        record = load_use_case(project, use_case_alias)
        if isinstance(record.lastRun, dict):
            sources.append(record.lastRun)
    except Exception:
        pass
    run_dir = layout.workspace_root(project) / layout.RUNS_DIR / use_case_alias
    if run_dir.exists():
        for path in run_dir.glob("*.yaml"):
            data = load_document(path, default={})
            if isinstance(data, dict):
                sources.append(data)
    return sources


def _run_has_committed_binding(run: dict[str, Any]) -> bool:
    for binding in run.get("resolvedRuntimeInputs", []):
        if isinstance(binding, dict) and (binding.get("status") == "committed" or binding.get("committed") is True):
            return True
    interpretation = run.get("postCommitInterpretation") if isinstance(run.get("postCommitInterpretation"), dict) else {}
    return bool(interpretation.get("postCommit") or interpretation.get("sideEffectMayExist"))


def _publish_outputs_from_run(project: Path, record: UseCaseRecord, entry: RunHistoryEntry) -> None:
    published: list[dict[str, Any]] = []
    declarations = [item for item in record.runtimeOutputs if isinstance(item, dict) and item.get("publishAsNamedOutput")]
    if not declarations:
        return
    if not _run_has_committed_binding(entry.to_dict()):
        return
    outputs_by_name = {str(item.get("name")): item for item in entry.runtimeOutputs if isinstance(item, dict)}
    target_scope = _target_scope_from_record(record)
    for declaration in declarations:
        name = str(declaration.get("name") or "")
        output = outputs_by_name.get(name)
        value = output.get("value") if isinstance(output, dict) else None
        if not name or value is None:
            continue
        published.append(
            NamedOutput(
                name=name,
                value=str(value),
                sourceBinding=str(declaration.get("source") or output.get("source") or ""),
                publishedByRunId=entry.runId,
                useCaseAlias=entry.useCaseAlias,
                targetScope=target_scope,
                resourceType=declaration.get("resourceType"),
            ).to_dict()
        )
    if published:
        publish_named_outputs(project, published)


def _target_scope_from_record(record: UseCaseRecord) -> str | None:
    identity = record.resourceIdentity if isinstance(record.resourceIdentity, dict) else {}
    if identity.get("targetScope"):
        return str(identity.get("targetScope"))
    for item in record.runtimeInputs:
        if item.name == "baseUrl" and item.value:
            return str(item.value)
    return None


def detect_conflict(path: Path, expected_sha256: str | None, hash_func) -> bool:
    if not expected_sha256 or not path.exists():
        return False
    return hash_func(path.read_bytes()) != expected_sha256


def artifact_fingerprints(project: Path, record: UseCaseRecord) -> dict[str, str]:
    fingerprints: dict[str, str] = {}
    refs: list[ArtifactReference] = []
    if record.runRequest:
        refs.append(record.runRequest)
    if record.mainSkill:
        refs.append(record.mainSkill)
    refs.extend(record.skills)
    refs.extend(record.sourceOnlySkills)
    for ref in refs:
        try:
            path = layout.project_relative_path(project, ref.path)
        except ValueError:
            continue
        if path.exists() and path.is_file():
            fingerprints[ref.path] = hashlib.sha256(path.read_bytes()).hexdigest()
    record_path = layout.use_case_path(project, record.alias)
    if record_path.exists():
        # Hash a normalized projection (Bug 3): drop volatile run/validate state so a passing
        # `run` (which mutates lastRun/status) does not invalidate the readiness snapshot.
        # Genuine authoring edits (runRequest/skills/runtimeInputs/sideEffects/...) still change
        # this projection and so still trigger an artifact-changed staleness reason.
        projection = record.to_dict()
        for volatile in (
            "status",
            "lastRun",
            "lastCoreAttempt",
            "validation",
            "repair",
            "workflow",
        ):
            projection.pop(volatile, None)
        normalized = json.dumps(projection, sort_keys=True, default=str).encode("utf-8")
        fingerprints[layout.to_project_relative(project, record_path)] = hashlib.sha256(normalized).hexdigest()
    return fingerprints


def current_project_revision(project: Path) -> str | None:
    result = run_text(
        ["git", "-C", str(project), "rev-parse", "HEAD"],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value or None


def save_readiness_snapshot(project: Path, snapshot: ReadinessSnapshot) -> None:
    save_document(layout.readiness_snapshot_path(project, snapshot.alias), snapshot.to_dict())


def load_readiness_snapshot(project: Path, alias: str) -> ReadinessSnapshot | None:
    data = load_document(layout.readiness_snapshot_path(project, alias), default=None)
    return ReadinessSnapshot.from_dict(data) if isinstance(data, dict) else None


def save_credential_readiness_hint(project: Path, hint: CredentialReadinessHint) -> None:
    save_document(layout.credential_hint_path(project, hint.credentialGroup.lower()), hint.to_dict())


def load_credential_readiness_hint(project: Path, group: str) -> CredentialReadinessHint | None:
    data = load_document(layout.credential_hint_path(project, group.lower()), default=None)
    return CredentialReadinessHint.from_dict(data) if isinstance(data, dict) else None


def credential_readiness_hints_for_record(project: Path, record: UseCaseRecord) -> list[dict[str, Any]]:
    hints: list[dict[str, Any]] = []
    for group in credential_runtime_requirements(record):
        hint = load_credential_readiness_hint(project, group["group"])
        hints.append(
            {
                "credentialGroup": group["group"],
                "expectedSource": group["source"],
                "requiredRuntimeNames": group["runtimeNames"],
                "preparationHint": hint.preparationHint if hint else "",
                "valuesIncluded": False,
            }
        )
    return hints


def save_confirmation_requirement(project: Path, requirement: ConfirmationRequirement) -> None:
    save_document(layout.confirmation_requirement_path(project, requirement.alias), requirement.to_dict())


def load_confirmation_requirement(project: Path, alias: str) -> ConfirmationRequirement | None:
    data = load_document(layout.confirmation_requirement_path(project, alias), default=None)
    return ConfirmationRequirement.from_dict(data) if isinstance(data, dict) else None


def reconcile_active_confirmation(
    project: Path,
    alias: str,
    requirement: ConfirmationRequirement | dict[str, Any] | None,
) -> ConfirmationRequirement | None:
    """Make the single active confirmation file match the current decision.

    Supersede reviews live under a separate append-only directory and are never
    inspected, modified, or removed here.
    """

    path = layout.confirmation_requirement_path(project, alias)
    if requirement is None:
        if path.exists() and path.is_file() and not path.is_symlink():
            path.unlink()
        return None
    model = (
        requirement
        if isinstance(requirement, ConfirmationRequirement)
        else ConfirmationRequirement.from_dict(requirement)
    )
    if model.alias != alias:
        raise ValueError("Confirmation alias does not match reconciliation target.")
    current = load_confirmation_requirement(project, alias)
    if current is None or current.to_dict() != model.to_dict():
        save_confirmation_requirement(project, model)
    return model


def save_refresh_impact(project: Path, impact: RefreshImpactResult) -> None:
    save_document(layout.refresh_impact_path(project, impact.alias), impact.to_dict())


def load_refresh_impact(project: Path, alias: str) -> RefreshImpactResult | None:
    data = load_document(layout.refresh_impact_path(project, alias), default=None)
    return RefreshImpactResult.from_dict(data) if isinstance(data, dict) else None


def save_supersede_review(project: Path, alias: str, review: SupersedeReview) -> SupersedeReview:
    save_document(layout.supersede_review_path(project, alias, review.reviewId), review.to_dict())
    return review


def load_supersede_reviews(project: Path, alias: str) -> list[SupersedeReview]:
    directory = layout.supersede_reviews_dir(project, alias)
    if not directory.exists():
        return []
    reviews: list[SupersedeReview] = []
    for path in sorted(directory.glob("*.yaml")):
        data = load_document(path, default={})
        if isinstance(data, dict):
            reviews.append(SupersedeReview.from_dict(data))
    return reviews


def save_capability_policy(project: Path, policy: ArtifactCapabilityPolicy) -> None:
    save_document(layout.capability_policy_path(project, policy.capability), policy.to_dict())


def load_capability_policy(project: Path, capability: str) -> ArtifactCapabilityPolicy | None:
    data = load_document(layout.capability_policy_path(project, capability), default=None)
    return ArtifactCapabilityPolicy.from_dict(data) if isinstance(data, dict) else None


def create_readiness_snapshot_from_validation(
    project: Path,
    alias: str,
    result: dict[str, Any],
    *,
    protected_operation_attempted: bool = False,
) -> ReadinessSnapshot:
    record = load_use_case(project, alias)
    managed = result.get("managedRuntimeReadiness") if isinstance(result.get("managedRuntimeReadiness"), dict) else {}
    runtime = result.get("runtimeReadiness") if isinstance(result.get("runtimeReadiness"), dict) else {}
    outcome = result.get("coreOutcome") if isinstance(result.get("coreOutcome"), dict) else {}
    command_status = str(runtime.get("commandCompatibilityStatus") or managed.get("commandCompatibilityStatus") or "not-checked")
    trust_status = str(runtime.get("trustMaterialStatus") or managed.get("trustMaterialStatus") or "not-checked")
    protected_status = (
        str(
            runtime.get("protectedOperationStatus")
            or (
                "passed"
                if outcome.get("kind") == "success" and outcome.get("status") == "passed"
                else "blocked"
                if outcome
                else "not-checked"
            )
        )
        if protected_operation_attempted
        else "not-checked"
    )
    readiness_scope = (
        str(
            runtime.get("readinessScope")
            or ("protected-operation" if outcome else "command-and-trust-inputs")
        )
        if protected_operation_attempted
        else "command-and-trust-inputs"
    )
    status = (
        "ready"
        if result.get("status") == "passed"
        and command_status == "passed"
        and trust_status == "ready"
        and protected_status == "passed"
        and readiness_scope == "protected-operation"
        else "blocked"
    )
    snapshot = ReadinessSnapshot(
        alias=alias,
        status=status,
        checkedAt=now_iso(),
        commandCompatibilityStatus=command_status,  # type: ignore[arg-type]
        trustMaterialStatus=trust_status,  # type: ignore[arg-type]
        protectedOperationStatus=protected_status,  # type: ignore[arg-type]
        readinessScope=readiness_scope,  # type: ignore[arg-type]
        artifactFingerprints=artifact_fingerprints(project, record),
        specVersion=SPEC_VERSION,
        artifactContractVersion=record.schemaVersion,
        coreVersion=managed.get("runtimeVersion"),
        coreContractVersion=managed.get("contractVersion"),
        targetProjectRevision=current_project_revision(project),
        testedCodeScopeStatus="unknown",
        environmentBoundCredentialGroups=[item["group"] for item in credential_runtime_requirements(record)],
        sideEffectClass=side_effect_class(record),
        refreshImpactStatus=(load_refresh_impact(project, alias).status if load_refresh_impact(project, alias) else None),
        invalidationReasons=[],
        summary=result.get("readinessSummary") or runtime.get("message") or result.get("status"),
    )
    save_readiness_snapshot(project, snapshot)
    return snapshot


# Reasons that are inherent, structural properties of a use case (a credentialed binding, a
# committed write) rather than fixable drift. A snapshot that PASSED and carries only these is a
# trusted ceiling, not a problem — it renders as green-with-lock and suggests no command, because
# no command would move it. Reserve amber strictly for drift a command can clear.
CEILING_REASONS = {"environment-bound", "write-post-commit-risk"}
# Freshness drift that a plain re-validate/rerun clears.
FRESHNESS_REASONS = {"age-expired", "artifact-changed", "target-revision-changed"}


def readiness_current_state(project: Path, record: UseCaseRecord) -> dict[str, Any]:
    snapshot = load_readiness_snapshot(project, record.alias)
    last_run = record.lastRun if isinstance(record.lastRun, dict) else None
    if not snapshot:
        return {
            "status": "not-checked",
            "label": _current_label("not-checked"),
            "nextAction": _readiness_next_action("not-checked", record.alias),
            "presentation": _readiness_presentation("not-checked"),
            "checked": False,
            "checkedAt": None,
            "reasons": ["No current readiness snapshot has been recorded."],
            "lastRunStatus": last_run.get("status") if last_run else None,
        }
    reasons = snapshot_invalidation_reasons(project, record, snapshot)
    reason_codes = {item["code"] for item in reasons}
    freshness = reason_codes & FRESHNESS_REASONS
    actionable_drift = reason_codes - CEILING_REASONS - FRESHNESS_REASONS  # spec-version / refresh-impact
    if snapshot.status == "blocked":
        # A failed validation must win over freshness so a real failure is never hidden as 'stale'.
        status = "blocked"
    elif freshness:
        # Freshness drift — re-validating clears it (and takes precedence over the write-rerun guard).
        status = "stale"
    elif actionable_drift:
        # spec-version / refresh-impact drift — a re-validate re-stamps/clears it.
        status = "needs-validate"
    elif "write-post-commit-risk" in reason_codes:
        # A committed write that PASSED: trusted, but the NEXT run needs confirmation. The lock flips
        # to 'confirmed' once a supersede/approve review matches this run (read the same source the
        # rerun gate reads). Re-validating never clears it; it is a ceiling, not a problem.
        status = "rerun-confirmed" if _has_matching_supersede_review(project, record) else "needs-rerun-confirmation"
    elif "environment-bound" in reason_codes:
        # A credentialed read that PASSED: trusted ceiling, credentials re-checked at run preflight.
        status = "ready-credential-bound"
    elif snapshot.status == "ready":
        status = "ready"
    else:
        status = "needs-validate"
    current = {
        "status": status,
        "label": _current_label(status),
        "nextAction": _readiness_next_action(status, record.alias),
        "presentation": _readiness_presentation(status),
        "checked": True,
        "checkedAt": snapshot.checkedAt,
        "ageSeconds": _snapshot_age_seconds(snapshot),
        "reasons": [item["message"] for item in reasons],
        "invalidationReasons": reasons,
        "snapshotStatus": snapshot.status,
        "lastRunStatus": last_run.get("status") if last_run else None,
        "environmentBoundCredentialGroups": snapshot.environmentBoundCredentialGroups,
        "testedCodeScopeStatus": snapshot.testedCodeScopeStatus,
    }
    if status == "needs-rerun-confirmation":
        # Informational pointer, NOT a 'fix this' command: only when the owner intends to rerun.
        current["confirmHint"] = f"verifysignal workflow approve-rerun --alias {record.alias} --json"
    if status == "stale" and "write-post-commit-risk" in reason_codes:
        # Disclose the still-pending rerun gate during the stale window so it does not ambush the
        # owner after they re-validate the freshness drift.
        current["pendingCeilingNote"] = (
            "After re-checking freshness, this committed write still needs rerun confirmation before the next run."
        )
    return current


def _has_matching_supersede_review(project: Path, record: UseCaseRecord) -> bool:
    """True when a supersede/approve review exists for the use case whose ``sourceRunId`` matches the
    current ``lastRun.runId`` — i.e. the owner has confirmed THIS run. Mirrors the gate's matching
    logic (``write_safety._matching_supersede_review``) but reads locally to avoid a workspace↔workflows
    import cycle. The readiness badge reads the same source the rerun gate already honors."""

    last_run = record.lastRun if isinstance(record.lastRun, dict) else {}
    run_id = str(last_run.get("runId") or "")
    if not run_id:
        return False
    for review in load_supersede_reviews(project, record.alias):
        source_run_id = getattr(review, "sourceRunId", None)
        if source_run_id is None and isinstance(review, dict):
            source_run_id = review.get("sourceRunId")
        if str(source_run_id or "") == run_id:
            return True
    return False


def _spec_minor(version: str | None) -> tuple[int, int]:
    parts = (version or "").split(".")
    try:
        return (int(parts[0]), int(parts[1]))
    except (ValueError, IndexError):
        return (0, 0)


def snapshot_invalidation_reasons(project: Path, record: UseCaseRecord, snapshot: ReadinessSnapshot) -> list[dict[str, str]]:
    reasons: list[dict[str, str]] = []
    current_fingerprints = artifact_fingerprints(project, record)
    for path, old_hash in snapshot.artifactFingerprints.items():
        if current_fingerprints.get(path) != old_hash:
            reasons.append({"code": "artifact-changed", "message": f"Artifact changed since readiness check: {path}"})
            break
    if snapshot.specVersion and _spec_minor(snapshot.specVersion) != _spec_minor(SPEC_VERSION):
        # Wart #1: only a minor/major Spec change invalidates readiness — a patch (bug fix) does
        # not change readiness semantics, so it must not churn every snapshot to needs-validate.
        reasons.append({"code": "spec-version-changed", "message": f"Spec major/minor version changed from {snapshot.specVersion} to {SPEC_VERSION}."})
    current_revision = current_project_revision(project)
    if snapshot.targetProjectRevision and current_revision and snapshot.targetProjectRevision != current_revision:
        reasons.append({"code": "target-revision-changed", "message": "Target project revision changed since readiness check."})
    max_age_hours = 24 if _risk_requires_short_snapshot(record) else 24 * 7
    age_seconds = _snapshot_age_seconds(snapshot)
    if age_seconds is None or age_seconds > max_age_hours * 3600:
        reasons.append({"code": "age-expired", "message": f"Readiness snapshot is older than the {max_age_hours} hour risk threshold."})
    if snapshot.environmentBoundCredentialGroups:
        reasons.append({"code": "environment-bound", "message": "Snapshot depends on credential/environment state and does not guarantee the current process."})
    if _effective_rerun_write_risk(project, record):
        reasons.append({"code": "write-post-commit-risk", "message": "Previous write run has inferred or unknown post-commit activity."})
    impact = load_refresh_impact(project, record.alias)
    if impact and impact.status in {"affected", "unknown"}:
        reasons.append({"code": f"refresh-impact-{impact.status}", "message": impact.reason or f"Understanding refresh impact is {impact.status}."})
    return reasons


def list_requirements(record: UseCaseRecord) -> dict[str, Any]:
    return {
        "runtimeInputs": [item.name for item in record.runtimeInputs if item.kind != "credential"],
        "credentials": credential_runtime_requirements(record),
        "sideEffectClass": side_effect_class(record),
        "cleanupPolicy": lifecycle_declaration(record).cleanupPolicy,
        "namedOutputs": [
            str(item.get("name"))
            for item in record.runtimeOutputs
            if isinstance(item, dict) and item.get("publishAsNamedOutput") and item.get("name")
        ],
    }


def list_risk(project: Path, record: UseCaseRecord) -> dict[str, Any]:
    # Import locally to keep workspace persistence independent from workflow
    # policy modules at import time.
    from verifysignal_spec.workflows.run_preflight import build_run_preflight

    preflight = build_run_preflight(
        {
            "confirmationRequirements": calculate_run_confirmation_requirements(project, record),
        },
        record,
        load_readiness_snapshot(project, record.alias),
        {},
        load_supersede_reviews(project, record.alias),
    )
    confirmation = reconcile_active_confirmation(
        project,
        record.alias,
        preflight.get("confirmation"),
    )
    capability = record.artifactCapabilities if isinstance(record.artifactCapabilities, dict) else {}
    risk_assertions = side_effect_risk_assertions(record)
    rerun = {
        **_rerun_policy_summary(record),
        **preflight["rerunDecision"],
    }
    return {
        "classes": _risk_classes(record),
        "write": side_effect_class(record) in {"write", "external-notification"},
        "cleanupPolicy": lifecycle_declaration(record).cleanupPolicy,
        "cleanupDeclared": lifecycle_declaration(record).cleanupPolicy != "not-declared",
        "capabilityStatus": capability.get("status", "legacy-or-unknown" if not capability else "unknown"),
        "requiresConfirmation": bool(confirmation and confirmation.blocksExecution),
        "confirmationId": confirmation.id if confirmation else None,
        "riskAssertions": risk_assertions,
        "rerun": rerun,
    }


def _rerun_policy_summary(record: UseCaseRecord) -> dict[str, Any]:
    if side_effect_class(record) not in {"write", "external-notification"}:
        return {"required": False}
    policy = RerunPolicy.from_dict(record.rerunPolicy)
    return {
        "required": True,
        "afterCommit": policy.afterCommit,
        "refreshRuntimeInputs": list(policy.refreshRuntimeInputs),
        "summary": _rerun_summary_text(policy.afterCommit),
    }


def _rerun_summary_text(decision: str) -> str:
    if decision == "allowed-with-new-inputs":
        return "Rerun allowed with refreshed generated inputs."
    if decision == "requires-confirmation":
        return "Rerun requires owner confirmation."
    if decision == "blocked":
        return "Rerun blocked until policy or state changes."
    return "Rerun allowed by declared policy."


def credential_runtime_requirements(record: UseCaseRecord) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    refs = record.credentialRefs if isinstance(record.credentialRefs, dict) else {}
    for group, data in refs.items():
        if not isinstance(data, dict):
            continue
        keys = data.get("keys") if isinstance(data.get("keys"), dict) else {}
        groups.append(
            {
                "group": str(group),
                "source": str(data.get("source") or "environment"),
                "runtimeNames": [str(value) for value in keys.values() if value],
                "fields": sorted(str(key) for key in keys),
            }
        )
    for group in record.credentialGroups:
        name = group.get("name") if isinstance(group, dict) else group
        if name and not any(item["group"] == str(name) for item in groups):
            groups.append({"group": str(name), "source": "unknown", "runtimeNames": [], "fields": []})
    return groups


def side_effect_class(record: UseCaseRecord) -> str:
    data = record.sideEffects if isinstance(record.sideEffects, dict) else {}
    return str(data.get("class") or data.get("sideEffectClass") or "none")


def side_effect_risk_assertions(record: UseCaseRecord) -> list[dict[str, Any]]:
    """Normalize persisted public side-effect risk signals.

    Consumers should depend on this assertion shape instead of branching on
    every historical or future field that may carry risk evidence.
    """

    last_run = record.lastRun if isinstance(record.lastRun, dict) else {}
    assertions: list[dict[str, Any]] = []
    for item in last_run.get("riskAssertions", []):
        if isinstance(item, dict):
            assertions.append(_normalize_risk_assertion(item, source="prior-run"))
    for key in ["writeRisk", "sideEffectRisk"]:
        if isinstance(last_run.get(key), dict):
            assertions.append(_normalize_risk_assertion(last_run[key], source=key))
    legacy = _legacy_post_commit_risk_assertion(last_run)
    if legacy:
        assertions.append(legacy)
    return [assertion for assertion in assertions if _risk_assertion_requires_confirmation(assertion)]


def lifecycle_declaration(record: UseCaseRecord) -> SideEffectLifecycleDeclaration:
    side_effects = record.sideEffects if isinstance(record.sideEffects, dict) else {}
    lifecycle = record.sideEffectLifecycle or side_effects.get("lifecycle")
    return SideEffectLifecycleDeclaration.from_dict(lifecycle if isinstance(lifecycle, dict) else None)


def capability_stamp(capabilities: list[str], *, contract_version: str, authored_at: str | None = None) -> dict[str, Any]:
    return ArtifactCapabilityStamp(
        specVersion=SPEC_VERSION,
        artifactContractVersion=contract_version,
        authoredAt=authored_at or now_iso(),
        capabilities=capabilities,
    ).to_dict()


def confirmation_requirement(
    *,
    alias: str,
    risk_class: str,
    scope: str,
    reason: str,
    recommended_action: str,
    blocks_execution: bool = True,
) -> ConfirmationRequirement:
    return ConfirmationRequirement(
        id=f"confirm.{alias}.{scope}",
        alias=alias,
        riskClass=risk_class,
        scope=scope,
        reason=reason,
        recommendedAction=recommended_action,
        blocksExecution=blocks_execution,
        expiresWhen=[
            "use-case artifact changes",
            "run request changes",
            "main skill changes",
            "target project revision changes",
            "24 hours pass for write or credentialed use cases",
        ],
    )


def calculate_run_confirmation_requirements(project: Path, record: UseCaseRecord) -> list[ConfirmationRequirement]:
    """Derive non-rerun run confirmations without mutating active gate state."""

    requirements: list[ConfirmationRequirement] = []
    side_effect = side_effect_class(record)
    unresolved_risks = side_effect_risk_assertions(record)
    if side_effect not in {"write", "external-notification"}:
        from verifysignal_spec.workflows.write_safety import (
            policy_changed_after_violation_run,
        )

        policy_changed = policy_changed_after_violation_run(
            record,
            record.lastRun if isinstance(record.lastRun, dict) else {},
        )
        if unresolved_risks and not policy_changed:
            risk = unresolved_risks[0]
            requirements.append(
                confirmation_requirement(
                    alias=record.alias,
                    risk_class="unknown-write-risk",
                    scope="unresolved-side-effect-risk",
                    reason=str(risk.get("reason") or "A persisted side-effect risk assertion is unresolved for this use case."),
                    recommended_action="Review cleanup/idempotency and explicitly confirm the side-effect risk before rerun.",
                )
            )
        return requirements
    lifecycle = lifecycle_declaration(record)
    capabilities = _capability_names(record)
    legacy = not capabilities
    if lifecycle.cleanupPolicy == "not-declared":
        requirements.append(
            confirmation_requirement(
                alias=record.alias,
                risk_class=side_effect,
                scope="missing-side-effect-lifecycle",
                reason=(
                    "Legacy write/external-notification artifact has no cleanup lifecycle declaration."
                    if legacy
                    else "Write/external-notification artifact has no cleanup lifecycle declaration."
                ),
                recommended_action="Migrate the artifact to declare cleanup lifecycle before future write runs.",
            )
        )
    safety_capabilities = {"explicit-confirmation", "side-effect-lifecycle", "write-activity-interpretation"}
    if not safety_capabilities <= capabilities:
        missing = sorted(safety_capabilities - capabilities) if capabilities else sorted(safety_capabilities)
        requirements.append(
            confirmation_requirement(
                alias=record.alias,
                risk_class=side_effect,
                scope="legacy-missing-safety-capability",
                reason=f"Artifact is missing safety capability metadata: {', '.join(missing)}.",
                recommended_action="Migrate or re-persist the artifact so current write safety capabilities are declared.",
            )
        )
    if _post_commit_rerun_requires_confirmation(record):
        requirements.append(
            confirmation_requirement(
                alias=record.alias,
                risk_class=side_effect,
                scope="post-commit-rerun",
                reason="Previous write run has inferred, confirmed, or unknown post-commit activity.",
                recommended_action="Clean up, refresh generated inputs, declare idempotency, or explicitly confirm rerun risk.",
            )
        )
    impact = load_refresh_impact(project, record.alias)
    if impact and impact.status == "unknown":
        requirements.append(
            confirmation_requirement(
                alias=record.alias,
                risk_class=side_effect,
                scope="unknown-refresh-impact",
                reason=impact.reason or "Refresh impact on this write use case is unknown.",
                recommended_action="Validate or refresh understanding before executing, or explicitly confirm the write risk.",
            )
        )
    return requirements


def run_confirmation_requirements(project: Path, record: UseCaseRecord) -> list[ConfirmationRequirement]:
    """Compatibility wrapper for callers that historically materialized a gate."""

    requirements = calculate_run_confirmation_requirements(project, record)
    if requirements:
        reconcile_active_confirmation(project, record.alias, requirements[0])
    return requirements


def side_effect_lifecycle_summary(record: UseCaseRecord, runtime_outputs: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    lifecycle = lifecycle_declaration(record)
    outputs = runtime_outputs or []
    refs = [
        {"name": item.get("name"), "source": item.get("source"), "value": item.get("value"), "status": item.get("status")}
        for item in outputs
        if isinstance(item, dict) and item.get("value")
    ]
    return {
        "cleanupPolicy": lifecycle.cleanupPolicy,
        "cleanupRequired": lifecycle.cleanupRequired,
        "trackingIntent": lifecycle.trackingIntent,
        "instructions": lifecycle.instructions,
        "declared": lifecycle.cleanupPolicy != "not-declared",
        "resourceRefs": refs,
        "status": "not-declared" if lifecycle.cleanupPolicy == "not-declared" else "declared",
    }


def _risk_requires_short_snapshot(record: UseCaseRecord) -> bool:
    return bool(credential_runtime_requirements(record)) or side_effect_class(record) in {"write", "external-notification"}


def _last_run_has_write_risk(record: UseCaseRecord) -> bool:
    return bool(side_effect_risk_assertions(record))


def _effective_rerun_write_risk(project: Path, record: UseCaseRecord) -> bool:
    attempt = record.lastCoreAttempt
    if attempt is None or attempt.operation != "run":
        return _last_run_has_write_risk(record)
    from verifysignal_spec.workflows.write_safety import evaluate_rerun_decision

    decision = evaluate_rerun_decision(
        record,
        supersede_reviews=load_supersede_reviews(project, record.alias),
    )
    return bool(
        decision.get("outcomeClass") in {"commit", "unknown-write"}
        and decision.get("decision") in {"blocked", "requires-confirmation"}
    )


def _normalize_risk_assertion(assertion: dict[str, Any], *, source: str) -> dict[str, Any]:
    return {
        "status": str(assertion.get("status") or assertion.get("sideEffectStatus") or "unknown"),
        "source": str(assertion.get("source") or source),
        "requiresConfirmationBeforeRun": bool(assertion.get("requiresConfirmationBeforeRun", False)),
        "reason": str(assertion.get("reason") or assertion.get("message") or "Persisted side-effect risk assertion requires review."),
    }


def _legacy_post_commit_risk_assertion(last_run: dict[str, Any]) -> dict[str, Any] | None:
    interpretation = last_run.get("postCommitInterpretation") if isinstance(last_run.get("postCommitInterpretation"), dict) else {}
    if not interpretation:
        return None
    risky = bool(interpretation.get("postCommit") or interpretation.get("sideEffectMayExist") or interpretation.get("sideEffectStatus") == "unknown")
    if not risky:
        return None
    return {
        "status": str(interpretation.get("sideEffectStatus") or "unknown"),
        "source": "legacy-post-commit-interpretation",
        "requiresConfirmationBeforeRun": True,
        "reason": str(interpretation.get("message") or "Previous run has unresolved side-effect risk."),
    }


def _risk_assertion_requires_confirmation(assertion: dict[str, Any]) -> bool:
    if assertion.get("requiresConfirmationBeforeRun") is True:
        return True
    return str(assertion.get("status") or "").lower() in {"possible", "inferred", "confirmed", "unknown"}


def _post_commit_rerun_requires_confirmation(record: UseCaseRecord) -> bool:
    if not _last_run_has_write_risk(record):
        return False
    policy = RerunPolicy.from_dict(record.rerunPolicy)
    if policy.afterCommit == "blocked":
        return False
    if policy.afterCommit == "allowed-with-new-inputs":
        refreshable = {item.name for item in record.runtimeInputs if item.source == "generated" and item.refreshOnRerunAfterCommit}
        return not bool(set(policy.refreshRuntimeInputs) & refreshable)
    return policy.afterCommit in {"requires-confirmation", "allowed"}


def _risk_classes(record: UseCaseRecord) -> list[str]:
    classes: list[str] = []
    if credential_runtime_requirements(record):
        classes.append("credentialed")
    side_effect = side_effect_class(record)
    if side_effect in {"write", "external-notification"}:
        classes.append(side_effect)
    if _last_run_has_write_risk(record):
        classes.append("post-commit")
    if not classes:
        classes.append("read-only")
    return classes


def _capability_names(record: UseCaseRecord) -> set[str]:
    raw = record.artifactCapabilities if isinstance(record.artifactCapabilities, dict) else {}
    if isinstance(raw.get("capabilities"), list):
        return {str(item) for item in raw.get("capabilities", [])}
    stamp = raw.get("stamp") if isinstance(raw.get("stamp"), dict) else {}
    if isinstance(stamp.get("capabilities"), list):
        return {str(item) for item in stamp.get("capabilities", [])}
    return set()


def _snapshot_age_seconds(snapshot: ReadinessSnapshot) -> int | None:
    try:
        checked = datetime.fromisoformat(snapshot.checkedAt.replace("Z", "+00:00"))
    except ValueError:
        return None
    if checked.tzinfo is None:
        checked = checked.replace(tzinfo=UTC)
    return int((datetime.now(UTC) - checked.astimezone(UTC)).total_seconds())


def _current_label(status: str) -> str:
    labels = {
        "ready": "Last checked ready",
        "ready-credential-bound": "Verified · credential-bound (re-checked at run)",
        "not-checked": "Not checked",
        "stale": "Out of date — re-check",
        "needs-validate": "Needs validation",
        "needs-rerun-confirmation": "Verified · confirm before next run",
        "rerun-confirmed": "Verified · rerun confirmed",
        "blocked": "Blocked",
    }
    return labels.get(status, "Unknown")


def _readiness_presentation(status: str) -> dict[str, Any]:
    # Ceiling statuses (ceiling=True) are a use case that PASSED and sits at an inherent safety floor;
    # they render as a calm green-with-lock and carry NO suggested command (running one would not move
    # them). Amber/red carry a command that provably moves the state.
    presentations = {
        "ready": {"severity": "ok", "icon": "🟢", "ceiling": False, "headline": "Ready"},
        "ready-credential-bound": {"severity": "ok-ceiling", "icon": "🔒", "ceiling": True, "headline": "Verified · credentials re-checked at run"},
        "needs-rerun-confirmation": {"severity": "ok-ceiling", "icon": "🔒", "ceiling": True, "headline": "Verified · confirm before next run"},
        "rerun-confirmed": {"severity": "ok-ceiling", "icon": "🔓", "ceiling": True, "headline": "Verified · rerun confirmed"},
        "needs-validate": {"severity": "attention", "icon": "🟡", "ceiling": False, "headline": "Needs validation"},
        "stale": {"severity": "attention", "icon": "🟡", "ceiling": False, "headline": "Out of date — re-check"},
        "blocked": {"severity": "failed", "icon": "🔴", "ceiling": False, "headline": "Blocked — validation failed"},
        "not-checked": {"severity": "unknown", "icon": "⚪", "ceiling": False, "headline": "Not checked yet"},
    }
    return presentations.get(status, {"severity": "unknown", "icon": "⚪", "ceiling": False, "headline": "Unknown"})


def _readiness_next_action(status: str, alias: str) -> str | None:
    # Honesty invariant: a status carries a suggested command ONLY when running it can move the
    # state. Ceiling (lock) and plain ready carry none — the no-op 'workflow check run' suggestion
    # for committed writes is intentionally gone (it never cleared the badge).
    if status == "stale":
        return f"verifysignal validate {alias} --runtime-readiness --json"
    if status in {"needs-validate", "blocked", "not-checked"}:
        return f"verifysignal validate {alias} --json"
    return None
