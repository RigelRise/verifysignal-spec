from __future__ import annotations

from verifysignal_spec.workspace.models import SideEffectDeclaration, RerunPolicy
from verifysignal_spec.workspace.validation import validate_side_effect_declaration


def _supported_contract() -> dict:
    return {
        "sections": {
            "sideEffectGuardrails": {
                "policyClasses": ["none", "authenticated-read", "write", "external-notification", "unknown"],
                "policyModes": ["observe", "warn", "enforce"],
                "confirmationSignalTypes": ["finalUrl", "runtimeOutput", "allowedNetworkObservation"],
                "confirmationSignals": {
                    "supportedTypes": ["finalUrl", "runtimeOutput", "allowedNetworkObservation"],
                    "unsupportedTypes": ["dom"],
                    "unsupportedSignalError": "unsupported-confirmation-signal",
                },
                "runtimeOutputSources": ["finalUrl", "location", "dom", "network"],
                "resultClassification": {
                    "failurePhases": ["pre-commit", "post-commit", "post-verification", "unknown"],
                    "rerunRisks": ["safe", "safe-with-new-inputs", "requires-confirmation", "blocked"],
                },
            }
        }
    }


def test_write_defaults_to_enforce_and_serializes_public_class_key() -> None:
    declaration = SideEffectDeclaration.from_dict({"class": "write", "commitStepId": "submit"})

    assert declaration.policyMode == "enforce"
    assert declaration.to_dict()["class"] == "write"
    assert "sideEffectClass" not in declaration.to_dict()


def test_read_only_declaration_does_not_require_write_metadata() -> None:
    declaration = SideEffectDeclaration.from_dict({"class": "none"})

    findings = validate_side_effect_declaration(declaration.to_dict(), core_contract=_supported_contract())

    assert findings == []


def test_read_only_declaration_blocks_when_the_unchanged_policy_has_an_unreviewed_violation() -> None:
    declaration = {
        "class": "none",
        "mode": "observe",
        "allowed": [],
        "forbidden": [],
    }
    findings = validate_side_effect_declaration(
        declaration,
        core_contract=_supported_contract(),
        runtime_outcomes=[
            {
                "runId": "run-policy-violation",
                "sideEffectPolicy": declaration,
                "sideEffects": {
                    "policy": {"class": "none", "mode": "observe"},
                    "violations": [
                        {
                            "code": "side-effect-class-none-violation",
                            "severity": "warning",
                            "message": "Unexpected POST",
                        }
                    ],
                },
                "postCommitInterpretation": {
                    "sideEffectStatus": "violated",
                    "rerunRisk": "blocked",
                },
            }
        ],
    )

    assert any(
        item["code"] == "side-effect-observation-review-required"
        and item["severity"] == "blocking"
        for item in findings
    )


def test_read_only_declaration_allows_rerun_after_an_explicit_policy_change_but_requires_clean_evidence() -> None:
    previous_policy = {
        "class": "none",
        "mode": "observe",
        "allowed": [],
        "forbidden": [],
    }
    current_policy = {
        "class": "none",
        "mode": "observe",
        "allowed": [
            {
                "id": "allow-analytics",
                "kind": "network",
                "methods": ["POST"],
                "urlContains": "/collect",
                "timing": "any",
            }
        ],
        "forbidden": [],
    }
    findings = validate_side_effect_declaration(
        current_policy,
        core_contract=_supported_contract(),
        runtime_outcomes=[
            {
                "runId": "run-policy-violation",
                "sideEffectPolicy": previous_policy,
                "sideEffects": {
                    "violations": [
                        {
                            "code": "side-effect-class-none-violation",
                            "severity": "warning",
                            "message": "Unexpected POST",
                        }
                    ]
                },
                "postCommitInterpretation": {
                    "sideEffectStatus": "violated",
                    "rerunRisk": "blocked",
                },
            }
        ],
    )

    assert not any(item["severity"] == "blocking" for item in findings)
    assert any(
        item["code"] == "side-effect-policy-changed-rerun-required"
        and item["severity"] == "warning"
        for item in findings
    )


def test_clean_read_only_run_supersedes_an_older_policy_violation() -> None:
    declaration = {
        "class": "none",
        "mode": "observe",
        "allowed": [],
        "forbidden": [],
    }
    findings = validate_side_effect_declaration(
        declaration,
        core_contract=_supported_contract(),
        runtime_outcomes=[
            {
                "runId": "run-clean",
                "sideEffectPolicy": declaration,
                "sideEffects": {"violations": []},
                "postCommitInterpretation": {
                    "sideEffectStatus": "not-observed",
                    "rerunRisk": "safe",
                },
            }
        ],
    )

    assert not any(
        item["code"]
        in {
            "side-effect-observation-review-required",
            "side-effect-policy-changed-rerun-required",
        }
        for item in findings
    )


def test_write_requires_commit_step_rerun_policy_and_local_envelope() -> None:
    declaration = SideEffectDeclaration.from_dict({"class": "write"})

    findings = validate_side_effect_declaration(declaration.to_dict(), core_contract=_supported_contract())
    codes = {item["code"] for item in findings}

    assert "side-effect-commit-step-missing" in codes
    assert "side-effect-envelope-missing" in codes
    assert "rerun-policy-missing" in codes


def test_write_accepts_allowed_rule_as_local_envelope() -> None:
    declaration = SideEffectDeclaration.from_dict(
        {
            "class": "write",
            "commitStepId": "submit",
            "allowed": [{"id": "create-resource", "kind": "network", "methods": ["POST"], "urlContains": "/resources"}],
        }
    )
    rerun_policy = RerunPolicy.from_dict({"afterNoCommit": "allowed", "afterCommit": "blocked"})

    findings = validate_side_effect_declaration(
        declaration.to_dict(),
        rerun_policy=rerun_policy.to_dict(),
        core_contract=_supported_contract(),
    )

    assert findings == []


def test_unsupported_core_contract_values_block_readiness() -> None:
    declaration = SideEffectDeclaration.from_dict(
        {
            "class": "write",
            "mode": "enforce",
            "commitStepId": "submit",
            "allowed": [{"id": "create-resource", "kind": "network", "methods": ["POST"], "urlContains": "/resources"}],
            "confirmationSignals": [{"id": "created-url", "type": "missingType"}],
        }
    )

    findings = validate_side_effect_declaration(
        declaration.to_dict(),
        rerun_policy={"afterNoCommit": "allowed", "afterCommit": "blocked"},
        core_contract=_supported_contract(),
    )

    assert any(item["code"] == "side-effect-confirmation-signal-unsupported" for item in findings)
