from __future__ import annotations

import pytest

from tests.fixtures.workflows.browser_first_understanding import (
    browser_understanding_alias_payload,
    browser_understanding_payload,
)
from verifysignal_spec.workflows.browser_understanding import (
    BROWSER_FIRST_UNDERSTANDING_CAPABILITY,
    normalize_browser_understanding_payload,
    sanitize_browser_url,
)


def test_sanitizes_url_and_applies_bounded_same_origin_defaults() -> None:
    normalized = normalize_browser_understanding_payload(browser_understanding_payload())

    assert BROWSER_FIRST_UNDERSTANDING_CAPABILITY == "browser-first-understanding/v1"
    assert normalized["targetEnvironment"]["locator"] == "https://app.example.test/projects"
    assert normalized["targetEnvironment"]["origin"] == "https://app.example.test"
    assert normalized["targetEnvironment"]["allowedOrigins"] == ["https://app.example.test"]
    assert normalized["explorationScope"] == {
        "allowedOrigins": ["https://app.example.test"],
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
        "status": "complete",
        "partialInventoryReasons": [],
    }


@pytest.mark.parametrize(
    "url",
    [
        "file:///tmp/app.html",
        "javascript:alert(1)",
        "https://user:password@app.example.test/",
        "https:///missing-host",
    ],
)
def test_rejects_unsupported_or_credential_bearing_target_urls(url: str) -> None:
    with pytest.raises(ValueError, match="HTTP\\(S\\)|credentials|host"):
        sanitize_browser_url(url)


@pytest.mark.parametrize(
    "forbidden_field",
    [
        "rawDom",
        "mcpSnapshot",
        "screenshotPath",
        "trace",
        "responseBody",
        "cookies",
        "storageState",
        "formValues",
        "queryParams",
    ],
)
def test_rejects_raw_or_secret_bearing_browser_artifacts(forbidden_field: str) -> None:
    payload = browser_understanding_payload()
    payload["productSignals"][0][forbidden_field] = "must-not-persist"

    with pytest.raises(ValueError, match=forbidden_field):
        normalize_browser_understanding_payload(payload)


def test_candidate_shortfall_is_partial_and_records_gap() -> None:
    payload = browser_understanding_payload(candidate_count=1)
    payload["coverageInventory"]["status"] = "complete"
    payload["explorationScope"]["status"] = "complete"
    payload["coverageInventory"]["partialInventoryReasons"] = []
    payload["explorationScope"]["partialInventoryReasons"] = []
    payload["gaps"] = []

    normalized = normalize_browser_understanding_payload(payload)

    assert normalized["coverageInventory"]["status"] == "partial"
    assert normalized["explorationScope"]["status"] == "partial"
    assert "candidate minimum" in normalized["gaps"][0].lower()


def test_normalization_is_idempotent() -> None:
    once = normalize_browser_understanding_payload(browser_understanding_payload())
    twice = normalize_browser_understanding_payload(once)

    assert twice == once


def test_mapping_scope_cannot_disable_read_safe_boundary() -> None:
    payload = browser_understanding_payload()
    payload["explorationScope"]["readSafeOnly"] = False

    with pytest.raises(ValueError, match="readSafeOnly"):
        normalize_browser_understanding_payload(payload)


def test_documented_aliases_normalize_to_the_canonical_payload() -> None:
    canonical = normalize_browser_understanding_payload(browser_understanding_payload())
    aliased = normalize_browser_understanding_payload(
        browser_understanding_alias_payload()
    )

    assert aliased == canonical


def test_equivalent_top_level_candidate_alias_does_not_duplicate_state() -> None:
    payload = browser_understanding_payload()
    payload["candidateUseCases"] = [
        dict(item)
        for item in payload["coverageInventory"]["candidateUseCases"]
    ]

    normalized = normalize_browser_understanding_payload(payload)

    assert "candidateUseCases" not in normalized
    assert normalized["coverageInventory"]["candidateUseCases"] == (
        normalize_browser_understanding_payload(
            browser_understanding_payload()
        )["coverageInventory"]["candidateUseCases"]
    )


@pytest.mark.parametrize(
    ("field", "value", "allowed"),
    [
        (
            "reachabilityStatus",
            "reachable-public",
            "reachable, unreachable, authentication-required, unknown",
        ),
        (
            "signalKind",
            "flow",
            "surface, state, transition, runtime-requirement, gap",
        ),
    ],
)
def test_manual_smoke_enum_errors_name_the_allowed_values(
    field: str,
    value: str,
    allowed: str,
) -> None:
    payload = browser_understanding_payload()
    if field == "reachabilityStatus":
        payload["targetEnvironment"]["reachabilityStatus"] = value
    else:
        payload["productSignals"][0]["kind"] = value

    with pytest.raises(ValueError) as raised:
        normalize_browser_understanding_payload(payload)

    assert allowed in str(raised.value)


