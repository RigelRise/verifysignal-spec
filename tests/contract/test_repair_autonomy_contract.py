from __future__ import annotations

import json
import os

from helpers import FAKE_CORE, CliTestCase


class RepairAutonomyContractTests(CliTestCase):
    def test_wait_strategy_report_is_proposed_without_a_verified_mutation(self) -> None:
        os.environ["FAKE_VERIFYSIGNAL_MODE"] = "aborted-activity-wait"
        self.cli(["init", str(self.project), "--integration", "codex", "--core-cmd", str(FAKE_CORE)])
        self.cli(["author", "home-page-unauth", "Validate home page.", "--project", str(self.project)])
        report = self.project / "report.json"
        report.write_text("{}", encoding="utf-8")

        code, out, err = self.cli(["repair", "home-page-unauth", "--project", str(self.project), "--from-report", str(report), "--json"])

        # Wait-strategy fixes need live page/DOM context, so the repair is PROPOSED (exit 4),
        # never a false `applied`: the agent must apply the described wait adjustment and rerun.
        self.assertEqual(code, 4, err)
        repair = json.loads(out)["repair"]
        self.assertEqual(repair["approvalStatus"], "proposed")
        # `autonomy` describes the available MECHANISM, not an aspiration: wait-strategy has no on-disk
        # mutator (only main-skill-ordering does), so labeling it `auto-applied` claimed an automation
        # that does not exist and drove an "after" reading as if the fix had been applied.
        self.assertEqual(repair["recommendations"][0]["autonomy"], "propose-only")
        self.assertNotEqual(repair["recommendations"][0]["autonomy"], "auto-applied")
        self.assertTrue(repair["recommendations"][0]["safeMechanical"])
        self.assertFalse(repair["recommendations"][0]["requiresUserDecision"])
        self.assertFalse(repair["applications"][0]["applied"])
        self.assertEqual(repair["applications"][0]["validationStatus"], "not-run")
        self.assertEqual(repair["stageCards"][0]["statusMarker"], "[REPAIR]")

    def test_gate_mapping_repair_still_requires_confirmation(self) -> None:
        self.cli(["init", str(self.project), "--integration", "codex", "--core-cmd", str(FAKE_CORE)])
        self.cli(["author", "home-page-unauth", "Validate home page.", "--project", str(self.project)])
        record_path = self.project / ".verifysignal/use-cases/home-page-unauth.yaml"
        data = json.loads(record_path.read_text(encoding="utf-8"))
        data["validation"] = {
            "findings": [
                {
                    "code": "missing-gateid",
                    "message": "assertion lacks gateId",
                    "artifact": ".verifysignal/skills/home-page-unauth.browser.md",
                    "path": "assertions[0]",
                }
            ]
        }
        record_path.write_text(json.dumps(data), encoding="utf-8")

        code, out, _err = self.cli(["repair", "home-page-unauth", "--project", str(self.project), "--json"])

        self.assertEqual(code, 4)
        repair = json.loads(out)["repair"]
        self.assertEqual(repair["approvalStatus"], "pending")
        self.assertEqual(repair["recommendations"][0]["autonomy"], "confirmation-required")
        self.assertTrue(repair["recommendations"][0]["requiresUserDecision"])
