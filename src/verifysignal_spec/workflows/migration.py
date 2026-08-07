from __future__ import annotations

from pathlib import Path
from typing import Any

from verifysignal_spec.workspace import layout
from verifysignal_spec.workspace.models import ArtifactReference, UseCaseRecord
from verifysignal_spec.workspace.repository import (
    load_document,
    load_registry,
    load_use_case,
    save_use_case,
)

from .models import WORKFLOW_MIGRATION_RESULT_SCHEMA, MigrationPlan


BROWSER_WORKFLOW_GUARDRAIL_COMPATIBILITY_NOTES = [
    "Public stage payload contracts are exposed through workflow info and preserved as portable workflow guidance rather than private source-derived schema hints.",
    "Existing browser use cases with empty baseUrl, targetUrl, or url parameters should be clarified before the next executable plan or implementation stage.",
    "Resolved target environments are stored as stage handoff decisions and merged into later plans or draft run requests when the value is non-secret.",
    "Selector, flow, data, and coverage repairs from runtime feedback require confirmation; deterministic metadata repairs remain safe to apply after approval.",
    "Gate intent, runtime feedback, and repair confirmation records are portable workflow fields and remain under .verifysignal/ workspace state.",
]


def compatibility_notes() -> list[str]:
    return list(BROWSER_WORKFLOW_GUARDRAIL_COMPATIBILITY_NOTES)


def migration_plans(project: Path, alias: str | None = None) -> list[MigrationPlan]:
    registry = load_registry(project)
    plans: list[MigrationPlan] = []
    for item in registry.get("useCases", []):
        item_alias = item.get("alias")
        if not item_alias or (alias and item_alias != alias):
            continue
        if not item.get("recordPath"):
            plans.append(
                MigrationPlan(
                    id=f"migrate-registry-record-path-{item_alias}",
                    reason="Registry entry is missing recordPath but references a recoverable use-case alias.",
                    affectedArtifacts=[f"{layout.WORKSPACE_DIR}/{layout.REGISTRY_FILE}"],
                    proposedActions=[
                        f"Create canonical use-case record for {item_alias}",
                        "Update registry entry to reference the canonical recordPath",
                    ],
                    destructive=False,
                    requiresApproval=True,
                )
            )
    return plans


def apply_migration(project: Path, migration_id: str) -> dict[str, Any]:
    plans = {plan.id: plan for plan in migration_plans(project)}
    plan = plans.get(migration_id)
    if not plan:
        return _result(migration_id, "blocked", warnings=["Migration plan is unknown or no longer current."])
    if plan.destructive:
        return _result(migration_id, "blocked", warnings=["Destructive migrations are not applied by this command."])

    alias = migration_id.removeprefix("migrate-registry-record-path-")
    registry = load_registry(project)
    item = next((entry for entry in registry.get("useCases", []) if entry.get("alias") == alias), None)
    if not item or item.get("recordPath"):
        return _result(migration_id, "blocked", warnings=["Migration plan is stale; registry entry no longer matches the expected malformed state."])

    alias = layout.ensure_path_safe_alias(alias)
    try:
        record = load_use_case(project, alias)
    except FileNotFoundError:
        record = UseCaseRecord(
            alias=alias,
            title=str(item.get("title") or alias.replace("-", " ").title()),
            description=str(item.get("description") or item.get("title") or alias),
            targetSurface=str(item.get("targetSurface") or "browser"),
            status=item.get("runnableStatus") or item.get("status") or "draft",
        )
        run_request = item.get("runRequest")
        if isinstance(run_request, str):
            record.runRequest = ArtifactReference(path=run_request, kind="run-request", generated=run_request.startswith(".verifysignal/"))
        skills = item.get("skills") or []
        if isinstance(skills, list):
            record.skills = [
                ArtifactReference(path=str(skill), kind="skill", generated=str(skill).startswith(".verifysignal/"))
                for skill in skills
                if isinstance(skill, str)
            ]
            record.mainSkill = record.skills[0] if record.skills else None
    save_use_case(project, record)
    return _result(
        migration_id,
        "applied",
        written=[
            f"{layout.WORKSPACE_DIR}/{layout.REGISTRY_FILE}",
            f"{layout.WORKSPACE_DIR}/{layout.USE_CASES_DIR}/{alias}.yaml",
        ],
        preserved=[f"{layout.WORKSPACE_DIR}/{layout.WORKFLOWS_DIR}/{layout.WORKFLOW_USE_CASES_DIR}/{alias}/spec.md"],
    )


def _result(
    migration_id: str,
    status: str,
    *,
    written: list[str] | None = None,
    preserved: list[str] | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "schemaVersion": WORKFLOW_MIGRATION_RESULT_SCHEMA,
        "migrationId": migration_id,
        "status": status,
        "writtenArtifacts": written or [],
        "preservedArtifacts": preserved or [],
        "warnings": warnings or [],
    }
