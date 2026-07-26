from __future__ import annotations

import json

from helpers import CliTestCase
from tests.integration.test_understanding_onboarding import representative_understanding_payload
from verifysignal_spec.workflows.stage_persistence import persist_stage


class UnderstandingOnboardingContractTests(CliTestCase):
    def test_missing_understanding_check_includes_auto_prepare_and_resume_fields(self) -> None:
        code, out, err = self.cli(["workflow", "check", "specify", "--project", str(self.project), "--json"])

        self.assertEqual(code, 0, err)
        data = json.loads(out)
        self.assertEqual(data["stage"], "specify")
        self.assertEqual(data["status"], "missing")
        self.assertFalse(data["canProceed"])
        self.assertEqual(data["recommendedAction"], "auto-prepare-understanding")
        self.assertEqual(data["onboardingPreparation"]["status"], "auto-preparable")
        self.assertFalse(data["onboardingPreparation"]["approvalRequired"])
        self.assertIn("verifysignal-understand", data["onboardingPreparation"]["nextCommand"])
        self.assertIn("verifysignal-specify", data["resumeCommand"])
        self.assertEqual(data["stageCards"][0]["statusMarker"], "[RUNNING]")

    def test_missing_understanding_guidance_has_single_resume_action(self) -> None:
        code, out, err = self.cli(["workflow", "check", "specify", "--project", str(self.project), "--json"])

        self.assertEqual(code, 0, err)
        data = json.loads(out)
        preparation = data["onboardingPreparation"]
        self.assertIn("safe product understanding", preparation["summary"].lower())
        self.assertIn("live url", preparation["summary"].lower())
        self.assertIn("sensitive", " ".join(preparation["safetyBoundaries"]).lower())
        self.assertEqual(preparation["resumeCommand"], data["resumeCommand"])

    def test_understanding_persistence_records_onboarding_inventory_fields(self) -> None:
        result = persist_stage(self.project, "understand", scope="all", payload=representative_understanding_payload())

        self.assertEqual(result["status"], "persisted")
        self.assertIn("partial inventory", " ".join(result.get("warnings", [])).lower())
        self.assertEqual(result["understandingOnboarding"]["sourceTraceabilityStatus"], "normalized")
        self.assertEqual(result["understandingOnboarding"]["trivialCandidateCount"], 1)