def test_rejects_unknown_nested_fields_with_an_actionable_path() -> None:
    payload = browser_understanding_payload()
    payload["coverageInventory"]["candidateUseCases"][0]["inventedSafety"] = True

    with pytest.raises(
        ValueError,
        match=r"coverageInventory\.candidateUseCases\[0\]\.inventedSafety",
    ):
        normalize_browser_understanding_payload(payload)


def test_rejects_structured_gap_instead_of_silently_dropping_its_fields() -> None:
    payload = browser_understanding_payload()
    payload["gaps"] = [
        {
            "id": "authenticated-surfaces-not-mapped",
            "summary": "Authenticated surfaces were not mapped.",
            "status": "authentication-required",
        }
    ]

    with pytest.raises(ValueError, match=r"gaps\[0\]"):
        normalize_browser_understanding_payload(payload)


def test_rejects_missing_required_signal_evidence() -> None:
    payload = browser_understanding_payload()
    payload["productSignals"][0].pop("evidence")

    with pytest.raises(
        ValueError,
        match=r"productSignals\[0\]\.evidence",
    ):
        normalize_browser_understanding_payload(payload)


def test_rejects_invalid_inventory_enum_value() -> None:
    payload = browser_understanding_payload()
    payload["coverageInventory"]["items"][0]["priority"] = "urgent"

    with pytest.raises(
        ValueError,
        match=r"coverageInventory\.items\[0\]\.priority",
    ):
        normalize_browser_understanding_payload(payload)


def test_rejects_unknown_refresh_impact_fields() -> None:
    payload = browser_understanding_payload()
    payload["refreshImpacts"] = [
        {
            "alias": "projects-list",
            "status": "unaffected",
            "reason": "No impact.",
            "inventedAction": "ignore",
        }
    ]

    with pytest.raises(
        ValueError,
        match=r"refreshImpacts\[0\]\.inventedAction",
    ):
        normalize_browser_understanding_payload(payload)


def test_rejects_conflicting_canonical_and_alias_values() -> None:
    payload = browser_understanding_payload()
    payload["coverageInventory"]["items"][0]["surface"] = "/different"

    with pytest.raises(
        ValueError,
        match=r"coverageInventory\.items\[0\]\.(path|surface)",
    ):
        normalize_browser_understanding_payload(payload)


def test_rejects_missing_required_inventory_identity() -> None:
    payload = browser_understanding_payload()
    payload["coverageInventory"]["items"][0].pop("title")

    with pytest.raises(
        ValueError,
        match=r"coverageInventory\.items\[0\]\.title",
    ):
        normalize_browser_understanding_payload(payload)


def test_rejects_unknown_inventory_and_signal_references() -> None:
    payload = browser_understanding_payload()
    payload["coverageInventory"]["candidateUseCases"][0][
        "productSignalRefs"
    ].append("missing-signal")

    with pytest.raises(
        ValueError,
        match=r"coverageInventory\.candidateUseCases\[0\]\.productSignalRefs",
    ):
        normalize_browser_understanding_payload(payload)


def test_observed_multi_surface_candidate_requires_matching_transition_signal() -> None:
    payload = browser_understanding_payload()
    candidate = payload["coverageInventory"]["candidateUseCases"][0]
    candidate["surface"] = "/projects -> /projects/alpha"
    candidate["sourceInventoryItems"] = [
        "surface-projects-list",
        "surface-project-details",
    ]
    candidate["productSignalRefs"] = ["projects-list", "project-details"]
    candidate["knownRuntimeRequirements"] = ["baseUrl"]
    candidate["groundingStatus"] = "observed"

    with pytest.raises(
        ValueError,
        match=r"coverageInventory\.candidateUseCases\[0\]\.groundingStatus",
    ):
        normalize_browser_understanding_payload(payload)

    payload["productSignals"].append(
        {
            "id": "projects-to-details",
            "kind": "transition",
            "surface": "/projects",
            "fromSurface": "/projects",
            "toSurface": "/projects/alpha",
            "summary": "Selecting a project opens its detail surface.",
            "evidence": ["The project result was selected and the detail rendered."],
            "provenance": "browser",
            "observedAt": "2026-07-26T18:00:00Z",
            "confidence": "high",
            "inventoryItemRefs": [
                "surface-projects-list",
                "surface-project-details",
            ],
        }
    )
    candidate["productSignalRefs"].append("projects-to-details")

    normalized = normalize_browser_understanding_payload(payload)

    assert normalized["coverageInventory"]["candidateUseCases"][0][
        "groundingStatus"
    ] == "observed"


def test_authentication_grounding_requires_a_runtime_or_gap_signal() -> None:
    payload = browser_understanding_payload()
    candidate = payload["coverageInventory"]["candidateUseCases"][0]
    candidate["knownRuntimeRequirements"] = ["baseUrl"]
    candidate["productSignalRefs"] = ["projects-list"]

    with pytest.raises(
        ValueError,
        match=r"coverageInventory\.candidateUseCases\[0\]\.groundingStatus",
    ):
        normalize_browser_understanding_payload(payload)
