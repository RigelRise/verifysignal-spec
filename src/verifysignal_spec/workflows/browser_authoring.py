from __future__ import annotations

import re
from typing import Any

from verifysignal_spec.workspace.models import RunProfile

from verifysignal_spec.core.executable_contract import browser_authoring_projection
from .models import RunProfileSettings

VALID_BROWSER_ACTIONS = {
    "navigate",
    "click",
    "fill",
    "select",
    "waitForText",
    "checkText",
    "checkLocation",
    "waitForLocation",
    "captureScreenshot",
    "scrollIntoView",
    "awaitNetwork",
    "repeatUntil",
}

VALID_ASSERTION_KINDS = {"text", "location", "visible", "hidden", "screenshot-required"}
VALID_NETWORK_MATCH_KEYS = {"urlContains", "method", "status", "requestBodyContains", "responseBodyContains"}
NETWORK_METADATA_KEYS = {"operationName", "expectedStatus"}
TARGET_SIGNAL_KEYS = ("testId", "label", "text", "css", "semanticLocator", "all")
PLACEHOLDER_RE = re.compile(r"\{\{\s*([^}]+?)\s*\}\}")

ACTION_REQUIREMENTS = {
    "navigate": {"required": ["value"], "notes": "The URL goes in value, not target."},
    "click": {"required": ["target"], "notes": "target must name a browser.targets entry."},
    "fill": {"required": ["target", "value"], "notes": "target must name a browser.targets entry; value must be a string."},
    "select": {"required": ["target", "value"], "notes": "target must name a browser.targets entry; value must be a string."},
    "waitForText": {"required": ["target", "value"], "notes": "Use a named target plus the text to wait for."},
    "checkText": {"required": ["target", "value"], "notes": "Use a named target plus the expected visible text."},
    "checkLocation": {"required": ["value"], "notes": "value is the URL fragment or location expectation."},
    "waitForLocation": {"required": ["value"], "notes": "value is the URL fragment to wait for; timeoutMs bounds the wait."},
    "captureScreenshot": {"required": [], "notes": "value may name the evidence screenshot."},
    "scrollIntoView": {"required": ["target"], "notes": "target must name a browser.targets entry."},
    "awaitNetwork": {"required": ["match"], "notes": "match must include at least one supported network field."},
    "repeatUntil": {"required": ["until", "do"], "notes": "Use supported condition/action blocks."},
}


def browser_authoring_contract(core_contract: dict[str, Any] | None = None) -> dict[str, Any]:
    if core_contract:
        return browser_authoring_projection(core_contract)
    return {
        "schemaVersion": "verifysignal-browser-authoring-contract/v1",
        "validActions": sorted(VALID_BROWSER_ACTIONS),
        "validAssertionKinds": sorted(VALID_ASSERTION_KINDS),
        "validNetworkMatchKeys": sorted(VALID_NETWORK_MATCH_KEYS),
        "targetRules": {
            "stepsReferenceNamedTargets": "Step target values must be aliases declared under browser.targets, not inline CSS, text=, placeholder=, xpath, or role selectors.",
            "targetSignalPriority": ["testId", "label", "text", "css", "semanticLocator"],
            "singlePrimarySignal": "Declare one primary selector signal per target. If a target has both label and css, Core uses label first and ignores css.",
            "composition": "Use all only when multiple signals must match the same element. all entries support testId or css.",
        },
        "actionRequirements": ACTION_REQUIREMENTS,
        "assertionRules": {
            "text": "Requires target and expected. Assertions run after all steps complete.",
            "location": "Requires expected.",
            "visible": "Requires target.",
            "hidden": "Requires target.",
            "screenshot-required": "Use for intermediate visual gates captured during steps.",
            "fieldName": "Assertions use expected, not value.",
            "gateId": "Assertions used for planned coverage must declare gateId and target a specific rendered result.",
        },
        "gateEvidenceRules": {
            "gateId": "UI assertions, network waits, and screenshots must declare gateId to count toward planned gate coverage.",
            "renderedResult": "Required page-view gates need a specific target plus expected text/state/count; URL, screenshot, body text, and HTTP 200 alone are not complete.",
            "network": "awaitNetwork match may include operationName as metadata, but method plus a public match key and expected status are required for gate coverage.",
        },
        "timingGuidance": [
            "For debounced inputs, do not rely on awaitNetwork immediately after fill; the request may not have fired yet.",
            "Prefer checkText or waitForText with a longer timeout to wait through debounce, API response, and render.",
        ],
        "examples": {
            "target": {"searchInput": {"css": "input#search", "domainSemantics": "Search input"}},
            "navigateStep": {"id": "open", "action": "navigate", "value": "{{parameters.baseUrl}}/search/people"},
            "textStep": {"id": "check-results", "action": "checkText", "target": "pageContent", "value": "Results", "timeoutMs": 30000},
            "networkStep": {"id": "wait-get", "action": "awaitNetwork", "match": {"method": "GET"}},
            "textAssertion": {"id": "final-state", "kind": "text", "target": "pageContent", "expected": "Search teams"},
        },
    }


