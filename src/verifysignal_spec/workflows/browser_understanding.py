from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import re
from typing import Any
from urllib.parse import urlsplit, urlunsplit


BROWSER_FIRST_UNDERSTANDING_CAPABILITY = "browser-first-understanding/v1"
UNDERSTANDING_MODES = ("repository", "browser-first", "hybrid")

DEFAULT_EXPLORATION_SCOPE: dict[str, Any] = {
    "maxPagesOrStates": 20,
    "maxDepth": 3,
    "candidateRange": {"minimum": 3, "maximum": 5},
    "softTimeBudgetMinutes": 15,
    "readSafeOnly": True,
    "excludedActions": [
        "destructive",
        "transactional",
        "state-changing",
        "unknown-safety",
    ],
}

FORBIDDEN_BROWSER_FIELDS = (
    "rawDom",
    "dom",
    "html",
    "mcpSnapshot",
    "snapshot",
    "screenshot",
    "screenshotPath",
    "trace",
    "har",
    "responseBody",
    "requestBody",
    "requestHeaders",
    "responseHeaders",
    "headers",
    "cookies",
    "localStorage",
    "sessionStorage",
    "storageState",
    "storageStatePath",
    "credentials",
    "authorization",
    "accessToken",
    "refreshToken",
    "sessionToken",
    "formValues",
    "query",
    "queryString",
    "queryParams",
)

_FORBIDDEN_BROWSER_FIELD_TOKENS = {
    re.sub(r"[^a-z0-9]", "", field.lower()): field for field in FORBIDDEN_BROWSER_FIELDS
}
_SIGNAL_ID = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_MODE_ALIASES = {
    "repository": "repository",
    "repo": "repository",
    "source": "repository",
    "browser-first": "browser-first",
    "browser_first": "browser-first",
    "browser": "browser-first",
    "live-url": "browser-first",
    "engagement": "browser-first",
    "hybrid": "hybrid",
}
_SIGNAL_KINDS = {"surface", "state", "transition", "runtime-requirement", "gap"}
_PROVENANCE_VALUES = {"browser", "repository", "hybrid"}
_CONFIDENCE_VALUES = {"high", "medium", "low"}
_SCOPE_STATUS_VALUES = {"complete", "partial", "blocked"}
_GROUNDING_STATUS_VALUES = {
    "observed",
    "partial",
    "authentication-required",
    "blocked",
    "unknown",
}
_SIDE_EFFECT_VALUES = {"none", "write", "external-notification", "unknown"}
_BROWSER_TOP_LEVEL_FIELDS = {
    "understandingMode",
    "workspaceKind",
    "productSummary",
    "repositorySummary",
    "localStartInstructions",
    "targetEnvironment",
    "explorationScope",
    "productSignals",
    "coverageInventory",
    "gaps",
    "provenanceTraceabilityStatus",
    "observedAt",
    "generatedGitHash",
    "gitAvailable",
    "gitUnavailableReason",
    "gitBranch",
    "safeInspectionPaths",
    "blockedSensitivePaths",
    "validationGoals",
    "knownRuntimeRequirements",
    "sourceFilesVisited",
    "partialInventoryReasons",
    "refreshImpacts",
}
_TARGET_FIELDS = {
    "kind",
    "locator",
    "environment",
    "reachabilityStatus",
    "observedAt",
    "origin",
    "allowedOrigins",
}
_SCOPE_FIELDS = {
    "allowedOrigins",
    "maxPagesOrStates",
    "maxDepth",
    "candidateRange",
    "softTimeBudgetMinutes",
    "readSafeOnly",
    "excludedActions",
    "status",
    "stopReason",
    "partialInventoryReasons",
}
_SIGNAL_FIELDS = {
    "id",
    "kind",
    "surface",
    "state",
    "summary",
    "evidence",
    "provenance",
    "observedAt",
    "confidence",
    "inventoryItemRefs",
    "fromSurface",
    "toSurface",
}
_INVENTORY_FIELDS = {
    "status",
    "generatedAt",
    "generatedGitHash",
    "gitAvailable",
    "sourceFilesVisited",
    "sourceTraceabilityStatus",
    "partialInventoryReasons",
    "passes",
    "items",
    "candidateUseCases",
    "uncoveredAreas",
    "staleAreas",
}
_INVENTORY_ITEM_FIELDS = {
    "id",
    "surfaceType",
    "path",
    "title",
    "sourceRefs",
    "userFacing",
    "inventoryStatus",
    "exclusionReason",
    "candidateUseCaseRefs",
    "priority",
    "productSignalRefs",
    "provenance",
}
_CANDIDATE_FIELDS = {
    "alias",
    "surface",
    "behavior",
    "sourceInventoryItems",
    "rationale",
    "confidence",
    "inventorySourceStatus",
    "priority",
    "requiresEnvironment",
    "knownRuntimeRequirements",
    "productSignalRefs",
    "provenance",
    "sideEffectClass",
    "groundingStatus",
    "proofStatus",
}
_PASS_FIELDS = {
    "scope",
    "startedAt",
    "completedAt",
    "coveredAreas",
    "uncoveredAreas",
    "sourceFilesVisited",
    "status",
}
_REFRESH_IMPACT_FIELDS = {
    "alias",
    "status",
    "reason",
    "affectedAreas",
    "recommendedAction",
    "generatedAt",
    "schemaVersion",
}
_RUNTIME_REQUIREMENT_FIELDS = {
    "name",
    "kind",
    "required",
    "description",
    "source",
    "envVar",
    "credentialGroup",
    "persistValue",
    "template",
    "default",
    "value",
    "refreshOnRerunAfterCommit",
    "references",
}


def normalize_understanding_mode(value: Any) -> str:
    token = str(value or "repository").strip().lower()
    mode = _MODE_ALIASES.get(token)
    if mode is None:
        raise ValueError(
            "understandingMode must be repository, browser-first, or hybrid."
        )
    return mode


def sanitize_browser_url(value: Any) -> str:
    raw = str(value or "").strip()
    try:
        parsed = urlsplit(raw)
        port = parsed.port
    except ValueError as exc:
        raise ValueError(f"Browser target URL is invalid: {exc}") from exc
    if parsed.scheme.lower() not in {"http", "https"}:
        raise ValueError("Browser target URL must use HTTP(S).")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("Browser target URL must not contain credentials.")
    if not parsed.hostname:
        raise ValueError("Browser target URL requires a host.")

    scheme = parsed.scheme.lower()
    host = parsed.hostname.lower()
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    default_port = (scheme == "http" and port == 80) or (
        scheme == "https" and port == 443
    )
    authority = host if port is None or default_port else f"{host}:{port}"
    path = parsed.path or "/"
    if not path.startswith("/"):
        path = f"/{path}"
    return urlunsplit((scheme, authority, path, "", ""))


def browser_origin(value: Any) -> str:
    sanitized = sanitize_browser_url(value)
    parsed = urlsplit(sanitized)
    return f"{parsed.scheme}://{parsed.netloc}"


