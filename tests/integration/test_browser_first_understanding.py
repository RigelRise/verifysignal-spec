from __future__ import annotations

from tests.fixtures.workflows.browser_first_understanding import (
    browser_understanding_alias_payload,
    browser_understanding_payload,
)
from verifysignal_spec.workspace.repository import load_document
from verifysignal_spec.workflows.first_run import build_first_run_recommendation
from verifysignal_spec.workflows.prerequisites import check_prerequisites
from verifysignal_spec.workflows.stage_persistence import persist_stage


def _workspace_text(project) -> str:
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((project / ".verifysignal").rglob("*"))
        if path.is_file()
    )


def test_browser_first_understanding_persists_in_non_git_engagement(tmp_path) -> None:
    assert not (tmp_path / ".git").exists()

    result = persist_stage(
        tmp_path,
        "understand",
        scope="all",
        payload=browser_understanding_payload(),
    )

    assert result["status"] == "persisted"
    assert result["understandingOnboarding"]["understandingMode"] == "browser-first"
    assert result["understandingOnboarding"]["productSignalCount"] == 4

    context = load_document(tmp_path / ".verifysignal/product-context.yaml", default={})
    assert context["schemaVersion"] == "verifysignal-spec-product-context/v1"
    assert context["workspaceKind"] == "engagement"
    assert context["understandingMode"] == "browser-first"
    assert context["repositorySummary"] == context["productSummary"]
    assert context["targetEnvironment"]["locator"] == "https://app.example.test/projects"
    assert context["targetEnvironment"]["origin"] == "https://app.example.test"
    assert context["understanding"]["mode"] == "browser-first"
    assert context["understanding"]["gitAvailable"] is False
    assert context["understanding"]["generatedGitHash"] is None
    assert context["understanding"]["candidateCount"] == 3
    assert context["understanding"]["provenanceTraceabilityStatus"] == "complete"
    assert context["coverageInventory"]["sourceFilesVisited"] == 0
    assert context["coverageInventory"]["sourceTraceabilityStatus"] == "missing"
    assert context["candidateUseCases"][0]["productSignalRefs"]
    assert context["candidateUseCases"][0]["groundingStatus"] == (
        "authentication-required"
    )
    assert context["knownRuntimeRequirements"] == [
        {"name": "baseUrl", "value": "https://app.example.test/projects"}
    ]

    durable = _workspace_text(tmp_path)
    assert "do-not-persist" not in durable
    assert "#members" not in durable
    assert "VerifySignal Product Understanding" in durable
    assert "Product Signals" in durable
    assert check_prerequisites(tmp_path, "specify")["status"] == "ready"

    recommendation = build_first_run_recommendation(tmp_path).to_dict()
    assert recommendation["status"] == "ready"
    assert recommendation["targetStatus"] == "resolved"
    assert recommendation["recommendedCandidate"]["alias"] in {
        item["alias"] for item in context["candidateUseCases"]
    }


def test_browser_first_candidate_shortfall_persists_as_partial(tmp_path) -> None:
    result = persist_stage(
        tmp_path,
        "understand",
        scope="all",
        payload=browser_understanding_payload(candidate_count=1),
    )

    assert result["status"] == "persisted"
    assert result["understandingOnboarding"]["status"] == "partial"
    assert result["warnings"]
    context = load_document(tmp_path / ".verifysignal/product-context.yaml", default={})
    assert context["coverageInventory"]["status"] == "partial"
    assert context["understanding"]["gaps"]


def test_forbidden_browser_capture_is_rejected_without_persisting_capture(tmp_path) -> None:
    payload = browser_understanding_payload()
    payload["productSignals"][0]["mcpSnapshot"] = "<button>Delete account</button>"

    result = persist_stage(tmp_path, "understand", scope="all", payload=payload)

    assert result["status"] == "invalid"
    assert "mcpSnapshot" in result["blockers"][0]["message"]
    durable = _workspace_text(tmp_path)
    assert "Delete account" not in durable


def test_existing_repository_payload_remains_compatible(tmp_path) -> None:
    from tests.integration.test_understanding_onboarding import representative_understanding_payload

    result = persist_stage(
        tmp_path,
        "understand",
        scope="all",
        payload=representative_understanding_payload(),
    )

    assert result["status"] == "persisted"
    context = load_document(tmp_path / ".verifysignal/product-context.yaml", default={})
    assert context["understandingMode"] == "repository"
    assert context["understanding"]["mode"] == "repository"
    assert context["repositorySummary"].startswith("Representative app")


