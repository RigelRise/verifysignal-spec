from __future__ import annotations

import json

from helpers import CliTestCase
from tests.fixtures.workflows.browser_first_understanding import (
    browser_understanding_payload,
)
from tests.fixtures.workflows.golden_path_productization import PUBLIC_ALIAS, create_golden_path_workspace
from verifysignal_spec.workspace.repository import load_document, save_document
from verifysignal_spec.workflows.stage_persistence import persist_stage


class FirstRunRecommendationContractTests(CliTestCase):
    def setUp(self) -> None:
        super().setUp()
        create_golden_path_workspace(self.project)

    def test_recommend_first_run_json_contract(self) -> None:
        code, out, err = self.cli(["workflow", "recommend-first-run", "--project", str(self.project), "--json"])

        self.assertEqual(code, 0, err)
        data = json.loads(out)
        self.assertEqual(data["schemaVersion"], "verifysignal-spec-first-run-recommendation/v1")
        self.assertEqual(data["status"], "ready")
        self.assertEqual(data["targetStatus"], "resolved")
        self.assertEqual(data["recommendedCandidate"]["alias"], PUBLIC_ALIAS)
        self.assertIn("strongly recommend", data["recommendationText"].lower())
        self.assertIn("highly recommended", data["acceptancePrompt"].lower())
        self.assertIn("not a pass", data["skipMeaning"])
        self.assertEqual(data["stageCards"][0]["statusMarker"], "[RECOMMENDED]")
        self.assertIn("accept-first-run", data["nextAction"])

    def test_accept_first_run_json_contract(self) -> None:
        code, out, err = self.cli(["workflow", "accept-first-run", PUBLIC_ALIAS, "--project", str(self.project), "--json"])

        self.assertEqual(code, 0, err)
        data = json.loads(out)
        self.assertEqual(data["schemaVersion"], "verifysignal-spec-guided-first-run/v1")
        self.assertEqual(data["status"], "accepted")
        self.assertEqual(data["stage"], "accepted")
        self.assertEqual(data["selectedCandidate"], PUBLIC_ALIAS)
        self.assertEqual(data["selectedCandidateDetails"]["alias"], PUBLIC_ALIAS)
        self.assertEqual(data["stageCards"][0]["statusMarker"], "[ACCEPTED]")
        self.assertIn(PUBLIC_ALIAS, data["resumeCommand"])
        self.assertEqual(
            data["nextAction"],
            f"$verifysignal-specify {PUBLIC_ALIAS}",
        )
        self.assertNotIn("author", data["nextAction"])

    def test_skip_first_run_json_contract(self) -> None:
        code, out, err = self.cli(["workflow", "skip-first-run", "--project", str(self.project), "--json"])

        self.assertEqual(code, 0, err)
        data = json.loads(out)
        self.assertEqual(data["schemaVersion"], "verifysignal-spec-guided-first-run/v1")
        self.assertEqual(data["status"], "skipped")
        self.assertEqual(data["stage"], "skipped")
        self.assertIn("not success", data["skipMeaning"])
        self.assertEqual(data["stageCards"][0]["statusMarker"], "[SKIPPED]")
        self.assertIn("nextAction", data)

    def test_accepts_inventory_only_candidate_and_resumes_codex_specify(self) -> None:
        project = self.project / "inventory-only-codex"
        payload = browser_understanding_payload()
        alias = payload["coverageInventory"]["candidateUseCases"][0]["alias"]
        persisted = persist_stage(
            project,
            "understand",
            scope="all",
            payload=payload,
        )
        self.assertEqual(persisted["status"], "persisted")
        self.assertFalse(
            (project / f".verifysignal/use-cases/{alias}.yaml").exists()
        )

        code, out, err = self.cli(
            [
                "workflow",
                "accept-first-run",
                alias,
                "--project",
                str(project),
                "--json",
            ]
        )

        self.assertEqual(code, 0, err)
        data = json.loads(out)
        self.assertEqual(data["status"], "accepted")
        self.assertEqual(
            data["nextAction"], f"$verifysignal-specify {alias}"
        )
        self.assertNotIn("author", data["nextAction"])
        self.assertEqual(
            data["selectedCandidateDetails"]["groundingStatus"],
            "authentication-required",
        )
        self.assertEqual(
            data["selectedCandidateDetails"]["sideEffectClass"], "none"
        )
        state = load_document(
            project / ".verifysignal/workflows/golden-path-state.yaml",
            default={},
        )
        self.assertEqual(
            state["selectedCandidateDetails"],
            data["selectedCandidateDetails"],
        )

    def test_inventory_only_acceptance_uses_claude_invocation(self) -> None:
        project = self.project / "inventory-only-claude"
        payload = browser_understanding_payload()
        alias = payload["coverageInventory"]["candidateUseCases"][0]["alias"]
        persisted = persist_stage(
            project,
            "understand",
            scope="all",
            payload=payload,
        )
        self.assertEqual(persisted["status"], "persisted")
        save_document(
            project / ".verifysignal/integrations/state.yaml",
            {
                "schemaVersion": "verifysignal-spec-integrations/v1",
                "integrations": {
                    "claude": {
                        "displayName": "Claude Code",
                        "installedAt": "2026-07-27T00:00:00Z",
                        "default": True,
                        "invokeStyle": "slash-command",
                    }
                },
            },
        )

        code, out, err = self.cli(
            [
                "workflow",
                "accept-first-run",
                alias,
                "--project",
                str(project),
                "--json",
            ]
        )

        self.assertEqual(code, 0, err)
        self.assertEqual(
            json.loads(out)["nextAction"],
            f"/verifysignal-specify {alias}",
        )
