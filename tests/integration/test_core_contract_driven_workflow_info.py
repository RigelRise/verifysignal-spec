from __future__ import annotations

import json
import os

from helpers import FAKE_CORE, CliTestCase, assert_no_core_contract_snapshots


class CoreContractDrivenWorkflowInfoTests(CliTestCase):
    def test_workflow_info_follows_fake_core_contract_drift(self) -> None:
        self.cli(
            [
                "init",
                str(self.project),
                "--integration",
                "codex",
                "--core-cmd",
                str(FAKE_CORE),
                "--json",
            ]
        )
        os.environ["FAKE_VERIFYSIGNAL_MODE"] = "contract-drift"

        code, out, err = self.cli(["workflow", "info", "--project", str(self.project), "--json"])

        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        browser = payload["browserAuthoringContract"]
        self.assertEqual(browser["source"], "core-public-contract")
        self.assertIn("press", browser["validActions"])
        self.assertNotIn("repeatUntil", browser["validActions"])
        self.assertEqual(payload["coreExecutableContract"]["source"], "core-public-contract")
        assert_no_core_contract_snapshots(self.project)

    def test_separate_workflow_info_commands_perform_fresh_contract_discovery(self) -> None:
        self.cli(
            [
                "init",
                str(self.project),
                "--integration",
                "codex",
                "--core-cmd",
                str(FAKE_CORE),
                "--json",
            ]
        )
        counter = self.project / "contract-counter.txt"
        os.environ["FAKE_VERIFYSIGNAL_CONTRACT_COUNTER"] = str(counter)
        try:
            for _ in range(2):
                code, _out, err = self.cli(["workflow", "info", "--project", str(self.project), "--json"])
                self.assertEqual(code, 0, err)
        finally:
            os.environ.pop("FAKE_VERIFYSIGNAL_CONTRACT_COUNTER", None)

        self.assertEqual(counter.read_text(encoding="utf-8"), "2")
