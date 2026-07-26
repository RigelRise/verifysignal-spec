from __future__ import annotations

from copy import deepcopy
from typing import Any


OBSERVED_AT = "2026-07-26T18:00:00Z"


def browser_understanding_payload(
    *,
    candidate_count: int = 3,
    mode: str = "browser-first",
    locator: str = "https://App.Example.test/projects?invite=do-not-persist#members",
) -> dict[str, Any]:
    surfaces = [
        ("projects-list", "/projects", "Projects", "Show the signed-in user's projects.", "high"),
        ("project-details", "/projects/alpha", "Project details", "Show one project's details.", "high"),
        ("account-settings", "/settings", "Account settings", "Show the signed-in user's settings.", "medium"),
        ("activity-feed", "/activity", "Activity", "Show recent project activity.", "medium"),
        ("help-center", "/help", "Help", "Show product help content.", "low"),
    ][:candidate_count]
    items: list[dict[str, Any]] = []
    signals: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    for signal_id, path, title, behavior, priority in surfaces:
        item_id = f"surface-{signal_id}"
        items.append(
            {
                "id": item_id,
                "surfaceType": "route",
                "path": path,
                "title": title,
                "sourceRefs": [],
                "userFacing": True,
                "inventoryStatus": "covered",
                "candidateUseCaseRefs": [signal_id],
                "priority": priority,
                "productSignalRefs": [signal_id],
                "provenance": "browser",
            }
        )
        signals.append(
            {
                "id": signal_id,
                "kind": "surface",
                "surface": path,
                "summary": f"{title} is visible to the signed-in user.",
                "evidence": [f"A {title} heading and its primary content were visible."],
                "provenance": "browser",
                "observedAt": OBSERVED_AT,
                "confidence": "high",
                "inventoryItemRefs": [item_id],
            }
        )
        candidates.append(
            {
                "alias": signal_id,
                "surface": path,
                "behavior": behavior,
                "sourceInventoryItems": [item_id],
                "rationale": "Stable user-visible behavior observed in the live product.",
                "confidence": "high",
                "inventorySourceStatus": "complete",
                "priority": priority,
                "requiresEnvironment": True,
                "knownRuntimeRequirements": ["baseUrl"],
                "productSignalRefs": [signal_id],
                "provenance": "browser",
                "sideEffectClass": "none",
            }
        )
    status = "complete" if candidate_count >= 3 else "partial"
    reasons = [] if status == "complete" else ["Only one read-safe journey was observable within scope."]
    payload: dict[str, Any] = {
        "understandingMode": mode,
        "productSummary": "A project tracking application with authenticated project surfaces.",
        "targetEnvironment": {
            "kind": "live-url",
            "locator": locator,
            "environment": "staging",
            "reachabilityStatus": "authentication-required",
            "observedAt": OBSERVED_AT,
        },
        "explorationScope": {
            "status": status,
            "partialInventoryReasons": reasons,
        },
        "productSignals": signals,
        "gaps": reasons,
        "coverageInventory": {
            "status": status,
            "generatedAt": OBSERVED_AT,
            "gitAvailable": False,
            "sourceFilesVisited": 0,
            "sourceTraceabilityStatus": "missing",
            "partialInventoryReasons": reasons,
            "items": items,
            "candidateUseCases": candidates,
        },
    }
    if mode == "hybrid":
        payload.update(
            {
                "repositorySummary": payload["productSummary"],
                "localStartInstructions": "npm run dev",
                "generatedGitHash": "abc123",
                "gitAvailable": True,
                "safeInspectionPaths": ["src/"],
            }
        )
    return deepcopy(payload)
