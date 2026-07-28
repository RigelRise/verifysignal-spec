from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from verifysignal_spec.workspace.models import ArtifactReference, RuntimeInputRequirement, UseCaseRecord
from verifysignal_spec.workspace.repository import init_workspace, load_document, save_document, save_use_case
from verifysignal_spec.workflows.models import ArtifactPlan
from verifysignal_spec.workflows.repository import save_artifact_plan


PUBLIC_ALIAS = "home-page-unauth"
BRANCH_ALIAS = "project-multi-actor-add-people"
AUTH_ALIAS = "settings-account-auth"
REAL_TARGET = "https://app.example.test"


def candidate(
    alias: str,
    *,
    surface: str = "/",
    behavior: str = "Public page renders stable visible content.",
    source: str = "route-home",
    priority: str = "medium",
    confidence: str = "high",
    requirements: list[str] | None = None,
    rationale: str | None = None,
    side_effect_class: str = "none",
    grounding_status: str = "observed",
) -> dict[str, Any]:
    return {
        "alias": alias,
        "surface": surface,
        "behavior": behavior,
        "sourceInventoryItems": [source],
        "rationale": rationale or behavior,
        "priority": priority,
        "confidence": confidence,
        "requiresEnvironment": True,
        "knownRuntimeRequirements": requirements or ["baseUrl"],
        "sideEffectClass": side_effect_class,
        "groundingStatus": grounding_status,
    }


def inventory_with_public_and_branch_candidates() -> dict[str, Any]:
    return {
        "status": "complete",
        "generatedAt": "2026-05-30T00:00:00Z",
        "generatedGitHash": "abc1234",
        "items": [
            {
                "id": "route-home",
                "surfaceType": "route",
                "path": "/",
                "title": "Public home",
                "sourceRefs": ["app/(public)/page.tsx"],
                "priority": "medium",
            },
            {
                "id": "route-project",
                "surfaceType": "route",
                "path": "/project/[path]",
                "title": "Project page",
                "sourceRefs": ["app/(public)/project/[path]/page.tsx"],
                "priority": "high",
            },
            {
                "id": "route-settings",
                "surfaceType": "route",
                "path": "/settings",
                "title": "Settings",
                "sourceRefs": ["app/(protected)/settings/page.tsx"],
                "priority": "high",
            },
        ],
        "candidateUseCases": [
            candidate(
                PUBLIC_ALIAS,
                behavior="Public unauthenticated home page renders stable hero and table content.",
                priority="medium",
            ),
            candidate(
                BRANCH_ALIAS,
                surface="/project/[path]",
                behavior="Active branch multi-actor add people flow writes project contributors for a BA Marketing user.",
                source="route-project",
                priority="critical",
                requirements=["baseUrl", "credential:ba-marketing-user", "write operation", "active branch"],
                rationale="Branch-relevant feature but setup-heavy for a first run.",
                side_effect_class="write",
                grounding_status="authentication-required",
            ),
            candidate(
                AUTH_ALIAS,
                surface="/settings",
                behavior="Authenticated settings page renders account controls.",
                source="route-settings",
                priority="high",
                requirements=["baseUrl", "credential:user"],
                grounding_status="authentication-required",
            ),
        ],
    }


def create_onboarding_product_context(project: Path, *, target: str = REAL_TARGET, inventory: dict[str, Any] | None = None) -> Path:
    init_workspace(project)
    context = load_document(project / ".verifysignal/product-context.yaml", default={}) or {}
    context.update(
        {
            "repositorySummary": "Fixture app with a trivial public flow and a complex branch-relevant flow.",
            "localStartInstructions": "npm run dev",
            "knownRuntimeRequirements": [{"name": "baseUrl", "value": target}],
            "coverageInventory": inventory or inventory_with_public_and_branch_candidates(),
        }
    )
    context["candidateUseCases"] = context["coverageInventory"].get("candidateUseCases", [])
    context["understanding"] = {
        "generatedAt": "2026-05-30T00:00:00Z",
        "generatedGitHash": "abc1234",
        "gitAvailable": True,
        "inventoryStatus": context["coverageInventory"].get("status", "partial"),
    }
    save_document(project / ".verifysignal/product-context.yaml", context)
    (project / ".verifysignal/workflows").mkdir(parents=True, exist_ok=True)
    (project / ".verifysignal/workflows/understanding.md").write_text("# Understanding\n", encoding="utf-8")
    return project


