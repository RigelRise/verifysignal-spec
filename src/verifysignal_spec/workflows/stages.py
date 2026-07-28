from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from verifysignal_spec.workspace.product_context import load_product_context, save_understanding_metadata
from verifysignal_spec.workspace.repository import now_iso

from . import repository
from .prerequisites import current_git_hash
from .repository_context import collect_safe_repository_context
from .stage_documents import write_global_understanding, write_understanding_snapshot


def initialize_understanding(project: Path, alias: str | None = None, goal: str | None = None) -> dict[str, Any]:
    repository.ensure_workflow_workspace(project, alias)
    collected = collect_safe_repository_context(project)
    context = load_product_context(project)
    context.setdefault("repositorySummary", "")
    context["safeInspectionPaths"] = collected["safeInspectionPaths"]
    context["blockedSensitivePaths"] = collected["blockedSensitivePaths"]
    if goal:
        goals = list(context.get("validationGoals", []))
        if goal not in goals:
            goals.append(goal)
        context["validationGoals"] = goals
    git_hash = current_git_hash(project)
    context["candidateUseCases"] = _candidate_use_cases(context, goal)
    save_understanding_metadata(
        project,
        context,
        generated_at=now_iso(),
        generated_git_hash=git_hash,
        git_available=git_hash is not None,
        stale_reasons=[],
    )
    write_global_understanding(project, context)
    if alias:
        write_understanding_snapshot(project, alias, {**context, "useCaseFocus": goal or alias})
    return {"alias": alias, "globalUnderstanding": ".verifysignal/workflows/understanding.md", "safeInspectionPaths": collected["safeInspectionPaths"], "blockedSensitivePaths": collected["blockedSensitivePaths"]}


def _candidate_use_cases(context: dict[str, Any], goal: str | None = None) -> list[dict[str, Any]]:
    source_context = list(context.get("safeInspectionPaths", []))[:3] or ["product-context.yaml"]
    if goal:
        return [
            {
                "candidateAlias": _candidate_alias(goal),
                "title": _candidate_title(goal),
                "behavior": goal,
                "targetSurface": "Primary browser surface",
                "expectedOutcome": "The user-visible success condition is confirmed.",
                "rationale": "The requested validation goal should be grounded in product understanding before artifact planning.",
                "sourceContext": source_context,
                "confidence": "medium",
            }
        ]
    product_name = str(context.get("productName") or "application")
    return [
        {
            "candidateAlias": _candidate_alias(product_name),
            "title": f"Validate {product_name} primary flow",
            "behavior": "A representative user completes a high-value browser flow.",
            "targetSurface": "Primary browser surface",
            "expectedOutcome": "The expected product outcome is visible and stable.",
            "rationale": "A primary flow is a practical starting point when no specific validation goal was provided.",
            "sourceContext": source_context,
            "confidence": "low",
        }
    ]


def _candidate_alias(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return (slug[:40].strip("-") or "primary-flow")


def _candidate_title(value: str) -> str:
    text = value.strip().rstrip(".")
    if text.lower().startswith("validate "):
        return text[0].upper() + text[1:]
    return f"Validate {text}"
