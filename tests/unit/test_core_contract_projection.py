from __future__ import annotations

from pathlib import Path

from tests.fixtures.managed_runtime import core_contract_fixture_payload, current_core_contract_fixture_payload
from verifysignal_spec.workflows.browser_authoring import browser_authoring_contract
from verifysignal_spec.core.executable_contract import CommandContractReuse, project_core_contract, validate_core_contract
from verifysignal_spec.workflows.readiness import executable_contract_blockers


def _finding_codes(projection: dict) -> set[str]:
    return {str(item.get("code")) for item in projection.get("findings", []) if isinstance(item, dict)}


def _required_authoring_warnings() -> list[dict]:
    return [
        {
            "code": "degenerate-text-target",
            "severity": "warning",
            "runtimeReadinessSeverity": "blocking",
            "message": "Broad text-only targets are ambiguous.",
            "remediation": "Use a stable semantic locator.",
            "appliesTo": ["targets", "assertions"],
        },
        {
            "code": "unstable-generated-css-target",
            "severity": "warning",
            "runtimeReadinessSeverity": "blocking",
            "message": "Generated or positional CSS targets are unstable.",
            "remediation": "Use testId, label, href, or another stable semantic locator.",
            "appliesTo": ["targets"],
        },
    ]


def test_command_contract_reuse_is_in_memory_and_keyed_per_command() -> None:
    calls = 0

    def discover() -> dict:
        nonlocal calls
        calls += 1
        return current_core_contract_fixture_payload()

    first_command = CommandContractReuse()
    second_command = CommandContractReuse()

    first = first_command.get_or_discover(
        runtime_identity="core-a",
        core_version="0.1.0",
        public_contract_version="verifysignal-public-cli-json/v1",
        discover=discover,
    )
    second = first_command.get_or_discover(
        runtime_identity="core-a",
        core_version="0.1.0",
        public_contract_version="verifysignal-public-cli-json/v1",
        discover=discover,
    )
    third = second_command.get_or_discover(
        runtime_identity="core-a",
        core_version="0.1.0",
        public_contract_version="verifysignal-public-cli-json/v1",
        discover=discover,
    )

    assert first == second == third
    assert first_command.discovery_count == 1
    assert second_command.discovery_count == 1
    assert calls == 2


def test_projection_filters_to_stable_browser_authoring_items() -> None:
    payload = core_contract_fixture_payload(
        browser_actions=[
            {"name": "navigate", "status": "stable", "requiredFields": ["value"]},
            {"name": "press", "status": "stable", "requiredFields": ["target", "value"]},
            {"name": "dragAndDrop", "status": "experimental", "requiredFields": ["target", "value"]},
        ]
    )

    projection = project_core_contract(payload, runtime_identity="fake-core", core_version="0.1.0")
    browser = projection["sections"]["browserWorkflow"]

    assert browser["validActions"] == ["navigate", "press"]
    assert browser["experimentalItems"]["actions"][0]["name"] == "dragAndDrop"
    authoring = browser_authoring_contract(core_contract=projection)
    assert "dragAndDrop" not in authoring["validActions"]
    assert authoring["experimentalItems"]["actions"][0]["name"] == "dragAndDrop"
    assert projection["sections"]["runRequest"]["schemaVersion"] == "qa-run-request/v1"
    assert projection["sections"]["skill"]["schemaVersion"] == "verifysignal-browser-skill/v1"


def test_projection_preserves_required_contract_sections() -> None:
    payload = core_contract_fixture_payload()

    projection = project_core_contract(payload)

    assert set(projection["sections"]) == {
        "operations",
        "runRequest",
        "skill",
        "skillExecution",
        "browserWorkflow",
        "credentials",
        "placeholders",
        "reportCoverage",
        "sideEffectGuardrails",
        "publicRedactionPolicy",
        "runtimeTrustHandoff",
    }
    assert "environment" in projection["sections"]["credentials"]["sourceNames"]
    assert projection["sections"]["placeholders"]["credentialSyntax"] == "{{credentials.<group>.<field>}}"
    assert "write" in projection["sections"]["sideEffectGuardrails"]["classes"]


