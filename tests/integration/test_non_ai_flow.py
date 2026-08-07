from __future__ import annotations

from helpers import FAKE_CORE, CliTestCase
from tests.fixtures.workflows.entitlement_preflight_recovery import save_protected_ready_snapshot
from tests.fixtures.workflows.guardrails import stage_payload, write_payload


class NonAiFlowTests(CliTestCase):
    def test_list_and_run_work_after_integration_removed(self) -> None:
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
        self.cli(["integration", "remove", "codex", "--project", str(self.project), "--force"])
        self.assertEqual(self.cli(["list", "--project", str(self.project)])[0], 0)
        self.assertEqual(self.cli(["run", "login", "--project", str(self.project), "--non-interactive"])[0], 0)

    def test_workflow_persist_specify_without_agent_session(self) -> None:
        self.cli(["init", str(self.project), "--integration", "codex"])
        payload = stage_payload(
            "specify",
            payload={
                "alias": "login",
                "surface": "/login",
                "behavior": "Validate login.",
                "expectedOutcome": "Dashboard.",
                "customSourceReason": "Non-AI smoke fixture.",
            },
        )
        code, _, err = self.cli([
            "workflow",
            "persist",
            "specify",
            "--alias",
            "login",
            "--project",
            str(self.project),
            "--payload",
            str(write_payload(self.project, "specify", payload)),
            "--json",
        ])
        self.assertEqual(code, 0, err)
        self.assertTrue((self.project / ".verifysignal/use-cases/login.yaml").exists())