def normalize_browser_understanding_payload(
    payload: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Understanding payload must be an object.")
    normalized = deepcopy(payload)
    mode = normalize_understanding_mode(
        normalized.get("understandingMode") or normalized.get("mode")
    )
    normalized["understandingMode"] = mode
    if mode == "repository":
        normalized.setdefault("workspaceKind", "repository")
        return normalized

    _reject_forbidden_browser_fields(normalized)
    normalized = _normalize_browser_aliases(normalized, mode=mode)
    _reject_unknown_fields(
        normalized, _BROWSER_TOP_LEVEL_FIELDS, "payload"
    )
    _normalize_browser_compatibility_fields(normalized)
    product_summary = str(
        normalized.get("productSummary")
        or normalized.get("repositorySummary")
        or ""
    ).strip()
    if not product_summary:
        raise ValueError(
            "Browser-first understanding requires productSummary."
        )
    normalized["productSummary"] = product_summary
    normalized["workspaceKind"] = (
        "hybrid" if mode == "hybrid" else "engagement"
    )

    target = _normalize_target_environment(normalized)
    normalized["targetEnvironment"] = target
    scope = _normalize_exploration_scope(
        normalized.get("explorationScope"), target["allowedOrigins"]
    )
    normalized["explorationScope"] = scope

    signals = _normalize_product_signals(normalized.get("productSignals"))
    normalized["productSignals"] = signals
    inventory = _normalize_browser_inventory(
        normalized.get("coverageInventory"), mode=mode
    )
    normalized["coverageInventory"] = inventory
    _validate_browser_references(signals, inventory)

    gaps = _normalize_gaps(
        normalized.get("gaps")
        or scope.get("partialInventoryReasons")
        or inventory.get("partialInventoryReasons")
        or []
    )
    candidate_count = len(inventory["candidateUseCases"])
    candidate_minimum = scope["candidateRange"]["minimum"]
    if candidate_count < candidate_minimum:
        reason = (
            f"Observed {candidate_count} candidate journey(s), below the "
            f"exploration candidate minimum of {candidate_minimum}."
        )
        if reason not in gaps:
            gaps.append(reason)
        inventory["status"] = "partial"
        scope["status"] = "partial"
        _append_unique(inventory["partialInventoryReasons"], reason)
        _append_unique(scope["partialInventoryReasons"], reason)

    if scope["status"] != "complete" and inventory["status"] == "complete":
        inventory["status"] = "partial"
    if inventory["status"] != "complete" and scope["status"] == "complete":
        scope["status"] = "partial"

    normalized["gaps"] = gaps
    normalized["provenanceTraceabilityStatus"] = _provenance_status(
        mode, signals, gaps
    )
    normalized["observedAt"] = target["observedAt"]
    normalized.setdefault("repositorySummary", product_summary)
    normalized.setdefault("localStartInstructions", "")
    normalized["gitAvailable"] = mode == "hybrid" and bool(
        normalized.get("generatedGitHash")
    )
    if mode == "browser-first":
        normalized["generatedGitHash"] = None
    return normalized


def browser_first_capability_contract() -> dict[str, Any]:
    return {
        "capability": BROWSER_FIRST_UNDERSTANDING_CAPABILITY,
        "modes": list(UNDERSTANDING_MODES),
        "modeRequirements": {
            "repository": [
                "repositorySummary",
                "localStartInstructions",
                "coverageInventory",
                "generatedGitHash or gitUnavailableReason",
            ],
            "browser-first": [
                "productSummary",
                "targetEnvironment",
                "explorationScope",
                "productSignals",
                "coverageInventory",
            ],
            "hybrid": [
                "repositorySummary",
                "localStartInstructions",
                "targetEnvironment",
                "explorationScope",
                "productSignals",
                "coverageInventory",
                "generatedGitHash or gitUnavailableReason",
            ],
        },
        "defaults": deepcopy(DEFAULT_EXPLORATION_SCOPE),
        "mapping": {
            "readSafeOnly": True,
            "originPolicy": "explicit-allowed-origins",
            "candidateOutcome": "three-to-five-when-observable-otherwise-partial",
        },
        "authentication": {
            "default": "assisted-headed",
            "credentialEntry": "user-directly-in-browser",
            "completion": "explicit-user-signal",
        },
        "browserLifecycle": {
            "headed": True,
            "pacing": "human-observable",
            "close": "after-user-acknowledgement",
        },
        "forbiddenPersistence": list(FORBIDDEN_BROWSER_FIELDS),
        "providerBoundary": "playwright-mcp-or-equivalent-host-browser",
        "proofHandoff": {
            "selection": "explicit-user-approval",
            "readOnly": "public-core-workflow",
            "potentiallyMutating": "explicit-confirmation-plus-public-probe",
            "probeSchema": "verifysignal.probe/v1",
            "probeCommitsWrite": False,
        },
        "compatibility": {
            "productContextSchema": "verifysignal-spec-product-context/v1",
            "legacyModeDefault": "repository",
            "coverageInventory": "additive",
        },
        "payloadSchema": browser_first_payload_schema(),
        "aliases": {
            "coverageInventory.items[].surface": "path",
            "coverageInventory.items[].summary": "title",
            "coverageInventory.items[].kind": "surfaceType",
            "coverageInventory.items[].status": "inventoryStatus",
            "coverageInventory.candidateUseCases[].id": "alias",
            "coverageInventory.candidateUseCases[].title": "behavior",
            "coverageInventory.candidateUseCases[].expectedOutcome": "rationale",
            "coverageInventory.candidateUseCases[].sideEffects.class": "sideEffectClass",
            "productSignals[].inventoryReferences": "inventoryItemRefs",
            "candidateUseCases": "coverageInventory.candidateUseCases",
        },
        "example": browser_first_payload_example(),
    }


def browser_first_payload_schema() -> dict[str, Any]:
    string = {"type": "string", "minLength": 1}
    string_list = {"type": "array", "items": {"type": "string"}}
    runtime_requirement = {
        "oneOf": [
            string,
            {
                "type": "object",
                "additionalProperties": False,
                "required": ["name"],
                "properties": {
                    "name": string,
                    "kind": {
                        "enum": [
                            "parameter",
                            "credential",
                            "precondition-input",
                        ]
                    },
                    "required": {"type": "boolean"},
                    "description": {"type": "string"},
                    "source": {
                        "enum": [
                            "prompt",
                            "environment",
                            "local-config",
                            "default",
                            "generated",
                            "named-output",
                        ]
                    },
                    "envVar": {"type": ["string", "null"]},
                    "credentialGroup": {"type": ["string", "null"]},
                    "persistValue": {"type": "boolean"},
                    "template": {"type": ["string", "null"]},
                    "default": {"type": ["string", "null"]},
                    "value": {"type": ["string", "null"]},
                    "refreshOnRerunAfterCommit": {"type": "boolean"},
                    "references": string_list,
                },
            },
        ]
    }
    refresh_impact = {
        "type": "object",
        "additionalProperties": False,
        "required": ["alias", "status"],
        "properties": {
            "alias": string,
            "status": {"enum": ["unaffected", "affected", "unknown"]},
            "reason": {"type": "string"},
            "affectedAreas": string_list,
            "recommendedAction": {"type": "string"},
            "generatedAt": {"type": ["string", "null"]},
            "schemaVersion": {"type": "string"},
        },
    }
    inventory_pass = {
        "type": "object",
        "additionalProperties": False,
        "required": ["scope", "startedAt", "status"],
        "properties": {
            "scope": string,
            "startedAt": string,
            "completedAt": {"type": ["string", "null"]},
            "coveredAreas": string_list,
            "uncoveredAreas": string_list,
            "sourceFilesVisited": {"type": "integer", "minimum": 0},
            "status": {"enum": ["complete", "partial", "interrupted"]},
        },
    }
    inventory_item = {
        "type": "object",
        "additionalProperties": False,
        "required": ["id", "surfaceType", "path", "title"],
        "properties": {
            "id": string,
            "surfaceType": string,
            "path": string,
            "title": string,
            "sourceRefs": string_list,
            "userFacing": {"type": "boolean"},
            "inventoryStatus": {
                "enum": ["covered", "excluded", "stale", "uncovered"]
            },
            "exclusionReason": {"type": "string"},
            "candidateUseCaseRefs": string_list,
            "priority": {"enum": ["critical", "high", "medium", "low"]},
            "productSignalRefs": string_list,
            "provenance": {"enum": sorted(_PROVENANCE_VALUES)},
        },
    }
    candidate = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "alias",
            "surface",
            "behavior",
            "sourceInventoryItems",
            "rationale",
            "sideEffectClass",
            "groundingStatus",
        ],
        "properties": {
            "alias": string,
            "surface": string,
            "behavior": string,
            "sourceInventoryItems": string_list,
            "rationale": string,
            "confidence": {"enum": sorted(_CONFIDENCE_VALUES)},
            "inventorySourceStatus": {
                "enum": ["complete", "partial", "stale"]
            },
            "priority": {"enum": ["critical", "high", "medium", "low"]},
            "requiresEnvironment": {"type": "boolean"},
            "knownRuntimeRequirements": string_list,
            "productSignalRefs": string_list,
            "provenance": {"enum": sorted(_PROVENANCE_VALUES)},
            "sideEffectClass": {"enum": sorted(_SIDE_EFFECT_VALUES)},
            "groundingStatus": {"enum": sorted(_GROUNDING_STATUS_VALUES)},
            "proofStatus": {
                "enum": [
                    "not-selected",
                    "selected",
                    "blocked",
                    "passed",
                    "failed",
                ]
            },
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "understandingMode",
            "productSummary",
            "targetEnvironment",
            "explorationScope",
            "productSignals",
            "coverageInventory",
        ],
        "properties": {
            "understandingMode": {"enum": ["browser-first", "hybrid"]},
            "productSummary": string,
            "targetEnvironment": {
                "type": "object",
                "additionalProperties": False,
                "required": ["kind", "locator", "reachabilityStatus", "observedAt"],
                "properties": {
                    "kind": {"enum": ["live-url"]},
                    "locator": string,
                    "origin": string,
                    "environment": {"type": "string"},
                    "reachabilityStatus": {
                        "enum": [
                            "reachable",
                            "unreachable",
                            "authentication-required",
                            "unknown",
                        ]
                    },
                    "observedAt": string,
                    "allowedOrigins": string_list,
                },
            },
            "explorationScope": {
                "type": "object",
                "additionalProperties": False,
                "required": ["status"],
                "properties": {
                    "allowedOrigins": string_list,
                    "maxPagesOrStates": {"type": "integer"},
                    "maxDepth": {"type": "integer"},
                    "candidateRange": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["minimum", "maximum"],
                        "properties": {
                            "minimum": {"type": "integer"},
                            "maximum": {"type": "integer"},
                        },
                    },
                    "softTimeBudgetMinutes": {"type": "integer"},
                    "readSafeOnly": {"const": True},
                    "excludedActions": string_list,
                    "status": {"enum": sorted(_SCOPE_STATUS_VALUES)},
                    "stopReason": {"type": "string"},
                    "partialInventoryReasons": string_list,
                },
            },
            "productSignals": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "id",
                        "kind",
                        "surface",
                        "summary",
                        "evidence",
                        "provenance",
                        "observedAt",
                        "confidence",
                    ],
                    "properties": {
                        "id": string,
                        "kind": {"enum": sorted(_SIGNAL_KINDS)},
                        "surface": string,
                        "state": {"type": "string"},
                        "summary": string,
                        "evidence": string_list,
                        "provenance": {"enum": sorted(_PROVENANCE_VALUES)},
                        "observedAt": string,
                        "confidence": {"enum": sorted(_CONFIDENCE_VALUES)},
                        "inventoryItemRefs": string_list,
                        "fromSurface": string,
                        "toSurface": string,
                    },
                },
            },
            "coverageInventory": {
                "type": "object",
                "additionalProperties": False,
                "required": ["status", "items", "candidateUseCases"],
                "properties": {
                    "status": {"enum": ["complete", "partial", "stale"]},
                    "generatedAt": string,
                    "generatedGitHash": {"type": ["string", "null"]},
                    "gitAvailable": {"type": "boolean"},
                    "sourceFilesVisited": {"type": "integer"},
                    "sourceTraceabilityStatus": {
                        "enum": ["complete", "normalized", "missing"]
                    },
                    "partialInventoryReasons": string_list,
                    "passes": {"type": "array", "items": inventory_pass},
                    "items": {"type": "array", "items": inventory_item},
                    "candidateUseCases": {
                        "type": "array",
                        "items": candidate,
                    },
                    "uncoveredAreas": string_list,
                    "staleAreas": string_list,
                },
            },
            "workspaceKind": {
                "enum": ["repository", "engagement", "hybrid"]
            },
            "repositorySummary": {"type": "string"},
            "localStartInstructions": {"type": "string"},
            "gaps": string_list,
            "provenanceTraceabilityStatus": {
                "enum": ["complete", "partial", "conflicted"]
            },
            "observedAt": string,
            "generatedGitHash": {"type": ["string", "null"]},
            "gitAvailable": {"type": "boolean"},
            "gitUnavailableReason": {"type": "string"},
            "gitBranch": {"type": "string"},
            "safeInspectionPaths": string_list,
            "blockedSensitivePaths": string_list,
            "validationGoals": string_list,
            "knownRuntimeRequirements": {
                "type": "array",
                "items": runtime_requirement,
            },
            "sourceFilesVisited": {
                "type": "integer",
                "minimum": 0,
            },
            "partialInventoryReasons": string_list,
            "refreshImpacts": {
                "type": "array",
                "items": refresh_impact,
            },
        },
    }