def test_hybrid_understanding_preserves_git_and_records_provenance_conflict(tmp_path) -> None:
    payload = browser_understanding_payload(mode="hybrid")
    payload["coverageInventory"]["generatedGitHash"] = "abc123"
    payload["coverageInventory"]["gitAvailable"] = True
    payload["coverageInventory"]["sourceFilesVisited"] = 4
    payload["coverageInventory"]["sourceTraceabilityStatus"] = "complete"
    payload["productSignals"][0]["provenance"] = "repository"
    payload["productSignals"][1]["provenance"] = "browser"
    payload["productSignals"][2]["provenance"] = "hybrid"
    payload["gaps"] = [
        "Conflict: repository copy differs from the browser-observed heading."
    ]

    result = persist_stage(tmp_path, "understand", scope="all", payload=payload)

    assert result["status"] == "persisted"
    assert result["understandingOnboarding"]["understandingMode"] == "hybrid"
    assert result["understandingOnboarding"]["provenanceTraceabilityStatus"] == "conflicted"
    context = load_document(tmp_path / ".verifysignal/product-context.yaml", default={})
    assert context["workspaceKind"] == "hybrid"
    assert context["understanding"]["generatedGitHash"] == "abc123"
    assert context["understanding"]["gitAvailable"] is True
    assert context["coverageInventory"]["generatedGitHash"] == "abc123"
    assert context["coverageInventory"]["gitAvailable"] is True
    assert context["coverageInventory"]["sourceFilesVisited"] == 4
    assert context["coverageInventory"]["sourceTraceabilityStatus"] == "complete"
    assert context["understanding"]["provenanceTraceabilityStatus"] == "conflicted"
    assert context["understanding"]["gaps"] == payload["gaps"]


def test_alias_payload_persists_the_same_canonical_context(tmp_path) -> None:
    canonical_project = tmp_path / "canonical"
    alias_project = tmp_path / "alias"

    canonical = persist_stage(
        canonical_project,
        "understand",
        scope="all",
        payload=browser_understanding_payload(),
    )
    aliased = persist_stage(
        alias_project,
        "understand",
        scope="all",
        payload=browser_understanding_alias_payload(),
    )

    assert canonical["status"] == "persisted"
    assert aliased["status"] == "persisted"
    canonical_context = load_document(
        canonical_project / ".verifysignal/product-context.yaml", default={}
    )
    alias_context = load_document(
        alias_project / ".verifysignal/product-context.yaml", default={}
    )
    for key in [
        "targetEnvironment",
        "explorationScope",
        "productSignals",
        "coverageInventory",
        "candidateUseCases",
    ]:
        assert alias_context[key] == canonical_context[key]


def test_invalid_nested_payload_is_atomic_and_reports_the_field_path(tmp_path) -> None:
    payload = browser_understanding_payload()
    payload["coverageInventory"]["items"][0]["unexpected"] = "discarded-before"

    result = persist_stage(tmp_path, "understand", scope="all", payload=payload)

    assert result["status"] == "invalid"
    assert (
        "coverageInventory.items[0].unexpected"
        in result["blockers"][0]["message"]
    )
    assert not (tmp_path / ".verifysignal").exists()


def test_zero_observation_host_failure_never_becomes_product_understanding(
    tmp_path,
) -> None:
    payload = browser_understanding_payload()
    payload["productSummary"] = (
        "Product understanding is unavailable because no headed browser "
        "backend was connected."
    )
    payload["explorationScope"]["status"] = "blocked"
    payload["explorationScope"]["partialInventoryReasons"] = [
        "No headed browser backend was available."
    ]
    payload["productSignals"] = []
    payload["coverageInventory"]["status"] = "partial"
    payload["coverageInventory"]["items"] = []
    payload["coverageInventory"]["candidateUseCases"] = []
    payload["coverageInventory"]["partialInventoryReasons"] = [
        "No headed browser backend was available."
    ]
    payload["gaps"] = ["No headed browser backend was available."]

    result = persist_stage(
        tmp_path,
        "understand",
        scope="all",
        payload=payload,
    )

    assert result["status"] == "invalid"
    assert "at least one productSignals item" in result["blockers"][0][
        "message"
    ]
    assert not (tmp_path / ".verifysignal").exists()
