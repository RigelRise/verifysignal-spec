from __future__ import annotations

import json
import os

from helpers import FAKE_CORE, CliTestCase
from tests.fixtures.workflows.golden_path_productization import PUBLIC_ALIAS, create_golden_path_workspace
from verifysignal_spec.workspace.repository import init_workspace


class GoldenPathRepairIntegrationTests(CliTestCase):
    def test_repairable_first_run_failure_emits_auto_repair_feedback(self) -> None:
        os.environ["FAKE_VERIFYSIGNAL_MODE"] = "aborted-activity-wait"
        create_golden_path_workspace(self.project)
        init_workspace(self.project, core_cmd=str(FAKE_CORE))
        self.cli(["workflow", "accept-first-run", PUBLIC_ALIAS, "--project", str(self.project), "--json"])
        report = self.project / "report.json"
        report.write_text("{}", encoding="utf-8")

        code, out, err = self.cli(["repair", PUBLIC_ALIAS, "--project", str(self.project), "--from-report", str(report), "--json"])

        # wait-strategy needs live page context, so the repair is proposed (exit 4), not a
        # false `applied`. The classification is `propose-only` — it has no mutator, so calling it
        # `auto-applied` contradicted this very comment — and the feedback + stage card still surface.
        self.assertEqual(code, 4, err)
        repair = json.loads(out)["repair"]
        self.assertEqual(repair["approvalStatus"], "proposed")
        self.assertEqual(repair["recommendations"][0]["autonomy"], "propose-only")
        self.assertEqual(repair["repairFeedback"][0]["autonomy"], "propose-only")
        self.assertEqual(repair["stageCards"][0]["statusMarker"], "[REPAIR]")