def browser_first_payload_example() -> dict[str, Any]:
    observed_at = "2026-07-26T18:00:00Z"
    return {
        "understandingMode": "browser-first",
        "productSummary": "A project tracking application.",
        "targetEnvironment": {
            "kind": "live-url",
            "locator": "https://app.example.test/projects",
            "reachabilityStatus": "authentication-required",
            "observedAt": observed_at,
        },
        "explorationScope": {
            "allowedOrigins": ["https://app.example.test"],
            "status": "partial",
            "partialInventoryReasons": [
                "Only one read-safe journey was observed."
            ],
        },
        "productSignals": [
            {
                "id": "projects-list",
                "kind": "surface",
                "surface": "/projects",
                "summary": "The signed-in user can view projects.",
                "evidence": ["A Projects heading was visible."],
                "provenance": "browser",
                "observedAt": observed_at,
                "confidence": "high",
                "inventoryItemRefs": ["surface-projects"],
            },
            {
                "id": "authenticated-session",
                "kind": "runtime-requirement",
                "surface": "/sign-in",
                "summary": "The surface requires an authenticated session.",
                "evidence": ["The user completed sign-in in the headed browser."],
                "provenance": "browser",
                "observedAt": observed_at,
                "confidence": "high",
                "inventoryItemRefs": [],
            },
        ],
        "coverageInventory": {
            "status": "partial",
            "generatedAt": observed_at,
            "gitAvailable": False,
            "sourceFilesVisited": 0,
            "sourceTraceabilityStatus": "missing",
            "partialInventoryReasons": [
                "Only one read-safe journey was observed."
            ],
            "items": [
                {
                    "id": "surface-projects",
                    "surfaceType": "route",
                    "path": "/projects",
                    "title": "Projects",
                    "sourceRefs": [],
                    "inventoryStatus": "covered",
                    "priority": "high",
                    "productSignalRefs": ["projects-list"],
                    "provenance": "browser",
                }
            ],
            "candidateUseCases": [
                {
                    "alias": "projects-list",
                    "surface": "/projects",
                    "behavior": "Show the signed-in user's projects.",
                    "sourceInventoryItems": ["surface-projects"],
                    "rationale": "Stable user-visible behavior.",
                    "confidence": "high",
                    "priority": "high",
                    "requiresEnvironment": True,
                    "knownRuntimeRequirements": [
                        "baseUrl",
                        "authenticated session",
                    ],
                    "productSignalRefs": [
                        "projects-list",
                        "authenticated-session",
                    ],
                    "provenance": "browser",
                    "sideEffectClass": "none",
                    "groundingStatus": "authentication-required",
                }
            ],
        },
        "gaps": ["Only one read-safe journey was observed."],
    }


