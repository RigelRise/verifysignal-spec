from __future__ import annotations

import json
import os

from helpers import FAKE_CORE, CliTestCase
from verifysignal_spec.workflows.evidence import normalize_planned_gates
from verifysignal_spec.workflows.gate_coverage import calculate_gate_coverage, coverage_status
from verifysignal_spec.workflows.models import EvidenceInventory
from verifysignal_spec.workflows.repair_recommendations import recommend_repairs_for_gate_coverage
from tests.fixtures.workflows.main_skill_run_coverage import create_main_skill_coverage_workspace


def test_core_pass_with_missing_required_gate_is_incomplete() -> None:
    gates, _warnings = normalize_planned_gates([{"id": "about-tab-content", "description": "About tab content", "required": True}])
    coverage = calculate_gate_coverage(gates, EvidenceInventory())

    assert coverage_status("passed", coverage) == "incomplete"
    contradictions = recommend_repairs_for_gate_coverage(coverage, gates, source_run_id="run-1")
    assert contradictions[0].gateId == "about-tab-content"
    assert contradictions[0].recommendation == "mark-conditional"


def test_conditional_unmet_gate_does_not_make_run_incomplete() -> None:
    gates, _warnings = normalize_planned_gates(
        [
            {
                "id": "about-tab-content",
                "description": "About tab",
                "required": False,
                "condition": "Profile has About tab",
                "conditionEvaluation": "unmet",
            }
        ]
    )
    coverage = calculate_gate_coverage(gates, EvidenceInventory())

    assert coverage[0].status == "conditional-unmet"
    assert coverage_status("passed", coverage) == "complete"


class RunResultCoverageCliContractTests(CliTestCase):
    def test_helper_only_core_success_is_incomplete_and_nonzero(self) -> None:
        create_main_skill_coverage_workspace(
            self.project,
            core_cmd=str(FAKE_CORE),
            protected_ready=True,
        )
        os.environ["FAKE_VERIFYSIGNAL_MODE"] = "helper-only"

        code, out, err = self.cli(["run", "profile-view-unauth", "--project", str(self.project), "--json", "--non-interactive"])

        assert err == ""
        assert code != 0
        payload = json.loads(out)
        assert payload["status"] == "incomplete"
        assert payload["coreStatus"] == "passed"
        assert payload["coverageStatus"] == "incomplete"
        assert payload["skillSelectionStatus"] == "mismatch"
        assert payload["executedSkill"]["id"] == "skill.discover-profile"
        assert payload["selectedMainSkill"]["id"] == "skill.validate-profile-view-unauth-flow"
        assert sorted(payload["missingRequiredGates"]) == ["overview-data-card", "overview-profile-query", "projects-tab-content"]
        assert payload["reason"]
        assert payload["nextAction"]

    def test_incomplete_summary_includes_missing_gates_reason_and_next_action(self) -> None:
        create_main_skill_coverage_workspace(
            self.project,
            core_cmd=str(FAKE_CORE),
            protected_ready=True,
        )
        os.environ["FAKE_VERIFYSIGNAL_MODE"] = "helper-only"

        _code, out, _err = self.cli(["run", "profile-view-unauth", "--project", str(self.project), "--json", "--non-interactive"])
        payload = json.loads(out)

        assert payload["missingRequiredGates"]
        assert "required validation gates" in payload["reason"]
        assert "verifysignal repair profile-view-unauth" in payload["nextAction"]

    def test_failed_core_run_separates_browser_status_from_diagnostic_coverage(self) -> None:
        create_main_skill_coverage_workspace(
            self.project,
            core_cmd=str(FAKE_CORE),
            protected_ready=True,
        )
        os.environ["FAKE_VERIFYSIGNAL_MODE"] = "aborted-activity-wait"

        code, out, err = self.cli(["run", "profile-view-unauth", "--project", str(self.project), "--json", "--non-interactive"])

        assert err == ""
        assert code != 0
        payload = json.loads(out)
        assert payload["status"] == "failed"
        assert payload["coreStatus"] == "failed"
        assert payload["coverageStatus"] == "diagnostic"
        assert payload["coreBrowserStatus"] == "failed"
        assert payload["specCoverageStatus"] == "diagnostic"
        assert payload["runOutcomeSummary"]["coreBrowserStatus"] == "failed"
        assert payload["runOutcomeSummary"]["specCoverageStatus"] == "diagnostic"
        assert "diagnostic" in payload["reason"]
