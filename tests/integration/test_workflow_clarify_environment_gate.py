from __future__ import annotations

import json

from helpers import CliTestCase

from tests.fixtures.workflows.guardrails import stage_payload, write_payload
from tests.fixtures.workflows.prerequisites import create_current_understanding_workspace
from verifysignal_spec.workflows.engine import create_workflow_run


class WorkflowClarifyEnvironmentGateIntegrationTests(CliTestCase):
    def test_plan_check_routes_back_to_clarify_for_unresolved_runtime_question(self) -> None:
        self.cli(["init", str(self.project), "--integration", "codex", "--json"])
        create_current_understanding_workspace(self.project)
        create_workflow_run(
            self.project,
            "Validate login.",
            alias="login",
            integration="codex",
        )
        self.cli([
            "workflow",
            "persist",
            "specify",
            "--alias",
            "login",
            "--project",
            str(self.project),
            "--payload",
            str(write_payload(self.project, "specify", stage_payload("specify", payload={
                "alias": "login",
                "surface": "/login",
                "behavior": "Validate login.",
                "expectedOutcome": "Dashboard.",
                "customSourceReason": "Fixture.",
            }))),
            "--json",
        ])
        self.cli([
            "workflow",
            "persist",
            "clarify",
            "--alias",
            "login",
            "--project",
            str(self.project),
            "--payload",
            str(write_payload(self.project, "clarify", stage_payload("clarify", payload={
                "alias": "login",
                "questions": [{
                    "id": "q1",
                    "prompt": "Which runtime base URL?",
                    "reason": "Runtime configuration affects execution.",
                    "affects": "runtime",
                    "environmentDependent": True,
                }],
                "answers": [
                    {
                        "questionId": "browser-target-environment",
                        "answerSummary": "Use https://app.example.test for this workflow.",
                        "confirmationSource": "direct-user",
                    }
                ],
                "blockingQuestionsResolved": False,
            }))),
            "--json",
        ])
        code, out, err = self.cli(["workflow", "check", "plan", "--alias", "login", "--project", str(self.project), "--json"])
        self.assertEqual(code, 0, err)
        result = json.loads(out)
        self.assertEqual(result["status"], "missing")
        self.assertEqual(result["nextCommand"], "$verifysignal-clarify login")
