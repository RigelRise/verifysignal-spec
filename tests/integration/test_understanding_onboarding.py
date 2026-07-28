from __future__ import annotations

from verifysignal_spec.workspace.repository import load_document
from verifysignal_spec.workflows.stage_persistence import persist_stage


def representative_understanding_payload() -> dict:
    return {
        "repositorySummary": "Representative app with public and branch-heavy routes.",
        "localStartInstructions": "npm run dev",
        "git": {
            "available": True,
            "hash": "eb58ef8111e8e6bfd090303ef417ef0a6c7609a6",
            "branch": "feature/multi-actor",
        },
        "safeInspectionPaths": ["app/", "src/"],
        "blockedSensitivePaths": [".env.local"],
        "coverageInventory": {
            "status": "partial",
            "partialInventoryReasons": ["Admin routes not inspected."],
            "sourceFilesVisited": 7,
            "items": [
                {"id": "route-home", "surfaceType": "route", "path": "/", "title": "Home", "sourceRefs": ["app/(public)/page.tsx"]},
                {
                    "id": "route-project",
                    "surfaceType": "route",
                    "path": "/project/[path]",
                    "title": "Project",
                    "sourceRefs": ["app/(public)/project/[path]/page.tsx"],
                    "priority": "high",
                },
            ],
            "candidateUseCases": [
                {
                    "alias": "home-page-unauth",
                    "surface": "/",
                    "behavior": "Public home page renders stable visible content.",
                    "rationale": "Trivial public read-only first-run candidate.",
                    "confidence": "high",
                    "priority": "medium",
                },
                {
                    "alias": "project-multi-actor-add-people",
                    "surface": "/project/[path]",
                    "behavior": "Active branch flow writes contributors for an authenticated BA user.",
                    "rationale": "Branch-relevant but not first-run simple.",
                    "confidence": "high",
                    "priority": "critical",
                    "knownRuntimeRequirements": ["credential:ba-user", "write operation"],
                },
            ],
        },
    }


def test_understand_persist_accepts_public_git_hash_and_normalizes_traceability(tmp_path) -> None:
    result = persist_stage(tmp_path, "understand", scope="all", payload=representative_understanding_payload())

    assert result["status"] == "persisted"
    context = load_document(tmp_path / ".verifysignal/product-context.yaml", default={})
    assert context["schemaVersion"] == "verifysignal-spec-product-context/v1"
    assert context["workspaceKind"] == "repository"
    assert context["understandingMode"] == "repository"
    assert context["repositorySummary"] == representative_understanding_payload()["repositorySummary"]
    assert context["localStartInstructions"] == "npm run dev"
    assert context["understanding"]["generatedGitHash"].startswith("eb58ef8")
    assert context["understanding"]["mode"] == "repository"
    assert context["understanding"]["sourceTraceabilityStatus"] == "normalized"
    assert context["understanding"]["partialInventoryReasons"] == ["Admin routes not inspected."]
    aliases = [item["alias"] for item in context["candidateUseCases"]]
    assert aliases[0] == "home-page-unauth"
    assert context["candidateUseCases"][0]["sourceInventoryItems"] == ["route-home"]


def test_understand_invalid_payload_reports_actionable_traceability_guidance(tmp_path) -> None:
    payload = representative_understanding_payload()
    payload["coverageInventory"] = {
        "items": [],
        "candidateUseCases": [{"alias": "orphan", "behavior": "No source.", "rationale": "No source."}],
    }

    result = persist_stage(tmp_path, "understand", scope="all", payload=payload)

    assert result["status"] == "invalid"
    assert "sourceInventoryItems" in result["blockers"][0]["message"]
    assert "coverageInventory.items" in result["blockers"][0]["message"]
