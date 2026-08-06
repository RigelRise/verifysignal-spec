from __future__ import annotations

import json

from helpers import FAKE_CORE, CliTestCase
from tests.fixtures.workflows.entitlement_preflight_recovery import save_protected_ready_snapshot
from tests.fixtures.workflows.golden_path_onboarding import PUBLIC_ALIAS, create_onboarding_repository
from verifysignal_spec.workspace.repository import init_workspace, load_document, load_use_case, save_use_case
from verifysignal_spec.workflows.transitions import transition_workflow


class GuidedFirstRunFlowIntegrationTests(CliTestCase):
    def setUp(self) -> None:
        super().setUp()
        create_onboarding_repository(self.project)
        init_workspace(self.project, core_cmd=str(FAKE_CORE))

    def test_accept_persists_guided_state_with_stage_cards(self) -> None:
        code, out, err = self.cli(["workflow", "accept-first-run", PUBLIC_ALIAS, "--project", str(self.project), "--json"])

        self.assertEqual(code, 0, err)
        data = json.loads(out)
        state = load_document(self.project / ".verifysignal/workflows/golden-path-state.yaml", default={})

        self.assertEqual(state["schemaVersion"], "verifysignal-spec-guided-first-run/v1")
        self.assertEqual(state["selectedCandidate"], PUBLIC_ALIAS)
        self.assertEqual(state["stage"], "accepted")
        self.assertEqual(state["resumeCommand"], data["resumeCommand"])
        self.assertTrue(state["stageCards"])

    def test_skip_preserves_normal_manual_use_case_selection(self) -> None:
        code, out, err = self.cli(["workflow", "skip-first-run", "--project", str(self.project), "--json"])

        self.assertEqual(code, 0, err)
        data = json.loads(out)
        self.assertEqual(data["stage"], "skipped")

        code, out, err = self.cli(["workflow", "recommend-first-run", "--project", str(self.project), "--json"])
        self.assertEqual(code, 0, err)
        recommendation = json.loads(out)
        self.assertEqual(recommendation["status"], "ready")

    def test_run_updates_guided_state_to_direct_pass(self) -> None:
        self.cli(["workflow", "accept-first-run", PUBLIC_ALIAS, "--project", str(self.project), "--json"])
        save_protected_ready_snapshot(self.project, PUBLIC_ALIAS)
        import os

        old_mode = os.environ.get("FAKE_VERIFYSIGNAL_MODE")
        os.environ["FAKE_VERIFYSIGNAL_MODE"] = "full-coverage"
        try:
            code, out, err = self.cli(["run", PUBLIC_ALIAS, "--project", str(self.project), "--profile", "normal", "--json"])
        finally:
            if old_mode is None:
                os.environ.pop("FAKE_VERIFYSIGNAL_MODE", None)
            else:
                os.environ["FAKE_VERIFYSIGNAL_MODE"] = old_mode

        self.assertEqual(code, 0, err)
        state = load_document(self.project / ".verifysignal/workflows/golden-path-state.yaml", default={})
        self.assertIn(state["stage"], {"passed", "repaired-passed"}, out)
        self.assertTrue(state["strictPass"])
        self.assertIn("stageCards", state)

    def test_side_effect_violation_prevents_strict_pass_and_blocks_unchanged_policy_rerun(self) -> None:
        self.cli(["workflow", "accept-first-run", PUBLIC_ALIAS, "--project", str(self.project), "--json"])
        save_protected_ready_snapshot(self.project, PUBLIC_ALIAS)
        import os

        old_mode = os.environ.get("FAKE_VERIFYSIGNAL_MODE")
        os.environ["FAKE_VERIFYSIGNAL_MODE"] = "full-coverage-side-effect-violation"
        try:
            code, out, err = self.cli(["run", PUBLIC_ALIAS, "--project", str(self.project), "--profile", "normal", "--json"])
            first = json.loads(out)
            state = load_document(self.project / ".verifysignal/workflows/golden-path-state.yaml", default={})
            record = load_use_case(self.project, PUBLIC_ALIAS)

            self.assertNotEqual(code, 0, err)
            self.assertEqual(first["status"], "failed")
            self.assertEqual(first["firstRunStatus"], "failed")
            self.assertFalse(first["strictPass"])
            self.assertFalse(state["strictPass"])
            self.assertEqual(record.lastRun["sideEffectPolicy"]["class"], "none")
            self.assertTrue(record.lastRun["sideEffects"]["violations"])
            record.status = "ready"
            save_use_case(self.project, record)
            transition_workflow(
                self.project,
                PUBLIC_ALIAS,
                stage="repair",
                outcome="completed",
                handoff_summary="Guided-flow fixture repair was reviewed.",
            )
            transition_workflow(
                self.project,
                PUBLIC_ALIAS,
                stage="validate",
                outcome="completed",
                handoff_summary="Guided-flow fixture is protected-ready.",
            )

            os.environ["FAKE_VERIFYSIGNAL_MODE"] = "full-coverage"
            blocked_code, blocked_out, blocked_err = self.cli(
                ["run", PUBLIC_ALIAS, "--project", str(self.project), "--profile", "normal", "--json"]
            )
            blocked = json.loads(blocked_out)
            self.assertNotEqual(blocked_code, 0, blocked_err)
            self.assertEqual(blocked["status"], "blocked")
            self.assertTrue(
                any(item["code"] == "runtime.side-effect-observation-review-required" for item in blocked["blockers"])
            )

            record = load_use_case(self.project, PUBLIC_ALIAS)
            record.sideEffects = {
                "class": "none",
                "mode": "observe",
                "allowed": [
                    {
                        "id": "reviewed-telemetry",
                        "kind": "network",
                        "methods": ["POST"],
                        "urlContains": "/api/telemetry",
                        "timing": "any",
                    }
                ],
                "forbidden": [],
            }
            save_use_case(self.project, record)
            save_protected_ready_snapshot(self.project, PUBLIC_ALIAS)
            os.environ["FAKE_VERIFYSIGNAL_MODE"] = "full-coverage-clean-side-effects"
            clean_code, clean_out, clean_err = self.cli(
                ["run", PUBLIC_ALIAS, "--project", str(self.project), "--profile", "normal", "--json"]
            )
            clean = json.loads(clean_out)
            self.assertEqual(clean_code, 0, f"{clean_err}\n{clean_out}")
            self.assertEqual(clean["status"], "passed")
            self.assertTrue(clean["strictPass"])
        finally:
            if old_mode is None:
                os.environ.pop("FAKE_VERIFYSIGNAL_MODE", None)
            else:
                os.environ["FAKE_VERIFYSIGNAL_MODE"] = old_mode