def _normalize_browser_compatibility_fields(
    payload: dict[str, Any],
) -> None:
    for field in (
        "repositorySummary",
        "localStartInstructions",
        "gitUnavailableReason",
        "gitBranch",
    ):
        if field in payload and not isinstance(payload[field], str):
            raise ValueError(f"payload.{field} must be a string.")

    for field in (
        "safeInspectionPaths",
        "blockedSensitivePaths",
        "validationGoals",
        "partialInventoryReasons",
    ):
        if field in payload:
            payload[field] = _string_list(
                payload[field], f"payload.{field}"
            )

    workspace_kind = payload.get("workspaceKind")
    if workspace_kind is not None and workspace_kind not in {
        "repository",
        "engagement",
        "hybrid",
    }:
        raise ValueError("payload.workspaceKind is invalid.")

    provenance_status = payload.get("provenanceTraceabilityStatus")
    if provenance_status is not None and provenance_status not in {
        "complete",
        "partial",
        "conflicted",
    }:
        raise ValueError(
            "payload.provenanceTraceabilityStatus is invalid."
        )

    if "gitAvailable" in payload and not isinstance(
        payload["gitAvailable"], bool
    ):
        raise ValueError("payload.gitAvailable must be a boolean.")
    if "generatedGitHash" in payload and payload["generatedGitHash"] is not None:
        if not isinstance(payload["generatedGitHash"], str):
            raise ValueError(
                "payload.generatedGitHash must be a string or null."
            )
    if "sourceFilesVisited" in payload:
        payload["sourceFilesVisited"] = _nonnegative_int(
            payload["sourceFilesVisited"], "payload.sourceFilesVisited"
        )

    requirements = payload.get("knownRuntimeRequirements")
    if requirements is not None:
        if not isinstance(requirements, list):
            raise ValueError(
                "payload.knownRuntimeRequirements must be a list."
            )
        normalized_requirements: list[Any] = []
        for index, requirement in enumerate(requirements):
            path = f"payload.knownRuntimeRequirements[{index}]"
            if isinstance(requirement, str):
                if not requirement.strip():
                    raise ValueError(f"{path} must not be empty.")
                normalized_requirements.append(requirement.strip())
                continue
            if not isinstance(requirement, dict):
                raise ValueError(
                    f"{path} must be a string or an object."
                )
            normalized_requirement = dict(requirement)
            _reject_unknown_fields(
                normalized_requirement,
                _RUNTIME_REQUIREMENT_FIELDS,
                path,
            )
            _require_nonempty(normalized_requirement, "name", path)
            if "references" in normalized_requirement:
                normalized_requirement["references"] = _string_list(
                    normalized_requirement["references"],
                    f"{path}.references",
                )
            normalized_requirements.append(normalized_requirement)
        payload["knownRuntimeRequirements"] = normalized_requirements

    refresh_impacts = payload.get("refreshImpacts")
    if refresh_impacts is not None:
        if not isinstance(refresh_impacts, list):
            raise ValueError("payload.refreshImpacts must be a list.")
        normalized_impacts: list[dict[str, Any]] = []
        for index, impact in enumerate(refresh_impacts):
            path = f"refreshImpacts[{index}]"
            if not isinstance(impact, dict):
                raise ValueError(f"{path} must be an object.")
            normalized_impact = dict(impact)
            _reject_unknown_fields(
                normalized_impact, _REFRESH_IMPACT_FIELDS, path
            )
            _require_nonempty(normalized_impact, "alias", path)
            status = str(
                _require_nonempty(normalized_impact, "status", path)
            ).strip()
            if status not in {"unaffected", "affected", "unknown"}:
                raise ValueError(f"{path}.status is invalid.")
            normalized_impact["status"] = status
            if "affectedAreas" in normalized_impact:
                normalized_impact["affectedAreas"] = _string_list(
                    normalized_impact["affectedAreas"],
                    f"{path}.affectedAreas",
                )
            if normalized_impact.get("generatedAt"):
                normalized_impact["generatedAt"] = _normalize_timestamp(
                    normalized_impact["generatedAt"],
                    f"{path}.generatedAt",
                )
            normalized_impacts.append(normalized_impact)
        payload["refreshImpacts"] = normalized_impacts


