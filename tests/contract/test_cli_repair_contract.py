from __future__ import annotations

import json
import os

from helpers import FAKE_CORE, CliTestCase
from verifysignal_spec.workspace.repository import load_use_case, save_use_case
from tests.fixtures.workflows.main_skill_run_coverage import create_main_skill_coverage_workspace


class RepairContractTests(CliTestCase):
    def test_repair_requires_approval_by_default(self) -> None:
        self.cli(["init", str(self.project), "--integration", "codex", "--core-cmd", str(FAKE_CORE)])
        self.cli(["author", "login", "Validate login.", "--project", str(self.project)])
        code, out, _ = self.cli(["repair", "login", "--project", str(self.project), "--json"])
        self.assertEqual(code, 4)
        payload = json.loads(out)
        self.assertEqual(payload["repair"]["approvalStatus"], "pending")

    def test_repair_recommends_supported_safe_categories(self) -> None:
        create_main_skill_coverage_workspace(self.project)
        record = load_use_case(self.project, "profile-view-unauth")
        record.validation = {
            "findings": [
                {"code": "strict-mode-violation", "message": "locator resolved to 84 elements", "artifact": ".verifysignal/skills/profile.browser.md", "path": "targets.profileCard"},
                {"code": "wait-timeout", "message": "waited for client-side GraphQL on an SSR page", "artifact": ".verifysignal/skills/profile.browser.md", "path": "steps[1]"},
                {"code": "main-skill-ordering", "message": "helper skill executed before main skill", "artifact": ".verifysignal/run-requests/profile.yaml", "path": "skills"},
                {"code": "debug-slowmo-default", "message": "debug run has slowMoMs 0", "artifact": ".verifysignal/use-cases/profile.yaml", "path": "profiles.debug"},
                {"code": "missing-gateid", "message": "assertion lacks gateId", "artifact": ".verifysignal/skills/profile.browser.md", "path": "assertions[0]"},
            ]
        }
        save_use_case(self.project, record)

        code, out, _ = self.cli(["repair", "profile-view-unauth", "--project", str(self.project), "--json"])

        self.assertEqual(code, 4)
        recommendations = json.loads(out)["repair"]["recommendations"]
        self.assertEqual(
            {item["safeCategory"] for item in recommendations},
            {"selector-ambiguity", "wait-strategy", "main-skill-ordering", "run-profile-defaults", "gateid-mapping"},
        )
        confirmation_required = {
            item["safeCategory"]
            for item in recommendations
            if item.get("requiresUserDecision")
        }
        self.assertEqual(confirmation_required, {"gateid-mapping"})

    def test_intent_changing_safe_categories_block_approved_auto_apply(self) -> None:
        create_main_skill_coverage_workspace(self.project)
        record = load_use_case(self.project, "profile-view-unauth")
        record.validation = {
            "findings": [
                {
                    "code": "missing-gateid",
                    "message": "assertion lacks gateId",
                    "artifact": ".verifysignal/skills/profile.browser.md",
                    "path": "assertions[0]",
                }
            ]
        }
        save_use_case(self.project, record)

        code, out, err = self.cli(["repair", "profile-view-unauth", "--project", str(self.project), "--approve", "--json"])

        # A blocked repair that was `--approve`d but applied nothing must signal action-required
        # (exit 4), not success — the `--approve` flag cannot silence an unresolved block.
        self.assertEqual(code, 4, err)
        repair = json.loads(out)["repair"]
        self.assertEqual(repair["approvalStatus"], "conflict")
        self.assertFalse(repair["readyForRun"])
        self.assertTrue(repair["recommendations"][0]["requiresUserDecision"])

    def test_data_credential_gate_and_expected_behavior_changes_still_require_confirmation(self) -> None:
        create_main_skill_coverage_workspace(self.project)
        record = load_use_case(self.project, "profile-view-unauth")
        record.validation = {
            "findings": [
                {"code": "seeded-data-change", "message": "Change data assumptions.", "artifact": ".verifysignal/use-cases/profile.yaml"},
                {"code": "credential-reference-change", "message": "Change credential requirements.", "artifact": ".verifysignal/use-cases/profile.yaml"},
                {"code": "missing-gateid", "message": "assertion lacks gateId", "artifact": ".verifysignal/skills/profile.browser.md"},
                {"code": "expected-behavior-change", "message": "Expected product behavior is different.", "artifact": ".verifysignal/use-cases/profile.yaml"},
            ]
        }
        save_use_case(self.project, record)

        code, out, _err = self.cli(["repair", "profile-view-unauth", "--project", str(self.project), "--json"])

        self.assertEqual(code, 4)
        recommendations = json.loads(out)["repair"]["recommendations"]
        self.assertTrue(all(item["requiresUserDecision"] for item in recommendations))
        self.assertTrue(all(item["autonomy"] in {"confirmation-required", "blocked"} for item in recommendations))

    def test_product_decision_changing_repair_is_blocked_even_when_approved(self) -> None:
        create_main_skill_coverage_workspace(self.project)
        record = load_use_case(self.project, "profile-view-unauth")
        record.validation = {
            "findings": [
                {
                    "code": "hardcoded-profile-replacement",
                    "message": "Replace dynamic discovery with fixed profile identifier.",
                    "artifact": ".verifysignal/skills/profile.browser.md",
                    "path": "steps[0]",
                }
            ]
        }
        save_use_case(self.project, record)

        code, out, err = self.cli(["repair", "profile-view-unauth", "--project", str(self.project), "--approve", "--json"])

        # Approving a product-decision-changing (blocked) repair still applies nothing, so it must
        # exit 4 (action required), not 0.
        self.assertEqual(code, 4, err)
        repair = json.loads(out)["repair"]
        self.assertEqual(repair["approvalStatus"], "conflict")
        self.assertFalse(repair["readyForRun"])
        self.assertEqual(repair["recommendations"][0]["category"], "clarification-required")

    def test_aborted_run_does_not_generate_required_gate_weakening_recommendations(self) -> None:
        create_main_skill_coverage_workspace(
            self.project,
            core_cmd=str(FAKE_CORE),
            protected_ready=True,
        )
        os.environ["FAKE_VERIFYSIGNAL_MODE"] = "aborted-activity-wait"

        code, out, err = self.cli(["run", "profile-view-unauth", "--project", str(self.project), "--json", "--non-interactive"])

        self.assertNotEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["specCoverageStatus"], "diagnostic")
        self.assertEqual(payload["runtimeContradictions"], [])
        self.assertFalse(any(item.get("action") == "mark-conditional" for item in payload["repairRecommendations"]))

    def test_execution_boundary_repair_does_not_recommend_gate_weakening(self) -> None:
        create_main_skill_coverage_workspace(self.project)
        record = load_use_case(self.project, "profile-view-unauth")
        record.validation = {
            "findings": [
                {
                    "code": "skill-execution.legacy-migration-required",
                    "message": "Helper skill executed as an unintended executable participant while required gates were missing.",
                    "artifact": ".verifysignal/run-requests/profile-view-unauth.yaml",
                    "path": "skills",
                }
            ]
        }
        save_use_case(self.project, record)

        code, out, _err = self.cli(["repair", "profile-view-unauth", "--project", str(self.project), "--json"])

        # This fixture's run-request already has the main skill first, so there is no deterministic
        # ordering mutation to apply — the repair is `proposed` (exit 4), not a false `applied`.
        # (Previously this exited 0 only because the buggy mutator regenerated the run-request and
        # its byte change was reported as `applied`.)
        self.assertEqual(code, 4)
        recommendations = json.loads(out)["repair"]["recommendations"]
        self.assertEqual(recommendations[0]["runtimeCategory"], "execution-boundary-issue")
        self.assertEqual(recommendations[0]["safeCategory"], "main-skill-ordering")
        # The guarantee, not one phrasing of it: the action must still rule out weakening required
        # gates. (The prose is now rendered from `autonomy` rather than hand-written, so the clause
        # reads "does not weaken" instead of the old imperative "do not weaken".)
        self.assertRegex(recommendations[0]["action"], r"(?:do|does) not weaken required gates")

    def test_post_commit_write_risk_does_not_recommend_blind_rerun(self) -> None:
        create_main_skill_coverage_workspace(self.project)
        record = load_use_case(self.project, "profile-view-unauth")
        record.validation = {
            "findings": [
                {
                    "code": "write-flow.post-commit-verification-failed",
                    "message": "Commit step was reached and final verification failed.",
                    "resultClassification": {
                        "sideEffectStatus": "likely-committed",
                        "failurePhase": "post-commit",
                        "rerunRisk": "requires-confirmation",
                    },
                }
            ]
        }
        save_use_case(self.project, record)

        code, out, _err = self.cli(["repair", "profile-view-unauth", "--project", str(self.project), "--json"])

        self.assertEqual(code, 4)
        recommendation = json.loads(out)["repair"]["recommendations"][0]
        self.assertEqual(recommendation["runtimeCategory"], "write-flow-safety")
        self.assertEqual(recommendation["autonomy"], "blocked")
        self.assertFalse(recommendation["safeMechanical"])
        self.assertIn("Review", recommendation["action"])
