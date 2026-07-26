from __future__ import annotations

import pytest

from tests.fixtures.workflows.browser_first_understanding import browser_understanding_payload
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