def test_core_contract_requires_canonical_data_sections_shape() -> None:
    payload = core_contract_fixture_payload()
    flat_payload = {**payload, "data": payload["data"]["sections"]}

    findings = validate_core_contract(flat_payload)

    assert findings
    assert {finding.code for finding in findings} == {"core-contract.section-missing"}
    assert {finding.contractSection for finding in findings} >= {"operations", "runRequest", "skill", "browserWorkflow"}


def test_projection_treats_supported_browser_capabilities_as_executable() -> None:
    payload = core_contract_fixture_payload(
        extra_sections={
            "browserWorkflow": {
                "actions": [
                    {"name": "navigate", "status": "supported", "requiredFields": ["value"]},
                    {"name": "awaitNetwork", "status": "supported", "requiredFields": ["match"]},
                    {"name": "dragAndDrop", "status": "experimental", "requiredFields": ["target", "value"]},
                ],
                "assertions": [
                    {"name": "visible", "status": "supported", "requiredFields": ["target"]},
                    {"name": "image-diff", "status": "experimental", "requiredFields": ["target"]},
                ],
                "targetSignals": [{"name": "testId", "status": "supported"}],
            }
        }
    )

    projection = project_core_contract(payload)
    browser = projection["sections"]["browserWorkflow"]

    assert browser["validActions"] == ["awaitNetwork", "navigate"]
    assert browser["validAssertionKinds"] == ["visible"]
    assert browser["targetSignalPriority"] == ["testId"]
    assert browser["experimentalItems"]["actions"][0]["name"] == "dragAndDrop"
    assert browser["experimentalItems"]["assertions"][0]["name"] == "image-diff"


def test_projection_accepts_target_signals_as_plain_strings() -> None:
    payload = core_contract_fixture_payload(
        extra_sections={
            "browserWorkflow": {
                "actions": [{"name": "navigate", "status": "supported", "requiredFields": ["value"]}],
                "assertions": [{"name": "visible", "status": "supported", "requiredFields": ["target"]}],
                "targetSignals": ["testId", "label", "text", "css", "semanticLocator"],
            }
        }
    )

    projection = project_core_contract(payload)
    browser = projection["sections"]["browserWorkflow"]

    assert browser["targetSignalPriority"] == ["testId", "label", "text", "css", "semanticLocator"]
    assert browser["targetRules"]["targetSignalPriority"] == ["testId", "label", "text", "css", "semanticLocator"]


def test_current_core_projection_reads_action_level_network_keys() -> None:
    projection = project_core_contract(current_core_contract_fixture_payload())
    browser = projection["sections"]["browserWorkflow"]

    assert browser["validNetworkMatchKeys"] == [
        "method",
        "requestBodyContains",
        "responseBodyContains",
        "status",
        "urlContains",
    ]


def test_projection_uses_legacy_top_level_network_keys_only_as_fallback() -> None:
    projection = project_core_contract(
        core_contract_fixture_payload(
            extra_sections={
                "browserWorkflow": {
                    "actions": [{"name": "awaitNetwork", "status": "stable", "requiredFields": ["match"]}],
                    "assertions": [{"name": "visible", "status": "stable", "requiredFields": ["target"]}],
                    "targetSignals": [{"name": "testId", "status": "stable"}],
                    "networkMatchKeys": [{"name": "urlPattern", "status": "stable"}],
                }
            }
        )
    )

    assert projection["sections"]["browserWorkflow"]["validNetworkMatchKeys"] == ["urlPattern"]


