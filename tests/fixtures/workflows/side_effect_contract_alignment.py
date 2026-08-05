from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from verifysignal_spec.workspace.models import ArtifactReference, RuntimeInputRequirement, UseCaseRecord
from verifysignal_spec.workspace.repository import init_workspace, save_use_case
from tests.fixtures.workflows.entitlement_preflight_recovery import save_protected_ready_snapshot

from .write_rerun_identity import write_minimal_artifacts


def supported_side_effect_contract(*, runtime_dom_supported: bool | None = None, static_dom_supported: bool = False) -> dict[str, Any]:
    confirmation_types = ["finalUrl", "runtimeOutput", "allowedNetworkObservation"]
    if static_dom_supported or runtime_dom_supported is True:
        confirmation_types.insert(2, "dom")
    guardrails: dict[str, Any] = {
        "status": "supported",
        "policyClasses": ["none", "authenticated-read", "write", "external-notification", "unknown"],
        "policyModes": ["observe", "warn", "enforce"],
        "confirmationSignalTypes": confirmation_types,
        "confirmationSignals": {
            "supportedTypes": confirmation_types,
            "unsupportedTypes": [] if "dom" in confirmation_types else ["dom"],
            "unsupportedSignalError": "unsupported-confirmation-signal",
        },
        "runtimeOutputSources": ["finalUrl", "location", "dom", "network"],
    }
    if runtime_dom_supported is not None:
        guardrails["runtimeConfirmationSupport"] = [
            {"type": "dom", "status": "supported" if runtime_dom_supported else "unsupported"},
            {"type": "runtimeOutput", "status": "supported"},
            {"type": "finalUrl", "status": "supported"},
        ]
    return {"sections": {"sideEffectGuardrails": guardrails}}


def legacy_rules_policy(*, mode: str = "observe") -> dict[str, Any]:
    return {
        "class": "write",
        "mode": mode,
        "commitStepId": "confirm-publish-dialog",
        "rules": [
            {"id": "allow-backend-graphql", "effect": "allow", "match": {"urlContains": "be.example.test/graphql", "method": "POST"}},
            {"id": "forbid-admin", "effect": "forbid", "match": {"urlContains": "/admin"}},
        ],
        "confirmationSignals": [{"id": "created-project-url", "type": "runtimeOutput", "runtimeOutput": "createdProjectUrl", "urlContains": "/project"}],
    }


def templated_confirmation_policy(*, placeholder: str = "{{parameters.projectTitle}}") -> dict[str, Any]:
    return {
        "class": "write",
        "mode": "enforce",
        "commitStepId": "confirm-publish-dialog",
        "allowed": [{"id": "allow-backend-graphql", "kind": "network", "methods": ["POST"], "urlContains": "be.example.test/graphql"}],
        "confirmationSignals": [
            {
                "id": "published-title-confirmed",
                "type": "runtimeOutput",
                "reference": "publishedProjectTitleText",
                "expectedContains": placeholder,
                "required": True,
            },
            {
                "id": "created-project-url-confirmed",
                "type": "runtimeOutput",
                "reference": "createdProjectUrl",
                "expectedContains": "/project/",
                "required": True,
            },
        ],
    }


def conflicting_policy() -> dict[str, Any]:
    policy = legacy_rules_policy()
    policy["allowed"] = [{"id": "canonical-different", "urlContains": "api.example.test"}]
    return policy


def unsupported_dom_last_run(run_id: str = "dom-unsupported-run") -> dict[str, Any]:
    return {
        "runId": run_id,
        "status": "failed",
        "sideEffects": {
            "confirmationSignals": [
                {"id": "published-title-rendered", "type": "dom", "status": "unsupported", "code": "unsupported-confirmation-signal"}
            ]
        },
        "postCommitInterpretation": {
            "postCommit": False,
            "sideEffectMayExist": False,
            "failurePhase": "pre-commit",
            "sideEffectStatus": "unknown",
            "rerunRisk": "safe",
        },
    }


def blocked_write_last_run(run_id: str = "violated-run") -> dict[str, Any]:
    return {
        "runId": run_id,
        "status": "passed",
        "postCommitInterpretation": {
            "postCommit": True,
            "sideEffectMayExist": True,
            "failurePhase": "post-commit",
            "sideEffectStatus": "violated",
            "rerunRisk": "blocked",
        },
    }


