from __future__ import annotations

import os

from helpers import CliTestCase


class RepairFromReportTests(CliTestCase):
    def test_deterministic_report_inspection_repair_is_proposed_when_artifact_is_canonical(self) -> None:
        os.environ["FAKE_VERIFYSIGNAL_MODE"] = "report-main-skill"
        self.cli(["init", str(self.project), "--integration", "codex"])
        self.cli(["author", "login", "Validate login.", "--project", str(self.project)])
        report = self.project / "report.json"
        report.write_text("{}", encoding="utf-8")
        code, out, err = self.cli(["repair", "login", "--project", str(self.project), "--from-report", str(report), "--approve", "--json"])
        # A freshly-authored artifact already has its main skill first in the run-request, so the
        # main-skill-ordering repair has nothing to reorder -> PROPOSED (exit 4), never a false
        # `applied`. (The mutator surgically reorders the skills array; it does not regenerate the
        # run-request, so an already-ordered artifact yields no byte change.)
        self.assertEqual(code, 4, err)
        repair = __import__("json").loads(out)["repair"]
        self.assertEqual(repair["approvalStatus"], "proposed")
        self.assertFalse(repair["applications"][0]["applied"])
        self.assertIn("readyForRun", out)

    def test_report_selector_repair_is_proposed_not_applied(self) -> None:
        self.cli(["init", str(self.project), "--integration", "codex"])
        self.cli(["author", "login", "Validate login.", "--project", str(self.project)])
        report = self.project / "report.json"
        report.write_text("{}", encoding="utf-8")

        code, out, err = self.cli(["repair", "login", "--project", str(self.project), "--from-report", str(report), "--approve", "--json"])

        # Selector-ambiguity needs live page/DOM context to compute a new selector, so it is
        # PROPOSED (exit 4) with no artifact mutation, never a false `applied`.
        self.assertEqual(code, 4, err)
        repair = __import__("json").loads(out)["repair"]
        self.assertEqual(repair["approvalStatus"], "proposed")
        self.assertFalse(repair["readyForRun"])
        self.assertEqual(repair["revalidation"]["status"], "not-run")
        self.assertTrue(any(item.get("safeCategory") == "selector-ambiguity" for item in repair["recommendations"]))
        self.assertFalse(any(item.get("requiresUserDecision") for item in repair["recommendations"]))
        self.assertTrue(all(not app["applied"] for app in repair["applications"]))

    def test_safe_repair_matrix_covers_supported_categories(self) -> None:
        from verifysignal_spec.workflows.repair_recommendations import classify_repair_findings

        findings = [
            {"code": "strict-mode-violation", "message": "locator matched multiple elements"},
            {"code": "wait-timeout", "message": "network wait timed out"},
            {"code": "main-skill-ordering", "message": "executed helper before main"},
            {"code": "debug-slowmo-default", "message": "slowMoMs is 0 in debug"},
            {"code": "missing-gateid", "message": "gateId is absent"},
        ]

        recommendations = classify_repair_findings(findings)

        assert {item.safeCategory for item in recommendations} == {
            "selector-ambiguity",
            "wait-strategy",
            "main-skill-ordering",
            "run-profile-defaults",
            "gateid-mapping",
        }
        assert {item.safeCategory for item in recommendations if item.requiresUserDecision} == {"gateid-mapping"}

    def test_activity_skeleton_report_recommends_wait_flow_fix(self) -> None:
        os.environ["FAKE_VERIFYSIGNAL_MODE"] = "aborted-activity-wait"
        self.cli(["init", str(self.project), "--integration", "codex"])
        self.cli(["author", "home-page-unauth", "Validate home page.", "--project", str(self.project)])
        report = self.project / "report.json"
        report.write_text("{}", encoding="utf-8")

        code, out, err = self.cli(["repair", "home-page-unauth", "--project", str(self.project), "--from-report", str(report), "--json"])

        # wait-strategy is proposed (exit 4), not auto-applied.
        self.assertEqual(code, 4, err)
        recommendations = __import__("json").loads(out)["repair"]["recommendations"]
        self.assertEqual(recommendations[0]["runtimeCategory"], "wait-flow-issue")
        self.assertEqual(recommendations[0]["safeCategory"], "wait-strategy")
        self.assertFalse(recommendations[0]["requiresUserDecision"])
        self.assertNotIn("mark conditional", str(recommendations).lower())

    def test_report_preserves_selector_repair_but_blocks_automatic_side_effect_policy_changes(self) -> None:
        os.environ["FAKE_VERIFYSIGNAL_MODE"] = "report-selector-and-side-effect"
        self.cli(["init", str(self.project), "--integration", "codex"])
        self.cli(["author", "login", "Validate login.", "--project", str(self.project)])
        report = self.project / "report.json"
        report.write_text("{}", encoding="utf-8")

        code, out, err = self.cli(
            ["repair", "login", "--project", str(self.project), "--from-report", str(report), "--approve", "--json"]
        )

        self.assertNotEqual(code, 0, err)
        recommendations = __import__("json").loads(out)["repair"]["recommendations"]
        selector = next(item for item in recommendations if item.get("runtimeCategory") == "selector-issue")
        policy = next(item for item in recommendations if item.get("runtimeCategory") == "side-effect-policy-issue")
        self.assertEqual(selector["safeCategory"], "selector-ambiguity")
        self.assertFalse(selector["requiresUserDecision"])
        self.assertTrue(policy["requiresUserDecision"])
        self.assertEqual(policy["autonomy"], "blocked")
        self.assertFalse(policy["safeMechanical"])