def test_projection_prefers_action_level_network_keys_and_reports_legacy_conflict() -> None:
    projection = project_core_contract(
        current_core_contract_fixture_payload(
            extra_sections={
                "browserWorkflow": {
                    "actions": [
                        {
                            "name": "awaitNetwork",
                            "status": "supported",
                            "requiredFields": ["match"],
                            "match": {"keys": [{"name": "urlContains", "status": "supported"}]},
                        }
                    ],
                    "assertions": [{"name": "visible", "status": "supported", "requiredFields": ["target"]}],
                    "targetSignals": ["testId"],
                    "networkMatchKeys": [{"name": "legacyOnly", "status": "stable"}],
                }
            }
        )
    )

    assert projection["sections"]["browserWorkflow"]["validNetworkMatchKeys"] == ["urlContains"]
    assert "core-contract.canonical-legacy-conflict" in _finding_codes(projection)


def test_current_core_projection_reads_path_field_identifiers() -> None:
    projection = project_core_contract(current_core_contract_fixture_payload())
    run_request = projection["sections"]["runRequest"]
    skill = projection["sections"]["skill"]

    assert "request.id" in run_request["fieldNames"]
    assert "target.url" in run_request["fieldNames"]
    assert "browser.targets" in skill["fieldNames"]
    assert "browser.steps" in skill["fieldNames"]


def test_current_core_projection_preserves_path_field_descriptors() -> None:
    projection = project_core_contract(current_core_contract_fixture_payload())
    run_request = projection["sections"]["runRequest"]
    skill = projection["sections"]["skill"]

    assert run_request["fields"][1]["path"] == "request.id"
    assert skill["fields"][2]["path"] == "browser.targets"


def test_current_core_projection_separates_section_and_artifact_schema_versions() -> None:
    projection = project_core_contract(current_core_contract_fixture_payload())
    run_request = projection["sections"]["runRequest"]
    skill = projection["sections"]["skill"]

    assert run_request["sectionSchemaVersion"] == 1
    assert run_request["artifactSchemaVersion"] == "qa-run-request/v1"
    assert skill["sectionSchemaVersion"] == 1
    assert skill["artifactSchemaVersion"] == "qa-skill/v1"


def test_current_core_projection_reads_credential_refs_supported_sources() -> None:
    projection = project_core_contract(current_core_contract_fixture_payload())
    credentials = projection["sections"]["credentials"]

    assert credentials["sourceNames"] == ["environment"]
    assert credentials["referenceShape"] == "credentialRefs.<group>.keys.<field>"
    assert credentials["placeholderSyntax"] == "{{credentials.<group>.<field>}}"
    assert credentials["credentialRefs"]["supportedSources"][0]["name"] == "environment"


def test_current_core_projection_uses_target_composition_supported_signals() -> None:
    projection = project_core_contract(
        current_core_contract_fixture_payload(
            extra_sections={
                "browserWorkflow": {
                    "actions": [{"name": "navigate", "status": "supported", "requiredFields": ["value"]}],
                    "assertions": [{"name": "visible", "status": "supported", "requiredFields": ["target"]}],
                    "targetSignals": ["testId", "label", "css"],
                    "targets": {"composition": {"supportedSignals": ["label", "css"]}},
                }
            }
        )
    )
    browser = projection["sections"]["browserWorkflow"]

    assert browser["targetRules"]["compositionSignals"] == ["label", "css"]
    assert "label, css" in browser["targetRules"]["composition"]


def test_projection_preserves_non_executable_status_items_as_metadata() -> None:
    projection = project_core_contract(
        current_core_contract_fixture_payload(
            extra_sections={
                "browserWorkflow": {
                    "actions": [
                        {"name": "navigate", "status": "supported", "requiredFields": ["value"]},
                        {"name": "click", "status": "stable", "requiredFields": ["target"]},
                        {"name": "dragAndDrop", "status": "experimental", "requiredFields": ["target", "value"]},
                        {"name": "legacyPress", "status": "deprecated", "requiredFields": ["target"]},
                        {"name": "privateAction", "status": "unsupported", "requiredFields": ["target"]},
                    ],
                    "assertions": [{"name": "visible", "status": "supported", "requiredFields": ["target"]}],
                    "targetSignals": ["testId"],
                }
            }
        )
    )
    browser = projection["sections"]["browserWorkflow"]

    assert browser["validActions"] == ["click", "navigate"]
    assert [item["name"] for item in browser["experimentalItems"]["actions"]] == ["dragAndDrop"]
    assert [item["name"] for item in browser["nonExecutableItems"]["actions"]] == ["legacyPress", "privateAction"]


