from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from verifysignal_spec.workspace.models import ArtifactReference, RuntimeInputRequirement, UseCaseRecord
from verifysignal_spec.workspace.repository import init_workspace, load_document, save_document, save_use_case
from verifysignal_spec.workflows.models import ArtifactPlan
from verifysignal_spec.workflows.repository import save_artifact_plan


PUBLIC_ALIAS = "home-page-unauth"
AUTH_ALIAS = "account-settings-auth"
REPAIRABLE_ALIAS = "home-page-repairable"
CONDITIONAL_ALIAS = "activity-data-conditional"
REAL_TARGET = "https://app.example.test"


def create_golden_path_workspace(
    project: Path,
    *,
    target: str = REAL_TARGET,
    include_credentials: bool = True,
    include_unreachable_target: bool = False,
) -> Path:
    init_workspace(project)
    product_context = load_document(project / ".verifysignal/product-context.yaml", default={}) or {}
    product_context["repositorySummary"] = "Test target with public and authenticated browser validation candidates."
    product_context["localStartInstructions"] = "npm run dev"
    product_context["knownRuntimeRequirements"] = [{"name": "baseUrl", "value": target}]
    product_context["coverageInventory"] = coverage_inventory(include_credentials=include_credentials)
    if include_unreachable_target:
        product_context["knownRuntimeRequirements"] = [{"name": "baseUrl", "value": "http://127.0.0.1:9"}]
    save_document(project / ".verifysignal/product-context.yaml", product_context)

    create_use_case(project, PUBLIC_ALIAS, target=target)
    create_use_case(project, AUTH_ALIAS, target=target, credential=True)
    create_use_case(project, REPAIRABLE_ALIAS, target=target)
    create_use_case(project, CONDITIONAL_ALIAS, target=target)
    return project


def coverage_inventory(*, include_credentials: bool = False) -> dict[str, Any]:
    return {
        "status": "complete",
        "generatedAt": "2026-05-30T00:00:00Z",
        "items": [
            {"id": "route-home", "surfaceType": "route", "path": "/", "title": "Home", "priority": "critical"},
            {"id": "route-settings", "surfaceType": "route", "path": "/settings", "title": "Settings", "priority": "high"},
            {"id": "route-activity", "surfaceType": "route", "path": "/", "title": "Activity", "priority": "medium"},
        ],
        "candidateUseCases": [
            {
                "alias": PUBLIC_ALIAS,
                "surface": "/",
                "behavior": "Public home page renders hero, activity, and ranked entity tables for an unauthenticated visitor.",
                "sourceInventoryItems": ["route-home"],
                "rationale": "Public, no credentials, simple rendered evidence, and stable first-run value.",
                "confidence": "high",
                "priority": "critical",
                "requiresEnvironment": True,
                "knownRuntimeRequirements": ["baseUrl"],
                "sideEffectClass": "none",
                "groundingStatus": "observed",
            },
            {
                "alias": AUTH_ALIAS,
                "surface": "/settings/account",
                "behavior": "Authenticated account settings render after sign-in.",
                "sourceInventoryItems": ["route-settings"],
                "rationale": "Useful but requires credentials, so it is not the first-run default.",
                "confidence": "high",
                "priority": "high",
                "requiresEnvironment": True,
                "knownRuntimeRequirements": ["baseUrl", "credential:qa-user"] if include_credentials else ["baseUrl"],
                "sideEffectClass": "none",
                "groundingStatus": "authentication-required",
            },
            {
                "alias": CONDITIONAL_ALIAS,
                "surface": "/",
                "behavior": "Activity section renders when seeded activity data exists.",
                "sourceInventoryItems": ["route-activity"],
                "rationale": "Data-dependent section is useful after the stable public candidate.",
                "confidence": "medium",
                "priority": "medium",
                "requiresEnvironment": True,
                "knownRuntimeRequirements": ["baseUrl", "seeded activity data"],
                "sideEffectClass": "none",
                "groundingStatus": "observed",
            },
        ],
    }


def create_use_case(project: Path, alias: str, *, target: str = REAL_TARGET, credential: bool = False) -> None:
    run_request = f".verifysignal/run-requests/{alias}.yaml"
    skill = f".verifysignal/skills/{alias}.browser.md"
    (project / ".verifysignal/run-requests").mkdir(parents=True, exist_ok=True)
    (project / ".verifysignal/skills").mkdir(parents=True, exist_ok=True)
    (project / run_request).write_text(json.dumps({"parameters": {"baseUrl": target}}, indent=2), encoding="utf-8")
    (project / skill).write_text("# Browser skill\n", encoding="utf-8")
    runtime_inputs = [
        RuntimeInputRequirement(name="baseUrl", required=True, source="default", persistValue=False),
    ]
    credential_groups: list[dict[str, str]] = []
    if credential:
        credential_groups.append({"name": "qa-user", "description": "Runtime-only QA user credential reference"})
    save_use_case(
        project,
        UseCaseRecord(
            alias=alias,
            title=alias.replace("-", " ").title(),
            description="Golden path fixture use case.",
            status="ready",
            runRequest=ArtifactReference(path=run_request, kind="run-request", id=f"request.{alias}", version="1.0.0"),
            mainSkill=ArtifactReference(path=skill, kind="skill", id=f"skill.{alias}", version="1.0.0"),
            skills=[ArtifactReference(path=skill, kind="skill", id=f"skill.{alias}", version="1.0.0")],
            runtimeInputs=runtime_inputs,
            credentialGroups=credential_groups,
        ),
    )
    save_artifact_plan(
        project,
        ArtifactPlan(
            useCaseAlias=alias,
            runRequest=run_request,
            mainSkill=skill,
            runtimeInputs=[{"name": "baseUrl", "required": True, "default": target}],
            validationGates=[
                {"id": "visible-content", "description": "Rendered content is visible", "required": True},
                {"id": "no-redirect", "description": "No unexpected redirect occurred", "required": True},
            ],
        ),
    )


def create_canonical_example_workspaces(root: Path) -> dict[str, dict[str, Any]]:
    examples: dict[str, dict[str, Any]] = {
        "public-unauthenticated": {
            "alias": PUBLIC_ALIAS,
            "expectedStatus": "pass",
            "target": REAL_TARGET,
            "evidence": ["hero visible", "activity visible", "ranked table visible"],
        },
        "authenticated-secret-safe": {
            "alias": AUTH_ALIAS,
            "expectedStatus": "pass",
            "target": REAL_TARGET,
            "credentialPolicy": "runtime-reference-only",
            "credentialRefs": ["QA_USER_EMAIL", "QA_USER_PASSWORD"],
        },
        "repairable-failure": {
            "alias": REPAIRABLE_ALIAS,
            "expectedStatus": "repaired-pass",
            "target": REAL_TARGET,
            "repairCategory": "wait-strategy",
            "failureMode": "activity skeletons still visible before slider evidence appears",
        },
        "conditional-data": {
            "alias": CONDITIONAL_ALIAS,
            "target": REAL_TARGET,
            "condition": "activity data exists in the target environment",
            "allowedOutcomes": ["pass", "fail", "blocked", "not-evaluated"],
        },
    }
    for key, metadata in examples.items():
        project = root / key
        create_golden_path_workspace(project, target=str(metadata["target"]))
        save_document(project / ".verifysignal/workflows/canonical-example.yaml", metadata)
        metadata["project"] = str(project)
    return examples