def _normalize_browser_aliases(
    payload: dict[str, Any], *, mode: str
) -> dict[str, Any]:
    normalized = deepcopy(payload)
    if "mode" in normalized:
        alias_mode = normalize_understanding_mode(normalized.pop("mode"))
        canonical_mode = normalize_understanding_mode(
            normalized.get("understandingMode") or alias_mode
        )
        if canonical_mode != alias_mode:
            raise ValueError(
                "payload.mode conflicts with payload.understandingMode."
            )
        normalized["understandingMode"] = canonical_mode
    else:
        normalized["understandingMode"] = mode

    _move_alias(
        normalized,
        "localStartInstructions",
        "startInstructions",
        "payload",
    )
    _move_alias(
        normalized,
        "safeInspectionPaths",
        "safePaths",
        "payload",
    )
    for alias in ("gitHash", "commitHash", "generatedCommitHash"):
        _move_alias(
            normalized,
            "generatedGitHash",
            alias,
            "payload",
        )

    git = normalized.pop("git", None)
    if git is not None:
        if not isinstance(git, dict):
            raise ValueError("payload.git must be an object.")
        _reject_unknown_fields(
            git, {"hash", "sha", "commit", "available", "branch"}, "payload.git"
        )
        git_hash = git.get("hash") or git.get("sha") or git.get("commit")
        if git_hash:
            _set_canonical_value(
                normalized,
                "generatedGitHash",
                git_hash,
                "payload.git",
            )
        if "available" in git:
            _set_canonical_value(
                normalized,
                "gitAvailable",
                bool(git["available"]),
                "payload.git",
            )
        if git.get("branch"):
            _set_canonical_value(
                normalized,
                "gitBranch",
                git["branch"],
                "payload.git",
            )

    target_aliases = [
        normalized.pop(key)
        for key in ("targetUrl", "url")
        if key in normalized
    ]
    if target_aliases:
        if len({str(item) for item in target_aliases}) > 1:
            raise ValueError(
                "payload.targetUrl conflicts with payload.url."
            )
        target = normalized.get("targetEnvironment")
        if isinstance(target, str):
            target = {"locator": target}
        elif target is None:
            target = {}
        elif not isinstance(target, dict):
            raise ValueError("payload.targetEnvironment must be an object.")
        target = dict(target)
        _set_canonical_value(
            target,
            "locator",
            target_aliases[0],
            "payload.targetEnvironment",
        )
        normalized["targetEnvironment"] = target

    inventory = normalized.get("coverageInventory")
    if not isinstance(inventory, dict):
        return normalized
    inventory = deepcopy(inventory)
    top_level_candidates = normalized.pop("candidateUseCases", None)
    if top_level_candidates is not None:
        _set_canonical_value(
            inventory,
            "candidateUseCases",
            top_level_candidates,
            "payload.candidateUseCases",
        )

    items = inventory.get("items")
    if isinstance(items, list):
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            path = f"coverageInventory.items[{index}]"
            _move_alias(item, "path", "surface", path)
            _move_alias(item, "title", "summary", path)
            _move_alias(item, "surfaceType", "kind", path)
            _move_alias(item, "inventoryStatus", "status", path)

    candidates = inventory.get("candidateUseCases")
    if isinstance(candidates, list):
        for index, candidate in enumerate(candidates):
            if not isinstance(candidate, dict):
                continue
            path = f"coverageInventory.candidateUseCases[{index}]"
            _move_alias(candidate, "alias", "id", path)
            _move_alias(candidate, "behavior", "title", path)
            _move_alias(candidate, "rationale", "expectedOutcome", path)
            side_effects = candidate.pop("sideEffects", None)
            if side_effects is not None:
                if not isinstance(side_effects, dict):
                    raise ValueError(f"{path}.sideEffects must be an object.")
                _reject_unknown_fields(
                    side_effects, {"class"}, f"{path}.sideEffects"
                )
                if "class" not in side_effects:
                    raise ValueError(
                        f"{path}.sideEffects.class is required."
                    )
                _set_canonical_value(
                    candidate,
                    "sideEffectClass",
                    side_effects["class"],
                    f"{path}.sideEffects.class",
                )

    signals = normalized.get("productSignals")
    if isinstance(signals, list):
        for index, signal in enumerate(signals):
            if not isinstance(signal, dict):
                continue
            _move_alias(
                signal,
                "inventoryItemRefs",
                "inventoryReferences",
                f"productSignals[{index}]",
            )

    normalized["coverageInventory"] = inventory
    return normalized


def _move_alias(
    data: dict[str, Any],
    canonical: str,
    alias: str,
    path: str,
) -> None:
    if alias not in data:
        return
    alias_value = data.pop(alias)
    _set_canonical_value(data, canonical, alias_value, f"{path}.{alias}")


def _set_canonical_value(
    data: dict[str, Any],
    canonical: str,
    value: Any,
    alias_path: str,
) -> None:
    if canonical in data and data[canonical] != value:
        canonical_path = alias_path.rsplit(".", 1)[0]
        raise ValueError(
            f"{canonical_path}.{canonical} conflicts with {alias_path}."
        )
    data[canonical] = value


def _reject_unknown_fields(
    data: dict[str, Any], allowed: set[str], path: str
) -> None:
    unknown = [str(key) for key in data if key not in allowed]
    if unknown:
        raise ValueError(
            f"{path}.{unknown[0]} is not part of the public browser-first "
            "understanding contract."
        )


def _require_nonempty(data: dict[str, Any], field: str, path: str) -> Any:
    value = data.get(field)
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ValueError(f"{path}.{field} is required.")
    return value


def _string_list(
    value: Any,
    path: str,
    *,
    required: bool = False,
) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{path} must be a list.")
    result = [str(item).strip() for item in value if str(item).strip()]
    if required and not result:
        raise ValueError(f"{path} requires at least one value.")
    return result


def _normalize_target_environment(payload: dict[str, Any]) -> dict[str, Any]:
    source = payload.get("targetEnvironment")
    if isinstance(source, str):
        source = {"locator": source}
    if not isinstance(source, dict):
        source = {}
    _reject_unknown_fields(source, _TARGET_FIELDS, "targetEnvironment")
    locator = (
        source.get("locator")
        or source.get("url")
        or payload.get("targetUrl")
        or payload.get("url")
    )
    sanitized = sanitize_browser_url(locator)
    origin = browser_origin(sanitized)
    observed_at = _normalize_timestamp(
        source.get("observedAt")
        or payload.get("observedAt")
        or (payload.get("coverageInventory") or {}).get("generatedAt"),
        "targetEnvironment.observedAt",
    )
    requested_origins = source.get("allowedOrigins")
    if not isinstance(requested_origins, list) or not requested_origins:
        requested_origins = [origin]
    allowed_origins = _normalize_origins(requested_origins)
    if origin not in allowed_origins:
        raise ValueError(
            "targetEnvironment.allowedOrigins must include the target origin."
        )
    reachability = str(
        source.get("reachabilityStatus") or "unknown"
    ).strip()
    if reachability not in {
        "reachable",
        "unreachable",
        "authentication-required",
        "unknown",
    }:
        raise ValueError(
            "targetEnvironment.reachabilityStatus is invalid; allowed "
            "values: reachable, unreachable, authentication-required, "
            "unknown."
        )
    target: dict[str, Any] = {
        "kind": "live-url",
        "locator": sanitized,
        "origin": origin,
    }
    environment = str(source.get("environment") or "").strip()
    if environment:
        target["environment"] = environment
    target.update(
        {
            "reachabilityStatus": reachability,
            "observedAt": observed_at,
            "allowedOrigins": allowed_origins,
        }
    )
    return target