def test_projection_prefers_path_over_legacy_name_and_reports_field_conflict() -> None:
    projection = project_core_contract(
        current_core_contract_fixture_payload(
            extra_sections={
                "runRequest": {
                    "schemaVersion": 1,
                    "status": "supported",
                    "fields": [
                        {"path": "schemaVersion", "name": "schemaVersion", "status": "supported", "required": True, "allowedValues": ["qa-run-request/v1"]},
                        {"path": "request.id", "name": "request", "status": "supported", "required": True},
                    ],
                }
            }
        )
    )

    assert projection["sections"]["runRequest"]["fieldNames"] == ["schemaVersion", "request.id"]
    assert "core-contract.canonical-legacy-conflict" in _finding_codes(projection)


def test_projection_prefers_credential_refs_over_legacy_sources_and_reports_conflict() -> None:
    projection = project_core_contract(
        current_core_contract_fixture_payload(
            extra_sections={
                "credentials": {
                    "credentialRefs": {
                        "supportedSources": [{"name": "environment", "status": "supported"}],
                        "referenceShape": "credentialRefs.<group>.keys.<field>",
                        "placeholderSyntax": "{{credentials.<group>.<field>}}",
                    },
                    "sources": [{"name": "vault", "status": "stable"}],
                }
            }
        )
    )

    assert projection["sections"]["credentials"]["sourceNames"] == ["environment"]
    assert "core-contract.canonical-legacy-conflict" in _finding_codes(projection)


def test_current_core_projection_reports_missing_required_executable_metadata() -> None:
    projection = project_core_contract(
        current_core_contract_fixture_payload(
            extra_sections={
                "browserWorkflow": {
                    "actions": [{"name": "awaitNetwork", "status": "supported", "requiredFields": ["match"]}],
                    "assertions": [{"name": "visible", "status": "supported", "requiredFields": ["target"]}],
                    "targetSignals": ["testId"],
                }
            }
        )
    )

    assert "core-contract.required-executable-metadata-missing" in _finding_codes(projection)


def test_projection_preserves_public_authoring_guardrails_for_runtime_readiness() -> None:
    payload = current_core_contract_fixture_payload()
    payload["data"]["sections"]["browserWorkflow"]["warnings"] = _required_authoring_warnings()

    projection = project_core_contract(payload)
    browser = projection["sections"]["browserWorkflow"]
    authoring = browser_authoring_contract(core_contract=projection)

    assert browser["authoringWarnings"] == _required_authoring_warnings()
    assert authoring["authoringWarnings"] == _required_authoring_warnings()


def test_runtime_readiness_blocks_a_core_that_does_not_announce_required_authoring_guardrails() -> None:
    payload = current_core_contract_fixture_payload()
    payload["data"]["sections"]["browserWorkflow"].pop("warnings", None)
    projection = project_core_contract(payload)

    blockers = executable_contract_blockers(Path("."), None, core_contract=projection)

    assert any(blocker.code == "core.authoring-guardrails-outdated" for blocker in blockers)


def test_runtime_readiness_accepts_a_core_that_announces_required_authoring_guardrails() -> None:
    payload = current_core_contract_fixture_payload()
    payload["data"]["sections"]["browserWorkflow"]["warnings"] = _required_authoring_warnings()
    projection = project_core_contract(payload)

    blockers = executable_contract_blockers(Path("."), None, core_contract=projection)

    assert not any(blocker.code == "core.authoring-guardrails-outdated" for blocker in blockers)
