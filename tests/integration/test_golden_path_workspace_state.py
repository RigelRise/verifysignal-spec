from __future__ import annotations

import json
import os

from helpers import FAKE_CORE, CliTestCase
from tests.fixtures.workflows.entitlement_preflight_recovery import save_protected_ready_snapshot
from tests.fixtures.workflows.golden_path_productization import PUBLIC_ALIAS, create_golden_path_workspace
from tests.fixtures.workflows.golden_path_onboarding import PUBLIC_ALIAS as ONBOARDING_PUBLIC_ALIAS, create_onboarding_repository
from verifysignal_spec.workspace.repository import init_workspace


class GoldenPathWorkspaceStateIntegrationTests(CliTestCase):
    def test_inspect_empty_resume_and_reset_flow(self) -> None:
        create_golden_path_workspace(self.project)

        empty_code, empty_out, empty_err = self.cli(["workflow", "inspect-golden-path-state", "--project", str(self.project), "--json"])
        self.assertEqual(empty_code, 0, empty_err)
        self.assertEqual(json.loads(empty_out)["status"], "empty")

        self.cli(["workflow", "accept-first-run", PUBLIC_ALIAS, "--project", str(self.project), "--json"])
        inspect_code, inspect_out, inspect_err = self.cli(["workflow", "inspect-golden-path-state", "--project", str(self.project), "--json"])
        self.assertEqual(inspect_code, 0, inspect_err)
        payload = json.loads(inspect_out)
        self.assertEqual(payload["status"], "ready")
        self.assertIn(PUBLIC_ALIAS, payload["resumeHint"])
        self.assertEqual(payload["firstRunState"]["selectedCandidate"], PUBLIC_ALIAS)
        self.assertEqual(payload["firstRunState"]["stage"], "accepted")

        reset_code, reset_out, reset_err = self.cli(["workflow", "reset-golden-path-state", "--project", str(self.project), "--confirm", "--json"])
        self.assertEqual(reset_code, 0, reset_err)
        self.assertEqual(json.loads(reset_out)["status"], "reset")

    def test_inspect_reports_untracked_run_history_without_implicit_acceptance(self) -> None:
        create_onboarding_repository(self.project)
        init_workspace(self.project, core_cmd=str(FAKE_CORE))
        save_protected_ready_snapshot(self.project, ONBOARDING_PUBLIC_ALIAS)
        old_mode = os.environ.get("FAKE_VERIFYSIGNAL_MODE")
        os.environ["FAKE_VERIFYSIGNAL_MODE"] = "full-coverage"
        try:
            run_code, _run_out, run_err = self.cli(["run", ONBOARDING_PUBLIC_ALIAS, "--project", str(self.project), "--profile", "normal", "--json"])
        finally:
            if old_mode is None:
                os.environ.pop("FAKE_VERIFYSIGNAL_MODE", None)
            else:
                os.environ["FAKE_VERIFYSIGNAL_MODE"] = old_mode

        self.assertEqual(run_code, 0, run_err)
        state_path = self.project / ".verifysignal/workflows/golden-path-state.yaml"
        self.assertFalse(state_path.exists())

        inspect_code, inspect_out, inspect_err = self.cli(["workflow", "inspect-golden-path-state", "--project", str(self.project), "--json"])

        self.assertEqual(inspect_code, 0, inspect_err)
        payload = json.loads(inspect_out)
        self.assertEqual(payload["status"], "untracked")
        self.assertIsNone(payload.get("firstRunState"))
        self.assertEqual(payload["untrackedRuns"][0]["alias"], ONBOARDING_PUBLIC_ALIAS)
        self.assertEqual(payload["untrackedRuns"][0]["status"], "passed")
        self.assertTrue(payload["warnings"])