def _normalize_exploration_scope(
    value: Any, target_origins: list[str]
) -> dict[str, Any]:
    source = dict(value) if isinstance(value, dict) else {}
    _reject_unknown_fields(source, _SCOPE_FIELDS, "explorationScope")
    requested_origins = source.get("allowedOrigins")
    allowed_origins = (
        _normalize_origins(requested_origins)
        if isinstance(requested_origins, list) and requested_origins
        else list(target_origins)
    )
    if not set(target_origins).issubset(allowed_origins):
        raise ValueError(
            "explorationScope.allowedOrigins must include the target origin."
        )

    max_pages = _bounded_int(
        source.get("maxPagesOrStates", DEFAULT_EXPLORATION_SCOPE["maxPagesOrStates"]),
        "explorationScope.maxPagesOrStates",
        minimum=1,
        maximum=100,
    )
    max_depth = _bounded_int(
        source.get("maxDepth", DEFAULT_EXPLORATION_SCOPE["maxDepth"]),
        "explorationScope.maxDepth",
        minimum=0,
        maximum=10,
    )
    budget = _bounded_int(
        source.get(
            "softTimeBudgetMinutes",
            DEFAULT_EXPLORATION_SCOPE["softTimeBudgetMinutes"],
        ),
        "explorationScope.softTimeBudgetMinutes",
        minimum=1,
        maximum=60,
    )
    candidate_range = source.get("candidateRange")
    if not isinstance(candidate_range, dict):
        candidate_range = DEFAULT_EXPLORATION_SCOPE["candidateRange"]
    candidate_minimum = _bounded_int(
        candidate_range.get("minimum", 3),
        "explorationScope.candidateRange.minimum",
        minimum=1,
        maximum=10,
    )
    candidate_maximum = _bounded_int(
        candidate_range.get("maximum", 5),
        "explorationScope.candidateRange.maximum",
        minimum=1,
        maximum=10,
    )
    if candidate_minimum > candidate_maximum:
        raise ValueError(
            "explorationScope candidate minimum cannot exceed maximum."
        )
    read_safe_only = source.get("readSafeOnly", True)
    if read_safe_only is not True:
        raise ValueError(
            "explorationScope.readSafeOnly must remain true during mapping."
        )
    status = str(source.get("status") or "partial").strip()
    if status not in _SCOPE_STATUS_VALUES:
        raise ValueError(
            "explorationScope.status must be complete, partial, or blocked."
        )
    excluded = source.get(
        "excludedActions", DEFAULT_EXPLORATION_SCOPE["excludedActions"]
    )
    if not isinstance(excluded, list):
        raise ValueError(
            "explorationScope.excludedActions must be a list."
        )
    reasons = _normalize_gaps(
        source.get("partialInventoryReasons") or []
    )
    normalized = {
        "allowedOrigins": allowed_origins,
        "maxPagesOrStates": max_pages,
        "maxDepth": max_depth,
        "candidateRange": {
            "minimum": candidate_minimum,
            "maximum": candidate_maximum,
        },
        "softTimeBudgetMinutes": budget,
        "readSafeOnly": True,
        "excludedActions": [str(item).strip() for item in excluded if str(item).strip()],
        "status": status,
        "partialInventoryReasons": reasons,
    }
    stop_reason = str(source.get("stopReason") or "").strip()
    if stop_reason:
        normalized["stopReason"] = stop_reason
    return normalized


