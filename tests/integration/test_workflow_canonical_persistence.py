from __future__ import annotations

import json

from helpers import FAKE_CORE, CliTestCase

from tests.fixtures.workflows.guardrails import stage_payload, write_payload


class WorkflowCanonicalPersistenceIntegrationTests(CliTestCase):
    def test_full_cli_persistence_flow_creates_listable_use_case(self) -> None:
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
        code, _out, err = self.cli(
            [
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
            ]
        )
        self.assertEqual(code, 0, err)
        payloads = {
            "specify": {
                "alias": "login",
                "surface": "/login",
                "behavior": "Validate login.",
                "expectedOutcome": "Dashboard is visible.",
                "customSourceReason": "Fixture.",
            },
            "clarify": {
                "alias": "login",
                "questions": [],
                "answers": [
                    {
                        "questionId": "browser-target-environment",
                        "answerSummary": "Use https://app.example.test for this workflow.",
                        "confirmationSource": "direct-user",
                    }
                ],
                "blockingQuestionsResolved": True,
            },
            "plan": {
                "alias": "login",
                "runRequest": ".verifysignal/run-requests/login.yaml",
                "reusableSkills": [".verifysignal/skills/login.browser.md"],
                "runtimeInputs": [{"name": "BASE_URL", "source": "environment"}],
                "unresolvedBlockingClarifications": [],
            },
            "tasks": {
                "alias": "login",
                "tasks": [{"id": "T001", "description": "Create login run request.", "artifact": "run-request"}],
                "dependencies": [],
                "parallelizableGroups": [],
            },
            "implement": {
                "alias": "login",
                "runRequest": {
                    "path": ".verifysignal/run-requests/login.yaml",
                    "content": '{"schemaVersion":"qa-run-request/v1","request":{"id":"request.login"}}',
                },
                "skills": [
                    {
                        "path": ".verifysignal/skills/login.browser.md",
                        "content": "---\nschemaVersion: qa-skill/v1\n---\n# Login\n",
                    }
                ],
                "recordUpdates": {},
            },
        }
        for stage, payload in payloads.items():
            code, out, err = self.cli([
                "workflow",
                "persist",
                stage,
                "--alias",
                "login",
                "--project",
                str(self.project),
                "--payload",
                str(write_payload(self.project, stage, stage_payload(stage, payload=payload))),
                "--json",
            ])
            self.assertEqual(code, 0, f"{stage}: {err}\n{out}")
            self.assertEqual(
                json.loads(out)["status"],
                "persisted",
                f"{stage}: {out}",
            )

        code, out, err = self.cli(["list", "--project", str(self.project), "--json"])
        self.assertEqual(code, 0, err)
        use_cases = json.loads(out)["useCases"]
        self.assertEqual(use_cases[0]["alias"], "login")
        self.assertTrue((self.project / ".verifysignal/skills/login.browser.md").exists())
        self.assertTrue((self.project / ".verifysignal/use-cases/login.yaml").exists())