def resolve_effective_profile_settings(profile: RunProfile, slow_mo_override: int | None = None) -> RunProfileSettings:
    if slow_mo_override is not None:
        return RunProfileSettings(
            profile=profile.name,
            headed=profile.headed,
            slowMoMs=int(slow_mo_override),
            source="cli-override",
            overrides=["slowMoMs"],
        )

    built_in_slow_mo = {"normal": 0, "debug": 900, "browser": 900}
    if profile.name in built_in_slow_mo:
        expected = built_in_slow_mo[profile.name]
        if profile.slowMoMs in {0, expected}:
            return RunProfileSettings(profile=profile.name, headed=profile.headed, slowMoMs=expected, source="default")
    return RunProfileSettings(profile=profile.name, headed=profile.headed, slowMoMs=profile.slowMoMs, source="workspace-profile")


def validate_browser_payload(
    browser: dict[str, Any],
    *,
    core_contract: dict[str, Any] | None = None,
    credential_refs: dict[str, Any] | None = None,
) -> list[str]:
    rules = _rules_from_contract(core_contract)
    blockers: list[str] = []
    targets = browser.get("targets") if isinstance(browser.get("targets"), dict) else {}
    for alias, bundle in targets.items():
        if not isinstance(bundle, dict):
            blockers.append(f"browser.targets.{alias} must be an object.")
            continue
        blockers.extend(_validate_target_bundle(str(alias), bundle, rules["targetSignals"], rules["compositionSignals"]))

    for index, step in enumerate(_list(browser.get("steps")), start=1):
        blockers.extend(_validate_step(step, index, targets, rules))

    for index, assertion in enumerate(_list(browser.get("assertions")), start=1):
        blockers.extend(_validate_assertion(assertion, index, targets, rules))
    blockers.extend(_validate_placeholders(browser, credential_refs or {}))
    return blockers


def _validate_target_bundle(alias: str, bundle: dict[str, Any], target_signal_keys: set[str], composition_signals: set[str]) -> list[str]:
    blockers: list[str] = []
    primary_signals = [key for key in target_signal_keys if _has_value(bundle.get(key))]
    if not primary_signals:
        blockers.append(f"browser.targets.{alias} must define one selector signal: {', '.join(sorted(target_signal_keys))}.")
    if len(primary_signals) > 1:
        blockers.append(
            f"browser.targets.{alias} defines multiple primary selector signals ({', '.join(primary_signals)}). "
            "Use one signal only, or use all for same-element composition."
        )
    if "all" in primary_signals:
        entries = bundle.get("all")
        if not isinstance(entries, list) or len(entries) < 2:
            blockers.append(f"browser.targets.{alias}.all must be an array with at least two entries.")
        else:
            for index, entry in enumerate(entries, start=1):
                if not isinstance(entry, dict):
                    blockers.append(f"browser.targets.{alias}.all[{index}] must be an object.")
                    continue
                signals = [key for key in composition_signals if _has_value(entry.get(key))]
                unsupported = sorted(key for key in entry if key not in composition_signals)
                if unsupported:
                    blockers.append(f"browser.targets.{alias}.all[{index}] uses unsupported signals: {', '.join(unsupported)}.")
                if len(signals) != 1:
                    blockers.append(f"browser.targets.{alias}.all[{index}] must contain exactly one supported signal.")
    return blockers


def _validate_step(step: Any, index: int, targets: dict[str, Any], rules: dict[str, Any]) -> list[str]:
    if not isinstance(step, dict):
        return [f"browser.steps[{index}] must be an object."]
    blockers: list[str] = []
    step_id = str(step.get("id") or f"#{index}")
    action = step.get("action")
    valid_actions = rules["actions"]
    if action not in valid_actions:
        blockers.append(
            f"Unsupported browser step action at {step_id}: {action!r}. Valid actions: {', '.join(sorted(valid_actions))}."
        )
        return blockers

    if action == "navigate":
        if not isinstance(step.get("value"), str) or not step.get("value"):
            blockers.append(f"Step {step_id} action navigate must put the URL in value, not target.")
        return blockers

    if action in {"click", "fill", "select", "waitForText", "checkText", "scrollIntoView"}:
        blockers.extend(_require_named_target(step, step_id, targets))
    if action in {"fill", "select", "waitForText", "checkText", "checkLocation", "waitForLocation"} and not isinstance(step.get("value"), str):
        blockers.append(f"Step {step_id} action {action} requires string value.")
    if action == "awaitNetwork":
        blockers.extend(_validate_network_match(step.get("match"), f"Step {step_id}", rules))
        if step.get("gateId") and not isinstance(step.get("gateId"), str):
            blockers.append(f"Step {step_id} gateId must be a string.")
    if action == "repeatUntil":
        if not isinstance(step.get("until"), dict):
            blockers.append(f"Step {step_id} action repeatUntil requires until object.")
        if not isinstance(step.get("do"), dict):
            blockers.append(f"Step {step_id} action repeatUntil requires do object.")
    return blockers


