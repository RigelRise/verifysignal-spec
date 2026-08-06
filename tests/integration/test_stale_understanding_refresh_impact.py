from __future__ import annotations

from verifysignal_spec.workflows.prerequisites import check_prerequisites
from verifysignal_spec.workspace.models import RefreshImpactResult
from verifysignal_spec.workspace.repository import load_use_case, save_refresh_impact, save_use_case
from tests.fixtures.workflows.live_write_readiness import (
    create_live_write_readiness_workspace,
    save_ready_snapshot,
)
from tests.fixtures.workflows.prerequisites import create_stale_understanding_workspace


def test_stale_understanding_still_blocks_inventory_dependent_specify(tmp_path) -> None:
    create_stale_understanding_workspace(tmp_path)

    result = check_prerequisites(tmp_path, "specify")

    assert result["status"] == "stale"
    assert result["recommendedAction"] == "refresh-understanding"
    assert result["nextCommand"] == "/verifysignal-understand"


def test_alias_scoped_run_with_stale_understanding_does_not_force_global_understand(tmp_path) -> None:
    create_stale_understanding_workspace(tmp_path)
    create_live_write_readiness_workspace(tmp_path)
    record = load_use_case(tmp_path, "about-page-unauth")
    record.status = "ready"
    save_use_case(tmp_path, record)
    save_ready_snapshot(tmp_path, record.alias)

    result = check_prerequisites(tmp_path, "run", alias="about-page-unauth")

    assert result["status"] in {"ready", "stale"}
    assert result["canProceed"] is True
    assert result["nextCommand"] != "/verifysignal-understand"
    assert result["recommendedAction"] in {"continue-with-warning", "validate-alias", "confirm-risk"}


def test_unknown_refresh_impact_requires_confirmation_for_write_run(tmp_path) -> None:
    create_stale_understanding_workspace(tmp_path)
    create_live_write_readiness_workspace(tmp_path)
    record = load_use_case(tmp_path, "add-collaboration-project")
    record.status = "ready"
    save_use_case(tmp_path, record)
    save_ready_snapshot(tmp_path, record.alias, side_effect_class="write")
    save_refresh_impact(
        tmp_path,
        RefreshImpactResult(
            alias="add-collaboration-project",
            status="unknown",
            reason="Could not determine whether refreshed tested code affects this write flow.",
        ),
    )

    result = check_prerequisites(tmp_path, "run", alias="add-collaboration-project")

    assert result["requiresConfirmation"] is True
    assert result["confirmation"]["riskClass"] == "write"
    assert result["confirmation"]["scope"] == "unknown-refresh-impact"
    assert result["nextCommand"] != "/verifysignal-understand"
