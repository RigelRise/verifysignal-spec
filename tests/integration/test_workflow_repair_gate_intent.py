from __future__ import annotations

from verifysignal_spec.commands import run as run_command
from verifysignal_spec.workflows.repository import load_artifact_plan
from tests.fixtures.workflows.main_skill_run_coverage import create_main_skill_coverage_workspace


def test_required_gate_stays_required_after_aborted_browser_run(tmp_path, monkeypatch) -> None:
    from tests.helpers import FAKE_CORE

    monkeypatch.setenv("VERIFYSIGNAL_CORE_CMD", str(FAKE_CORE))
    monkeypatch.setenv("FAKE_VERIFYSIGNAL_MODE", "aborted-activity-wait")
    create_main_skill_coverage_workspace(
        tmp_path,
        core_cmd=str(FAKE_CORE),
        protected_ready=True,
    )

    result = run_command.run(tmp_path, "profile-view-unauth", interactive=False, core_cmd=str(FAKE_CORE))
    gates = load_artifact_plan(tmp_path, "profile-view-unauth").validationGates

    assert result["specCoverageStatus"] == "diagnostic"
    assert result["runtimeContradictions"] == []
    assert all(gate["required"] is True for gate in gates if gate["id"] in {"overview-data-card", "projects-tab-content", "overview-profile-query"})