def _validate_assertion(assertion: Any, index: int, targets: dict[str, Any], rules: dict[str, Any]) -> list[str]:
    if not isinstance(assertion, dict):
        return [f"browser.assertions[{index}] must be an object."]
    blockers: list[str] = []
    assertion_id = str(assertion.get("id") or f"#{index}")
    kind = assertion.get("kind")
    valid_assertions = rules["assertions"]
    if kind not in valid_assertions:
        blockers.append(
            f"Unsupported browser assertion kind at {assertion_id}: {kind!r}. Valid kinds: {', '.join(sorted(valid_assertions))}."
        )
        return blockers
    if kind in {"text", "visible", "hidden"}:
        blockers.extend(_require_named_target(assertion, f"Assertion {assertion_id}", targets))
    if kind in {"text", "location"}:
        if "expected" not in assertion:
            if "value" in assertion:
                blockers.append(f"Assertion {assertion_id} uses value; browser assertions require expected.")
            else:
                blockers.append(f"Assertion {assertion_id} kind {kind} requires expected.")
    if assertion.get("gateId") and not isinstance(assertion.get("gateId"), str):
        blockers.append(f"Assertion {assertion_id} gateId must be a string.")
    return blockers


def _validate_network_match(match: Any, prefix: str, rules: dict[str, Any] | None = None) -> list[str]:
    if not isinstance(match, dict):
        return [f"{prefix} action awaitNetwork requires match object."]
    rules = rules or _rules_from_contract(None)
    valid_network_keys = rules["networkKeys"]
    metadata_keys = rules["networkMetadataKeys"]
    present_keys = {str(key) for key, value in match.items() if value is not None}
    unsupported = sorted(present_keys - valid_network_keys - metadata_keys)
    blockers = []
    if unsupported:
        blockers.append(f"{prefix} awaitNetwork.match uses unsupported keys: {', '.join(unsupported)}.")
    public_present = present_keys & valid_network_keys
    if not public_present:
        blockers.append(f"{prefix} awaitNetwork.match must include at least one supported field.")
    return blockers


def _require_named_target(item: dict[str, Any], label: str, targets: dict[str, Any]) -> list[str]:
    target = item.get("target")
    if not isinstance(target, str) or not target:
        return [f"{label} requires target referencing a browser.targets alias."]
    if target not in targets:
        return [f"{label} target {target!r} is not declared in browser.targets."]
    return []


def _validate_placeholders(value: Any, credential_refs: dict[str, Any], path: str = "browser") -> list[str]:
    blockers: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            blockers.extend(_validate_placeholders(child, credential_refs, f"{path}.{key}"))
        return blockers
    if isinstance(value, list):
        for index, child in enumerate(value):
            blockers.extend(_validate_placeholders(child, credential_refs, f"{path}[{index}]"))
        return blockers
    if not isinstance(value, str):
        return blockers
    for match in PLACEHOLDER_RE.finditer(value):
        expression = match.group(1).strip()
        if expression.startswith("env."):
            blockers.append(f"{path} uses unsupported placeholder namespace '{{{{{expression}}}}}'. Use credentialRefs plus {{{{credentials.<group>.<field>}}}} for secrets.")
            continue
        if not expression.startswith("credentials."):
            continue
        parts = expression.split(".")
        if len(parts) != 3 or not parts[1] or not parts[2]:
            blockers.append(f"{path} uses invalid credential placeholder '{{{{{expression}}}}}'. Expected {{{{credentials.<group>.<field>}}}}.")
            continue
        group, field = parts[1], parts[2]
        config = credential_refs.get(group)
        keys = config.get("keys") if isinstance(config, dict) else None
        if not isinstance(keys, dict) or field not in keys:
            blockers.append(f"{path} references undeclared credential '{{{{{expression}}}}}'. Declare credentialRefs.{group}.keys.{field}.")
    return blockers


def _has_value(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) or isinstance(value, list) and bool(value)


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _rules_from_contract(core_contract: dict[str, Any] | None) -> dict[str, Any]:
    if not core_contract:
        return {
            "actions": set(VALID_BROWSER_ACTIONS),
            "assertions": set(VALID_ASSERTION_KINDS),
            "networkKeys": set(VALID_NETWORK_MATCH_KEYS),
            "networkMetadataKeys": set(NETWORK_METADATA_KEYS),
            "targetSignals": set(TARGET_SIGNAL_KEYS),
            "compositionSignals": {"testId", "css"},
        }
    browser = core_contract.get("sections", {}).get("browserWorkflow", {})
    target_signals = set(browser.get("targetSignalPriority") or [])
    target_rules = browser.get("targetRules") if isinstance(browser.get("targetRules"), dict) else {}
    composition_signals = set(target_rules.get("compositionSignals") or [])
    if composition_signals:
        target_signals.add("all")
    return {
        "actions": set(browser.get("validActions") or []),
        "assertions": set(browser.get("validAssertionKinds") or []),
        "networkKeys": set(browser.get("validNetworkMatchKeys") or []),
        "networkMetadataKeys": set(browser.get("networkMetadataKeys") or []),
        "targetSignals": target_signals,
        "compositionSignals": composition_signals,
    }