def _normalize_product_signals(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise ValueError(
            "Browser-first understanding requires at least one productSignals item."
        )
    signals: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, source in enumerate(value):
        if not isinstance(source, dict):
            raise ValueError(f"productSignals[{index}] must be an object.")
        source = dict(source)
        _reject_unknown_fields(
            source, _SIGNAL_FIELDS, f"productSignals[{index}]"
        )
        signal_id = str(source.get("id") or "").strip()
        if not _SIGNAL_ID.fullmatch(signal_id):
            raise ValueError(
                f"productSignals[{index}].id must be a stable lowercase slug."
            )
        if signal_id in seen:
            raise ValueError(f"Duplicate product signal id: {signal_id}.")
        seen.add(signal_id)
        kind = str(source.get("kind") or "").strip()
        if kind not in _SIGNAL_KINDS:
            raise ValueError(
                f"productSignals[{index}].kind is invalid; allowed values: "
                "surface, state, transition, runtime-requirement, gap."
            )
        surface = _sanitize_surface(source.get("surface"))
        summary = str(source.get("summary") or "").strip()
        if not surface or not summary:
            raise ValueError(
                f"productSignals[{index}] requires surface and summary."
            )
        for field in ("evidence", "provenance", "observedAt", "confidence"):
            if field not in source:
                raise ValueError(
                    f"productSignals[{index}].{field} is required."
                )
        provenance = str(source.get("provenance") or "").strip()
        if provenance not in _PROVENANCE_VALUES:
            raise ValueError(
                f"productSignals[{index}].provenance is invalid."
            )
        confidence = str(source.get("confidence") or "").strip()
        if confidence not in _CONFIDENCE_VALUES:
            raise ValueError(
                f"productSignals[{index}].confidence is invalid."
            )
        evidence = source.get("evidence")
        if not isinstance(evidence, list):
            raise ValueError(
                f"productSignals[{index}].evidence must be a list."
            )
        signal: dict[str, Any] = {
            "id": signal_id,
            "kind": kind,
            "surface": surface,
        }
        state = str(source.get("state") or "").strip()
        if state:
            signal["state"] = state
        signal.update(
            {
                "summary": summary,
                "evidence": [
                    str(item).strip()
                    for item in evidence
                    if str(item).strip()
                ],
                "provenance": provenance,
                "observedAt": _normalize_timestamp(
                    source.get("observedAt"),
                    f"productSignals[{index}].observedAt",
                ),
                "confidence": confidence,
            }
        )
        refs = source.get("inventoryItemRefs") or []
        if not isinstance(refs, list):
            raise ValueError(
                f"productSignals[{index}].inventoryItemRefs must be a list."
            )
        if refs:
            signal["inventoryItemRefs"] = [
                str(item).strip() for item in refs if str(item).strip()
            ]
        for field in ("fromSurface", "toSurface"):
            if field in source:
                surface_value = _sanitize_surface(source.get(field))
                if not surface_value:
                    raise ValueError(
                        f"productSignals[{index}].{field} is required when supplied."
                    )
                signal[field] = surface_value
        if kind == "transition":
            for field in ("fromSurface", "toSurface"):
                if field not in signal:
                    raise ValueError(
                        f"productSignals[{index}].{field} is required for a transition signal."
                    )
        signals.append(signal)
    return signals


def _normalize_browser_inventory(
    value: Any, *, mode: str
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(
            "Browser-first understanding requires coverageInventory."
        )
    inventory = deepcopy(value)
    _reject_unknown_fields(
        inventory, _INVENTORY_FIELDS, "coverageInventory"
    )
    items = inventory.get("items")
    candidates = inventory.get("candidateUseCases")
    if not isinstance(items, list) or not isinstance(candidates, list):
        raise ValueError(
            "coverageInventory requires items and candidateUseCases lists."
        )
    normalized_items: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError("coverageInventory.items must contain objects.")
        normalized_item = dict(item)
        path = f"coverageInventory.items[{index}]"
        _reject_unknown_fields(
            normalized_item, _INVENTORY_ITEM_FIELDS, path
        )
        for field in ("id", "surfaceType", "path", "title"):
            _require_nonempty(normalized_item, field, path)
        normalized_item["path"] = _sanitize_surface(
            normalized_item.get("path")
        )
        normalized_item["sourceRefs"] = _string_list(
            normalized_item.get("sourceRefs", []), f"{path}.sourceRefs"
        )
        normalized_item["candidateUseCaseRefs"] = _string_list(
            normalized_item.get("candidateUseCaseRefs", []),
            f"{path}.candidateUseCaseRefs",
        )
        normalized_item["productSignalRefs"] = _string_list(
            normalized_item.get("productSignalRefs", []),
            f"{path}.productSignalRefs",
        )
        inventory_status = normalized_item.get(
            "inventoryStatus", "covered"
        )
        if inventory_status not in {
            "covered",
            "excluded",
            "stale",
            "uncovered",
        }:
            raise ValueError(f"{path}.inventoryStatus is invalid.")
        normalized_item["inventoryStatus"] = inventory_status
        priority = normalized_item.get("priority", "medium")
        if priority not in {"critical", "high", "medium", "low"}:
            raise ValueError(f"{path}.priority is invalid.")
        normalized_item["priority"] = priority
        provenance = normalized_item.get("provenance", "browser")
        if provenance not in _PROVENANCE_VALUES:
            raise ValueError(f"{path}.provenance is invalid.")
        normalized_item["provenance"] = provenance
        if "userFacing" in normalized_item and not isinstance(
            normalized_item["userFacing"], bool
        ):
            raise ValueError(f"{path}.userFacing must be a boolean.")
        normalized_item.setdefault("provenance", "browser")
        normalized_items.append(normalized_item)
    normalized_candidates: list[dict[str, Any]] = []
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            raise ValueError(
                "coverageInventory.candidateUseCases must contain objects."
            )
        normalized_candidate = dict(candidate)
        path = f"coverageInventory.candidateUseCases[{index}]"
        _reject_unknown_fields(
            normalized_candidate, _CANDIDATE_FIELDS, path
        )
        for field in (
            "alias",
            "surface",
            "behavior",
            "rationale",
            "sideEffectClass",
            "groundingStatus",
        ):
            _require_nonempty(normalized_candidate, field, path)
        normalized_candidate["surface"] = _sanitize_journey_surface(
            normalized_candidate.get("surface")
        )
        normalized_candidate["sourceInventoryItems"] = _string_list(
            normalized_candidate.get("sourceInventoryItems"),
            f"{path}.sourceInventoryItems",
            required=True,
        )
        normalized_candidate["knownRuntimeRequirements"] = _string_list(
            normalized_candidate.get("knownRuntimeRequirements", []),
            f"{path}.knownRuntimeRequirements",
        )
        normalized_candidate["productSignalRefs"] = _string_list(
            normalized_candidate.get("productSignalRefs"),
            f"{path}.productSignalRefs",
            required=True,
        )
        side_effect = str(normalized_candidate["sideEffectClass"]).strip()
        if side_effect not in _SIDE_EFFECT_VALUES:
            raise ValueError(f"{path}.sideEffectClass is invalid.")
        normalized_candidate["sideEffectClass"] = side_effect
        grounding = str(normalized_candidate["groundingStatus"]).strip()
        if grounding not in _GROUNDING_STATUS_VALUES:
            raise ValueError(f"{path}.groundingStatus is invalid.")
        normalized_candidate["groundingStatus"] = grounding
        confidence = str(
            normalized_candidate.get("confidence") or "medium"
        ).strip()
        if confidence not in _CONFIDENCE_VALUES:
            raise ValueError(f"{path}.confidence is invalid.")
        normalized_candidate["confidence"] = confidence
        inventory_source_status = normalized_candidate.get(
            "inventorySourceStatus", inventory.get("status", "partial")
        )
        if inventory_source_status not in {
            "complete",
            "partial",
            "stale",
        }:
            raise ValueError(f"{path}.inventorySourceStatus is invalid.")
        normalized_candidate["inventorySourceStatus"] = (
            inventory_source_status
        )
        priority = normalized_candidate.get("priority", "medium")
        if priority not in {"critical", "high", "medium", "low"}:
            raise ValueError(f"{path}.priority is invalid.")
        normalized_candidate["priority"] = priority
        if "requiresEnvironment" in normalized_candidate and not isinstance(
            normalized_candidate["requiresEnvironment"], bool
        ):
            raise ValueError(
                f"{path}.requiresEnvironment must be a boolean."
            )
        provenance = normalized_candidate.get("provenance", "browser")
        if provenance not in _PROVENANCE_VALUES:
            raise ValueError(f"{path}.provenance is invalid.")
        normalized_candidate["provenance"] = provenance
        proof_status = normalized_candidate.get("proofStatus")
        if proof_status is not None and proof_status not in {
            "not-selected",
            "selected",
            "blocked",
            "passed",
            "failed",
        }:
            raise ValueError(f"{path}.proofStatus is invalid.")
        normalized_candidates.append(normalized_candidate)
    passes = inventory.get("passes", [])
    if not isinstance(passes, list):
        raise ValueError("coverageInventory.passes must be a list.")
    normalized_passes: list[dict[str, Any]] = []
    for index, inventory_pass in enumerate(passes):
        if not isinstance(inventory_pass, dict):
            raise ValueError(
                f"coverageInventory.passes[{index}] must be an object."
            )
        normalized_pass = dict(inventory_pass)
        path = f"coverageInventory.passes[{index}]"
        _reject_unknown_fields(
            normalized_pass,
            _PASS_FIELDS,
            path,
        )
        for field in ("scope", "startedAt", "status"):
            _require_nonempty(normalized_pass, field, path)
        if normalized_pass["status"] not in {
            "complete",
            "partial",
            "interrupted",
        }:
            raise ValueError(f"{path}.status is invalid.")
        for field in ("coveredAreas", "uncoveredAreas"):
            normalized_pass[field] = _string_list(
                normalized_pass.get(field, []), f"{path}.{field}"
            )
        normalized_pass["sourceFilesVisited"] = _nonnegative_int(
            normalized_pass.get("sourceFilesVisited", 0),
            f"{path}.sourceFilesVisited",
        )
        normalized_passes.append(normalized_pass)
    if "status" not in inventory:
        raise ValueError("coverageInventory.status is required.")
    status = str(inventory.get("status") or "")
    if status not in {"complete", "partial", "stale"}:
        raise ValueError(
            "coverageInventory.status must be complete, partial, or stale."
        )
    inventory.update(
        {
            "status": status,
            "partialInventoryReasons": _normalize_gaps(
                inventory.get("partialInventoryReasons") or [],
                path="coverageInventory.partialInventoryReasons",
            ),
            "passes": normalized_passes,
            "items": normalized_items,
            "candidateUseCases": normalized_candidates,
        }
    )
    if mode == "browser-first":
        inventory.update(
            {
                "gitAvailable": False,
                "generatedGitHash": None,
                "sourceFilesVisited": 0,
                "sourceTraceabilityStatus": "missing",
            }
        )
    else:
        inventory["gitAvailable"] = bool(
            inventory.get("generatedGitHash")
            or inventory.get("gitAvailable")
        )
        inventory["sourceFilesVisited"] = int(
            inventory.get("sourceFilesVisited", 0) or 0
        )
        inventory.setdefault("sourceTraceabilityStatus", "missing")
    return inventory


def _validate_browser_references(
    signals: list[dict[str, Any]], inventory: dict[str, Any]
) -> None:
    signal_ids = [str(item.get("id") or "") for item in signals]
    item_ids = [
        str(item.get("id") or "") for item in inventory.get("items", [])
    ]
    candidates = inventory.get("candidateUseCases", [])
    candidate_aliases = [
        str(item.get("alias") or "") for item in candidates
    ]
    _reject_duplicate_ids(signal_ids, "productSignals")
    _reject_duplicate_ids(item_ids, "coverageInventory.items")
    _reject_duplicate_ids(
        candidate_aliases, "coverageInventory.candidateUseCases"
    )
    signal_set = set(signal_ids)
    signals_by_id = {
        str(item.get("id") or ""): item for item in signals
    }
    item_set = set(item_ids)
    candidate_set = set(candidate_aliases)
    for index, signal in enumerate(signals):
        _require_known_references(
            signal.get("inventoryItemRefs", []),
            item_set,
            f"productSignals[{index}].inventoryItemRefs",
        )
    for index, item in enumerate(inventory.get("items", [])):
        _require_known_references(
            item.get("productSignalRefs", []),
            signal_set,
            f"coverageInventory.items[{index}].productSignalRefs",
        )
        _require_known_references(
            item.get("candidateUseCaseRefs", []),
            candidate_set,
            f"coverageInventory.items[{index}].candidateUseCaseRefs",
        )
    for index, candidate in enumerate(candidates):
        path = f"coverageInventory.candidateUseCases[{index}]"
        _require_known_references(
            candidate.get("sourceInventoryItems", []),
            item_set,
            f"{path}.sourceInventoryItems",
        )
        _require_known_references(
            candidate.get("productSignalRefs", []),
            signal_set,
            f"{path}.productSignalRefs",
        )
        referenced_signals = [
            signals_by_id[reference]
            for reference in candidate.get("productSignalRefs", [])
            if reference in signals_by_id
        ]
        grounding = str(candidate.get("groundingStatus") or "unknown")
        journey = str(candidate.get("surface") or "")
        if grounding == "observed" and " -> " in journey:
            source, destination = journey.split(" -> ", 1)
            matching_transition = any(
                signal.get("kind") == "transition"
                and signal.get("fromSurface") == source
                and signal.get("toSurface") == destination
                for signal in referenced_signals
            )
            if not matching_transition:
                raise ValueError(
                    f"{path}.groundingStatus cannot be observed without a "
                    "referenced matching transition signal."
                )
        if grounding == "authentication-required" and not any(
            signal.get("kind") in {"runtime-requirement", "gap"}
            for signal in referenced_signals
        ):
            raise ValueError(
                f"{path}.groundingStatus authentication-required needs a "
                "referenced runtime-requirement or gap signal."
            )


def _reject_duplicate_ids(values: list[str], path: str) -> None:
    seen: set[str] = set()
    for index, value in enumerate(values):
        if value in seen:
            raise ValueError(f"{path}[{index}] duplicates id '{value}'.")
        seen.add(value)


def _require_known_references(
    values: Any, known: set[str], path: str
) -> None:
    references = _string_list(values, path)
    missing = [value for value in references if value not in known]
    if missing:
        raise ValueError(
            f"{path} references unknown id '{missing[0]}'."
        )


def _normalize_origins(values: list[Any]) -> list[str]:
    origins: list[str] = []
    for value in values:
        origin = browser_origin(value)
        if origin not in origins:
            origins.append(origin)
    if not origins:
        raise ValueError("At least one allowed HTTP(S) origin is required.")
    return origins


def _sanitize_surface(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    parsed = urlsplit(raw)
    if parsed.scheme or parsed.netloc:
        sanitized = sanitize_browser_url(raw)
        return urlsplit(sanitized).path or "/"
    path = parsed.path or "/"
    return path if path.startswith("/") else f"/{path}"


def _sanitize_journey_surface(value: Any) -> str:
    raw = str(value or "").strip()
    if "->" not in raw:
        return _sanitize_surface(raw)
    surfaces = [_sanitize_surface(item) for item in raw.split("->")]
    if len(surfaces) != 2 or not all(surfaces):
        raise ValueError(
            "Candidate surface transitions must use '<from> -> <to>'."
        )
    return " -> ".join(surfaces)


def _normalize_timestamp(value: Any, field: str) -> str:
    timestamp = str(value or "").strip()
    if not timestamp:
        raise ValueError(f"{field} is required.")
    candidate = timestamp[:-1] + "+00:00" if timestamp.endswith("Z") else timestamp
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO-8601 timestamp.") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone.")
    return timestamp


def _normalize_gaps(value: Any, *, path: str = "gaps") -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{path} must be a list.")
    gaps: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str):
            raise ValueError(f"{path}[{index}] must be a string.")
        text = item.strip()
        if text and text not in gaps:
            gaps.append(text)
    return gaps


def _nonnegative_int(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be an integer.")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an integer.") from exc
    if number < 0:
        raise ValueError(f"{field} must be zero or greater.")
    return number


def _bounded_int(
    value: Any, field: str, *, minimum: int, maximum: int
) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be an integer.")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an integer.") from exc
    if number < minimum or number > maximum:
        raise ValueError(
            f"{field} must be between {minimum} and {maximum}."
        )
    return number


def _reject_forbidden_browser_fields(value: Any, path: str = "payload") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            token = re.sub(r"[^a-z0-9]", "", str(key).lower())
            canonical = _FORBIDDEN_BROWSER_FIELD_TOKENS.get(token)
            if canonical:
                raise ValueError(
                    f"Forbidden browser artifact field '{key}' at {path}.{key}; "
                    f"{canonical} must not be persisted."
                )
            _reject_forbidden_browser_fields(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_forbidden_browser_fields(item, f"{path}[{index}]")


def _append_unique(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)


def _provenance_status(
    mode: str, signals: list[dict[str, Any]], gaps: list[str]
) -> str:
    if mode == "hybrid" and any(
        "conflict" in gap.lower() for gap in gaps
    ):
        return "conflicted"
    expected = {"browser"} if mode == "browser-first" else {"browser", "repository", "hybrid"}
    observed = {str(item.get("provenance")) for item in signals}
    if not observed or not observed.issubset(expected):
        return "partial"
    return "partial" if gaps else "complete"
