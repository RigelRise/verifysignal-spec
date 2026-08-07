from __future__ import annotations

from helpers import FAKE_CORE, CliTestCase
from tests.fixtures.workflows.entitlement_preflight_recovery import write_active_run_documents
from verifysignal_spec.workspace.models import RuntimeInputRequirement
from verifysignal_spec.workspace.repository import (
    load_document,
    load_use_case,
    save_document,
    save_use_case,
)


class CliSmokeTests(CliTestCase):
    def test_init_author_list_run_repair_smoke(self) -> None:
        self.assertEqual(
            self.cli([
                "init",
                str(self.project),
                "--integration",
                "codex",
                "--core-cmd",
                str(FAKE_CORE),
            ])[0],
            0,
        )
        self.assertEqual(self.cli(["author", "login", "Validate login.", "--project", str(self.project)])[0], 0)
        record = load_use_case(self.project, "login")
        record.runtimeInputs = [
            RuntimeInputRequirement(
                name="baseUrl",
                source="default",
                value="https://example.test",
            )
        ]
        target_question = record.authoringQuestions[0]
        target_question.status = "answered"
        target_question.answerSummary = "https://example.test"
        target_question.confirmationSource = "direct-user"
        save_use_case(self.project, record)
        assert record.runRequest is not None
        request_path = self.project / record.runRequest.path
        request = load_document(request_path)
        request["parameters"] = {"baseUrl": "https://example.test"}
        save_document(request_path, request)
        write_active_run_documents(self.project, "login")
        self.assertEqual(self.cli(["list", "--project", str(self.project)])[0], 0)
        self.assertEqual(
            self.cli([
                "validate",
                "login",
                "--project",
                str(self.project),
                "--runtime-readiness",
            ])[0],
            0,
        )
        self.assertEqual(self.cli(["run", "login", "--project", str(self.project), "--non-interactive"])[0], 0)
        self.assertEqual(self.cli(["repair", "login", "--project", str(self.project)])[0], 4)
