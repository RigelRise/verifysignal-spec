from __future__ import annotations

from tests.fixtures.workflows.browser_first_understanding import (
    browser_understanding_payload,
)
from verifysignal_spec.workspace.repository import load_document, save_document
from verifysignal_spec.workspace.models import UnderstandingFreshnessState
from verifysignal_spec.workflows.prerequisites import check_prerequisites
from verifysignal_spec.workflows.stage_persistence import persist_stage


def test_stale_inventory_context_blocks_for_refresh() -> None:
    state = UnderstandingFreshnessState.from_context(
        stale=True,
        workflow_context="specify",
        reasons=["understanding older than threshold"],
    )

    assert state.status == "stale"
    assert state.policy == "block"
    assert state.recommendedAction == "refresh-understanding"


def test_alias_scoped_read_only_run_warns_when_impact_is_unaffected() -> None:
    state = UnderstandingFreshnessState.from_context(
        stale=True,
        workflow_context="run",
        use_case_impact="unaffected",
        side_effect_class="none",
    )

    assert state.policy == "warn"
    assert state.recommendedAction == "continue"


def test_alias_scoped_write_run_requires_confirmation_when_impact_unknown() -> None:
    state = UnderstandingFreshnessState.from_context(
        stale=True,
        workflow_context="run",
        use_case_impact="unknown",
        side_effect_class="write",
    )

    assert state.policy == "requires-confirmation"
    assert state.recommendedAction == "confirm"


def test_alias_scoped_affected_run_requires_validation_not_understand() -> None:
    state = UnderstandingFreshnessState.from_context(
        stale=True,
        workflow_context="run",
        use_case_impact="affected",
        side_effect_class="write",
    )

    assert state.policy == "block"
    assert state.recommendedAction == "validate"


def test_browser_first_freshness_is_age_based_without_git(tmp_path) -> None:
    result = persist_stage(
        tmp_path,
        "understand",
        scope="all",
        payload=browser_understanding_payload(),
    )
    assert result["status"] == "persisted"

    context_path = tmp_path / ".verifysignal/product-context.yaml"
    context = load_document(context_path, default={})
    context["understanding"]["generatedAt"] = "2026-01-01T00:00:00Z"
    context["understanding"]["generatedGitHash"] = None
    context["understanding"]["gitAvailable"] = False
    save_document(context_path, context)

    readiness = check_prerequisites(tmp_path, "specify")

    assert readiness["status"] == "stale"
    assert [item["code"] for item in readiness["staleReasons"]] == ["age"]
