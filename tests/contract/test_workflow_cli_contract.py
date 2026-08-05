from __future__ import annotations

import json
from unittest.mock import patch

from helpers import CliTestCase


class WorkflowCliContractTests(CliTestCase):
    def test_json_init_permission_failure_is_structured_and_actionable(
        self,
    ) -> None:
        with patch(
            "verifysignal_spec.commands.integration.install_rendered_files",
            side_effect=PermissionError(
                "Operation not permitted: '.agents/VERIFYSIGNAL_ONBOARDING.md'"
            ),
        ):
            code, out, err = self.cli(
                [
                    "init",
                    str(self.project),
                    "--integration",
                    "codex",
                    "--json",
                ]
            )

        self.assertEqual(code, 2)
        self.assertEqual(err, "")
        payload = json.loads(out)
        self.assertEqual(
            payload["schemaVersion"],
            "verifysignal-spec-cli-error/v1",
        )
        self.assertEqual(payload["status"], "blocked")
        self.assertEqual(
            payload["blockers"][0]["code"],
            "workspace.permission-denied",
        )
        self.assertFalse(payload["blockers"][0]["repairable"])
        self.assertIn("Grant write access", payload["nextAction"])
        self.assertNotIn("Traceback", out)

    def test_inline_json_passed_as_payload_reports_stdin_recovery(self) -> None:
        code, out, err = self.cli(
            [
                "workflow",
                "persist",
                "understand",
                "--scope",
                "all",
                "--payload",
                '{"understandingMode":"browser-first"}',
                "--project",
                str(self.project),
                "--json",
            ]
        )

        self.assertNotEqual(code, 0)
        self.assertEqual(out, "")
        self.assertIn("--payload expects a JSON/YAML file path", err)
        self.assertIn("--stdin", err)
        self.assertNotIn("File name too long", err)

    def test_workflow_info_json_contract(self) -> None:
        code, out, err = self.cli(["workflow", "info", "verifysignal-use-case", "--project", str(self.project), "--json"])
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertEqual(payload["schemaVersion"], "verifysignal-spec-workflow-info/v1")
        self.assertEqual(payload["integration"], "codex")
        self.assertEqual(payload["nativeCommands"]["understand"], "$verifysignal-understand")

        code, out, err = self.cli([
            "workflow",
            "info",
            "verifysignal-use-case",
            "--integration",
            "claude",
            "--project",
            str(self.project),
            "--json",
        ])
        self.assertEqual(code, 0, err)
        claude = json.loads(out)
        self.assertEqual(claude["nativeCommands"]["understand"], "/verifysignal-understand")

    def test_workflow_run_status_and_resume_contract(self) -> None:
        self.cli(["init", str(self.project), "--integration", "codex", "--json"])
        code, out, err = self.cli([
            "workflow",
            "run",
            "verifysignal-use-case",
            "--goal",
            "Validate login.",
            "--alias",
            "login",
            "--project",
            str(self.project),
            "--json",
        ])
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertEqual(payload["schemaVersion"], "verifysignal-spec-workflow-run/v1")
        self.assertEqual(payload["currentStage"], "specify")
        self.assertEqual(payload["nextCommand"], "$verifysignal-specify login")

        code, out, err = self.cli(["workflow", "status", payload["runId"], "--project", str(self.project), "--json"])
        self.assertEqual(code, 0, err)
        status = json.loads(out)
        self.assertEqual(status["runId"], payload["runId"])
        self.assertEqual(status["currentStage"], "specify")
        self.assertEqual(status["nextCommand"], "$verifysignal-specify login")

    def test_codex_status_normalizes_legacy_slash_command_without_rewriting_history(self) -> None:
        self.cli(["init", str(self.project), "--integration", "codex", "--json"])
        code, out, err = self.cli([
            "workflow",
            "run",
            "verifysignal-use-case",
            "--goal",
            "Validate login.",
            "--alias",
            "legacy-login",
            "--project",
            str(self.project),
            "--json",
        ])
        self.assertEqual(code, 0, err)
        run_id = json.loads(out)["runId"]
        run_path = self.project / ".verifysignal" / "workflows" / "runs" / f"{run_id}.yaml"
        legacy = run_path.read_text(encoding="utf-8").replace(
            "$verifysignal-specify", "/verifysignal-specify"
        )
        run_path.write_text(legacy, encoding="utf-8")

        code, out, err = self.cli(
            ["workflow", "status", run_id, "--project", str(self.project), "--json"]
        )

        self.assertEqual(code, 0, err)
        status = json.loads(out)
        self.assertEqual(status["nextCommand"], "$verifysignal-specify legacy-login")
        self.assertIn("/verifysignal-specify", run_path.read_text(encoding="utf-8"))

    def test_workflow_validate_contract_uses_existing_core_adapter(self) -> None:
        self.cli(["init", str(self.project), "--integration", "codex", "--json"])
        self.cli(["author", "login", "Validate login.", "--project", str(self.project), "--json"])
        code, out, err = self.cli(["validate", "login", "--project", str(self.project), "--json"])
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertIn("core", payload)