def create_onboarding_repository(
    project: Path,
    *,
    target: str = REAL_TARGET,
    inventory: dict[str, Any] | None = None,
    with_artifacts: bool = True,
) -> Path:
    create_onboarding_product_context(project, target=target, inventory=inventory)
    if with_artifacts:
        for alias in [PUBLIC_ALIAS, BRANCH_ALIAS, AUTH_ALIAS]:
            create_use_case(project, alias, target=target, credential=alias != PUBLIC_ALIAS)
    return project


def create_use_case(project: Path, alias: str, *, target: str = REAL_TARGET, credential: bool = False) -> None:
    run_request = f".verifysignal/run-requests/{alias}.yaml"
    skill = f".verifysignal/skills/{alias}.browser.md"
    (project / ".verifysignal/run-requests").mkdir(parents=True, exist_ok=True)
    (project / ".verifysignal/skills").mkdir(parents=True, exist_ok=True)
    (project / run_request).write_text(json.dumps({"parameters": {"baseUrl": target}}, indent=2), encoding="utf-8")
    (project / skill).write_text("# Browser skill\n\nValidate the fixture page.\n", encoding="utf-8")
    credential_groups = [{"name": "qa-user", "description": "Runtime-only credential reference"}] if credential else []
    save_use_case(
        project,
        UseCaseRecord(
            alias=alias,
            title=alias.replace("-", " ").title(),
            description="Golden path onboarding fixture use case.",
            status="ready",
            runRequest=ArtifactReference(path=run_request, kind="run-request", id=f"request.{alias}", version="1.0.0"),
            mainSkill=ArtifactReference(path=skill, kind="skill", id=f"skill.{alias}", version="1.0.0"),
            skills=[ArtifactReference(path=skill, kind="skill", id=f"skill.{alias}", version="1.0.0")],
            runtimeInputs=[RuntimeInputRequirement(name="baseUrl", required=True, source="default", persistValue=False)],
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
                {"id": "overview-data-card", "description": "Rendered overview data is visible", "required": True},
                {"id": "projects-tab-content", "description": "Rendered project content is visible", "required": True},
                {"id": "overview-profile-query", "description": "Data query completes", "required": True},
            ],
        ),
    )


def no_ideal_inventory() -> dict[str, Any]:
    inventory = inventory_with_public_and_branch_candidates()
    inventory["candidateUseCases"] = [
        candidate(
            "authenticated-lowest-risk",
            surface="/dashboard",
            behavior="Authenticated dashboard renders visible read-only account data.",
            source="route-settings",
            requirements=["baseUrl", "credential:user"],
            priority="medium",
        ),
        candidate(
            BRANCH_ALIAS,
            surface="/project/[path]",
            behavior="Active branch multi-actor add people flow writes project contributors for a BA Marketing user.",
            source="route-project",
            priority="critical",
            requirements=["baseUrl", "credential:ba-marketing-user", "write operation", "active branch"],
        ),
    ]
    return inventory


def assert_stage_card_shape(card: dict[str, Any]) -> None:
    for field in ["stageId", "title", "statusMarker", "summary", "whyItMatters", "primaryEvidence", "nextAction"]:
        assert card.get(field), f"missing stage card field: {field}"


def assert_guidance_shape(guide: dict[str, Any]) -> None:
    for field in [
        "terminalTitle",
        "terminalSummary",
        "generatedGuidePath",
        "nextCommand",
        "stageMarkers",
        "safetyBoundaries",
        "successSemantics",
        "plainTextFallback",
    ]:
        assert guide.get(field), f"missing onboarding guide field: {field}"


def assert_no_secret_findings(data: dict[str, Any]) -> None:
    from verifysignal_spec.workspace.validation import validate_no_secret_values

    findings = validate_no_secret_values(data)
    assert findings == []
