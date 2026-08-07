from __future__ import annotations

import json

from helpers import FAKE_CORE, CliTestCase
from verifysignal_spec.workspace.repository import load_use_case, save_use_case
from tests.fixtures.workflows.main_skill_run_coverage import create_main_skill_coverage_workspace


class RepairConfirmationFlowTests(CliTestCase):
    def test_ambiguous_selector_feedback_is_propose_only_when_intent_is_preserved(self) -> None:
        create_main_skill_coverage_workspace(self.project)
        record = load_use_case(self.project, "profile-view-unauth")
        record.validation = {
            "findings": [
                {
                    "code": "strict-mode-violation",
                    "message": "Profile card locator resolved to multiple elements.",
                    "artifact": ".verifysignal/skills/profile.browser.md",
                    "path": "targets.profileCard",
                }
            ]
        }
        save_use_case(self.project, record)

        code, out, err = self.cli(["repair", "profile-view-unauth", "--project", str(self.project), "--approve", "--json"])

        # Selector-ambiguity is proposed (exit 4), not a false `applied`: the fix needs the
        # live page to compute a stable selector, so the agent must apply it, then rerun.
        self.assertEqual(code, 4, err)
        repair = json.loads(out)["repair"]
        self.assertEqual(repair["approvalStatus"], "proposed")
        self.assertFalse(repair["readyForRun"])
        self.assertFalse(repair["recommendations"][0]["requiresUserDecision"])
        self.assertEqual(repair["recommendations"][0]["safeCategory"], "selector-ambiguity")
        # The label must match the comment above: there is no selector mutator, so it is propose-only.
        self.assertEqual(repair["recommendations"][0]["autonomy"], "propose-only")

    def test_auto_repair_feedback_is_recorded_after_root_cause_and_scope(self) -> None:
        import os

        os.environ["FAKE_VERIFYSIGNAL_MODE"] = "aborted-activity-wait"
        self.cli(["init", str(self.project), "--integration", "codex", "--core-cmd", str(FAKE_CORE)])
        self.cli(["author", "home-page-unauth", "Validate home page.", "--project", str(self.project)])
        report = self.project / "report.json"
        report.write_text("{}", encoding="utf-8")

        code, out, err = self.cli(["repair", "home-page-unauth", "--project", str(self.project), "--from-report", str(report), "--approve", "--json"])

        # wait-strategy is proposed (exit 4), not a false `applied`; revalidation stays not-run
        # because no artifact mutation occurred.
        self.assertEqual(code, 4, err)
        repair = json.loads(out)["repair"]
        self.assertEqual(repair["approvalStatus"], "proposed")
        self.assertEqual(repair["repairFeedback"][0]["category"], "wait-flow-issue")
        # No wait-strategy mutator exists (it needs live page context), so the honest label is propose-only.
        self.assertEqual(repair["repairFeedback"][0]["autonomy"], "propose-only")
        self.assertTrue(repair["repairFeedback"][0]["intentPreserved"])
        self.assertEqual(repair["revalidation"]["status"], "not-run")
