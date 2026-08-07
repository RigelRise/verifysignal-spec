from __future__ import annotations

import os

from helpers import FAKE_CORE, CliTestCase


class RepairFromValidationTests(CliTestCase):
    def test_repair_proposal_uses_validation_finding_artifact_and_field(self) -> None:
        self.cli(
            [
                "init",
                str(self.project),
                "--integration",
                "codex",
                "--core-cmd",
                str(FAKE_CORE),
            ]
        )
        self.cli(["author", "login", "Validate login.", "--project", str(self.project)])
        os.environ["FAKE_VERIFYSIGNAL_MODE"] = "blocked"
        self.cli(["validate", "login", "--project", str(self.project)])
        os.environ.pop("FAKE_VERIFYSIGNAL_MODE", None)
        code, out, _ = self.cli(["repair", "login", "--project", str(self.project), "--json"])
        self.assertEqual(code, 4)
        self.assertIn("parameters.baseUrl", out)
