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
    }


def _normalize_target_environment(payload: dict[str, Any]) -> dict[str, Any]:
    source = payload.get("targetEnvironment")
    if isinstance(source, str):
        source = {"locator": source}
    if not isinstance(source, dict):
        source = {}
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
            "targetEnvironment.reachabilityStatus is invalid."
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
    return {
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
                f"productSignals[{index}].kind is invalid."
            )
        surface = _sanitize_surface(source.get("surface"))
        summary = str(source.get("summary") or "").strip()
        if not surface or not summary:
            raise ValueError(
                f"productSignals[{index}] requires surface and summary."
            )
        provenance = str(source.get("provenance") or "browser").strip()
        if provenance not in _PROVENANCE_VALUES:
            raise ValueError(
                f"productSignals[{index}].provenance is invalid."
            )
        confidence = str(source.get("confidence") or "medium").strip()
        if confidence not in _CONFIDENCE_VALUES:
            raise ValueError(
                f"productSignals[{index}].confidence is invalid."
            )
        evidence = source.get("evidence") or []
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
    items = inventory.get("items")
    candidates = inventory.get("candidateUseCases")
    if not isinstance(items, list) or not isinstance(candidates, list):
        raise ValueError(
            "coverageInventory requires items and candidateUseCases lists."
        )
    normalized_items: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("coverageInventory.items must contain objects.")
        normalized_item = dict(item)
        normalized_item["path"] = _sanitize_surface(
            normalized_item.get("path")
        )
        normalized_item.setdefault("sourceRefs", [])
        normalized_item.setdefault("provenance", "browser")
        normalized_items.append(normalized_item)
    normalized_candidates: list[dict[str, Any]] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            raise ValueError(
                "coverageInventory.candidateUseCases must contain objects."
            )
        normalized_candidate = dict(candidate)
        normalized_candidate["surface"] = _sanitize_surface(
            normalized_candidate.get("surface")
            or normalized_candidate.get("targetSurface")
        )
        normalized_candidate.setdefault("provenance", "browser")
        normalized_candidate.setdefault("sideEffectClass", "unknown")
        normalized_candidates.append(normalized_candidate)
    status = str(inventory.get("status") or "partial")
    if status not in {"complete", "partial", "stale"}:
        raise ValueError(
            "coverageInventory.status must be complete, partial, or stale."
        )
    inventory.update(
        {
            "status": status,
            "partialInventoryReasons": _normalize_gaps(
                inventory.get("partialInventoryReasons") or []
            ),
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


def _normalize_gaps(value: Any) -> list[str]:
    if not isinstance(value, list):
        raise ValueError("Understanding gaps must be a list.")
    gaps: list[str] = []
    for item in value:
        if isinstance(item, dict):
            text = str(
                item.get("summary")
                or item.get("reason")
                or item.get("message")
                or ""
            ).strip()
        else:
            text = str(item).strip()
        if text and text not in gaps:
            gaps.append(text)
    return gaps


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
