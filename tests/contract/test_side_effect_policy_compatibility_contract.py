from __future__ import annotations

import json

import pytest

from verifysignal_spec.workspace.artifacts import render_run_request

from tests.fixtures.workflows.side_effect_contract_alignment import create_write_policy_workspace, legacy_rules_policy


def test_generated_run_request_uses_canonical_allowed_forbidden_policy(tmp_path) -> None:
    record = create_write_policy_workspace(tmp_path)

    rendered = json.loads(render_run_request(record))

    policy = rendered["sideEffectPolicy"]
    assert policy["class"] == "write"
    assert policy["mode"] == "enforce"
    assert "allowed" in policy
    assert "forbidden" not in policy or isinstance(policy["forbidden"], list)
    assert "rules" not in policy
    assert policy["allowed"] == [{"id": "allow-backend-graphql", "kind": "network", "methods": ["POST"], "urlContains": "be.example.test/graphql"}]
    assert "method" not in policy["allowed"][0]


def test_legacy_rules_are_compatibility_input_only_not_rendered(tmp_path) -> None:
    record = create_write_policy_workspace(tmp_path, side_effects=legacy_rules_policy())

    rendered = json.loads(render_run_request(record))

    policy = rendered["sideEffectPolicy"]
    assert "rules" not in policy
    assert policy["allowed"] == [{"id": "allow-backend-graphql", "kind": "network", "methods": ["POST"], "urlContains": "be.example.test/graphql"}]
    assert policy["forbidden"] == [{"id": "forbid-admin", "kind": "network", "methods": [], "urlContains": "/admin"}]
    assert "method" not in policy["allowed"][0]


@pytest.mark.parametrize(
    ("side_effect_class", "expected_mode"),
    [
        ("none", "observe"),
        ("authenticated-read", "observe"),
        ("write", "enforce"),
        ("external-notification", "enforce"),
    ],
)
def test_generated_run_request_materializes_core_required_policy_mode(
    tmp_path,
    side_effect_class: str,
    expected_mode: str,
) -> None:
    record = create_write_policy_workspace(
        tmp_path,
        side_effects={"class": side_effect_class},
    )

    rendered = json.loads(render_run_request(record))

    assert rendered["sideEffectPolicy"] == {
        "class": side_effect_class,
        "mode": expected_mode,
    }
