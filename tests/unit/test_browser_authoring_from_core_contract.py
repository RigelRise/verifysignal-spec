from __future__ import annotations

from tests.fixtures.managed_runtime import core_contract_fixture_payload, current_core_contract_fixture_payload
from verifysignal_spec.core.executable_contract import project_core_contract
from verifysignal_spec.workflows.browser_authoring import validate_browser_payload


def _projection() -> dict:
    return project_core_contract(
        core_contract_fixture_payload(
            browser_actions=[
                {"name": "navigate", "status": "stable", "requiredFields": ["value"]},
                {"name": "press", "status": "stable", "requiredFields": ["target", "value"]},
                {"name": "repeatUntil", "status": "unsupported", "requiredFields": ["until", "do"]},
            ]
        )
    )


def _current_projection() -> dict:
    return project_core_contract(current_core_contract_fixture_payload())


def _browser_with_network_match(match: dict) -> dict:
    return {
        "targets": {"page": {"testId": "page"}},
        "steps": [{"id": "wait-api", "action": "awaitNetwork", "match": match}],
        "assertions": [],
    }


def test_browser_validation_uses_core_added_stable_action() -> None:
    browser = {
        "targets": {"searchBox": {"testId": "search-box"}},
        "steps": [{"id": "press-enter", "action": "press", "target": "searchBox", "value": "Enter"}],
        "assertions": [],
    }

    assert validate_browser_payload(browser, core_contract=_projection()) == []


def test_browser_validation_rejects_core_removed_local_action() -> None:
    browser = {
        "targets": {"page": {"css": "body"}},
        "steps": [{"id": "legacy-repeat", "action": "repeatUntil", "until": {"text": "Done"}, "do": {"action": "click"}}],
        "assertions": [],
    }

    blockers = validate_browser_payload(browser, core_contract=_projection())

    assert blockers
    assert "repeatUntil" in blockers[0]


def test_browser_validation_accepts_core_declared_network_match_key() -> None:
    browser = _browser_with_network_match({"method": "POST", "responseBodyContains": "ok"})

    assert validate_browser_payload(browser, core_contract=_current_projection()) == []


def test_browser_validation_rejects_undeclared_network_match_key() -> None:
    browser = _browser_with_network_match({"method": "POST", "privateHeaderContains": "secret"})

    blockers = validate_browser_payload(browser, core_contract=_current_projection())

    assert blockers
    assert "privateHeaderContains" in blockers[0]


def test_browser_validation_accepts_declared_group_field_credential_placeholder() -> None:
    browser = {
        "targets": {"email": {"testId": "email"}},
        "steps": [{"id": "fill-email", "action": "fill", "target": "email", "value": "{{credentials.e2eUser.email}}"}],
        "assertions": [],
    }

    assert validate_browser_payload(
        browser,
        core_contract=_current_projection(),
        credential_refs={"e2eUser": {"source": "environment", "keys": {"email": "E2E_USER_EMAIL"}}},
    ) == []


def test_browser_validation_rejects_raw_env_credential_placeholder() -> None:
    browser = {
        "targets": {"email": {"testId": "email"}},
        "steps": [{"id": "fill-email", "action": "fill", "target": "email", "value": "{{env.E2E_USER_EMAIL}}"}],
        "assertions": [],
    }

    blockers = validate_browser_payload(browser, core_contract=_current_projection())

    assert blockers
    assert "{{env.E2E_USER_EMAIL}}" in blockers[0]


def test_browser_validation_accepts_core_declared_target_composition_signals() -> None:
    projection = project_core_contract(
        current_core_contract_fixture_payload(
            extra_sections={
                "browserWorkflow": {
                    "actions": [{"name": "click", "status": "supported", "requiredFields": ["target"]}],
                    "assertions": [{"name": "visible", "status": "supported", "requiredFields": ["target"]}],
                    "targetSignals": ["testId", "label", "css"],
                    "targets": {"composition": {"supportedSignals": ["label", "css"]}},
                }
            }
        )
    )
    browser = {
        "targets": {"emailField": {"all": [{"label": "Email"}, {"css": "input[type=email]"}]}},
        "steps": [{"id": "click-email", "action": "click", "target": "emailField"}],
        "assertions": [],
    }

    assert validate_browser_payload(browser, core_contract=projection) == []


def test_browser_validation_rejects_composition_signal_not_declared_by_core() -> None:
    projection = project_core_contract(
        current_core_contract_fixture_payload(
            extra_sections={
                "browserWorkflow": {
                    "actions": [{"name": "click", "status": "supported", "requiredFields": ["target"]}],
                    "assertions": [{"name": "visible", "status": "supported", "requiredFields": ["target"]}],
                    "targetSignals": ["testId", "label", "css"],
                    "targets": {"composition": {"supportedSignals": ["label", "css"]}},
                }
            }
        )
    )
    browser = {
        "targets": {"emailField": {"all": [{"testId": "email"}, {"css": "input[type=email]"}]}},
        "steps": [{"id": "click-email", "action": "click", "target": "emailField"}],
        "assertions": [],
    }

    blockers = validate_browser_payload(browser, core_contract=projection)

    assert blockers
    assert "testId" in blockers[0]


def test_browser_validation_fallback_accepts_wait_for_location() -> None:
    # Core spec 019: waitForLocation is the first-class click-to-navigation wait. The managed path
    # projects it from Core contract discovery; the offline fallback list must accept it too.
    browser = {
        "targets": {"page": {"testId": "page"}},
        "steps": [{"id": "await-dashboard-url", "action": "waitForLocation", "value": "/dashboard"}],
        "assertions": [],
    }

    assert validate_browser_payload(browser) == []


def test_browser_validation_fallback_requires_wait_for_location_value() -> None:
    browser = {
        "targets": {"page": {"testId": "page"}},
        "steps": [{"id": "await-dashboard-url", "action": "waitForLocation"}],
        "assertions": [],
    }

    blockers = validate_browser_payload(browser)

    assert blockers
    assert "waitForLocation" in blockers[0]
    assert "value" in blockers[0]
