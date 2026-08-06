from __future__ import annotations

from helpers import FAKE_CORE, CliTestCase
from tests.fixtures.workflows.entitlement_preflight_recovery import save_protected_ready_snapshot


class RunUseCaseIntegrationTests(CliTestCase):
    def test_run_records_history_without_credentials(self) -> None:
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
        save_protected_ready_snapshot(self.project, "login")
        self.assertEqual(self.cli(["run", "login", "--project", str(self.project), "--non-interactive"])[0], 0)
        history = self.project / ".verifysignal" / "runs" / "login" / "fake-run-1.yaml"
        self.assertTrue(history.exists())
        self.assertNotIn("password", history.read_text(encoding="utf-8").lower())