def confirmable_write_last_run(run_id: str = "committed-run") -> dict[str, Any]:
    return {
        "runId": run_id,
        "status": "passed",
        "postCommitInterpretation": {
            "postCommit": True,
            "sideEffectMayExist": True,
            "failurePhase": "post-commit",
            "sideEffectStatus": "committed-confirmed",
            "rerunRisk": "requires-confirmation",
        },
    }


def supersede_review_payload(source_run_id: str = "violated-run") -> dict[str, Any]:
    return {
        "reviewId": "review-violated-run",
        "sourceRunId": source_run_id,
        "ownerDecision": "Treat the prior violations as expected telemetry/login traffic.",
        "evidenceSummary": "Public run outcome reached commit and verification passed; unmatched observations were policy-shape false positives.",
        "previousClassification": {"sideEffectStatus": "violated", "rerunRisk": "blocked"},
        "resultingClassification": {"sideEffectStatus": "committed-confirmed", "rerunRisk": "safe-with-new-inputs"},
        "reason": "Owner reviewed the public outcome and approved superseding the false-positive rerun risk.",
        "createdAt": "2026-06-18T00:00:00Z",
        "createdBy": "test-owner",
    }


def create_write_policy_workspace(
    project: Path,
    *,
    side_effects: dict[str, Any] | None = None,
    last_run: dict[str, Any] | None = None,
    protected_ready: bool = False,
) -> UseCaseRecord:
    init_workspace(project, core_cmd=os.environ.get("VERIFYSIGNAL_CORE_CMD", "verifysignal-core"))
    write_minimal_artifacts(project, "add-collaboration-project", parameters={"baseUrl": "https://example.test"})
    record = UseCaseRecord(
        alias="add-collaboration-project",
        title="Add Collaboration Project",
        description="Publish a collaboration project.",
        targetSurface="/",
        runRequest=ArtifactReference(
            path=".verifysignal/run-requests/add-collaboration-project.yaml",
            kind="run-request",
            id="request.add-collaboration-project",
            version="1.0.0",
        ),
        mainSkill=ArtifactReference(
            path=".verifysignal/skills/add-collaboration-project.browser.md",
            kind="skill",
            id="skill.add-collaboration-project",
            version="1.0.0",
        ),
        skills=[
            ArtifactReference(
                path=".verifysignal/skills/add-collaboration-project.browser.md",
                kind="skill",
                id="skill.add-collaboration-project",
                version="1.0.0",
            )
        ],
        runtimeInputs=[
            RuntimeInputRequirement(name="baseUrl", source="default", value="https://example.test"),
            RuntimeInputRequirement(name="projectTitle", source="generated", value="VerifySignal collab seed", refreshOnRerunAfterCommit=True),
        ],
        sideEffects=side_effects
        or {
            "class": "write",
            "mode": "enforce",
            "commitStepId": "confirm-publish-dialog",
            "allowed": [{"id": "allow-backend-graphql", "kind": "network", "methods": ["POST"], "urlContains": "be.example.test/graphql"}],
            "confirmationSignals": [{"id": "created-project-url", "type": "runtimeOutput", "runtimeOutput": "createdProjectUrl"}],
        },
        runtimeOutputs=[{"name": "createdProjectUrl", "source": "finalUrl", "publishAsNamedOutput": True, "resourceType": "collaboration-project"}],
        rerunPolicy={"afterNoCommit": "allowed", "afterCommit": "allowed-with-new-inputs", "refreshRuntimeInputs": ["projectTitle"]},
        sideEffectLifecycle={"cleanupPolicy": "manual", "cleanupRequired": True, "instructions": "Delete the created project in the DB."},
        resourceIdentity={
            "resourceType": "collaboration-project",
            "identityStrategy": "generated-input",
            "identityInput": "projectTitle",
            "collisionPolicy": "allow-duplicates",
            "targetScope": "https://example.test",
            "confidence": "confirmed",
        },
        artifactCapabilities={
            "capabilities": [
                "explicit-confirmation",
                "side-effect-lifecycle",
                "resource-identity",
                "generated-runtime-inputs",
                "write-activity-interpretation",
            ]
        },
        lastRun=last_run,
    )
    save_use_case(project, record)
    if protected_ready:
        record.status = "ready"
        save_use_case(project, record)
        save_protected_ready_snapshot(project, record.alias, side_effect_class="write")
    return record
