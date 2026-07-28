from __future__ import annotations

import json

from helpers import CliTestCase

from tests.fixtures.workflows.prerequisites import (
    create_current_understanding_workspace,
    create_stale_understanding_workspace,
)
from tests.fixtures.workflows.guardrails import stage_payload, write_payload


class WorkflowPrerequisiteCheckContractTests(CliTestCase):
    def test_missing_specify_check_json_shape(self) -> None:
        code, out, err = self.cli(["workflow", "check", "specify", "--project", str(self.project), "--json"])
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertEqual(payload["schemaVersion"], "verifysignal-spec-workflow-capability/v1")
        self.assertEqual(payload["prerequisiteSchemaVersion"], "verifysignal-spec-workflow-prerequisite-check/v1")
        self.assertEqual(payload["requiredCapability"], "workflow.guardrails/v1")
        self.assertTrue(payload["supported"])
        self.assertEqual(payload["stage"], "specify")
        self.assertIsNone(payload["useCaseAlias"])
        self.assertEqual(payload["status"], "missing")
        self.assertFalse(payload["canProceed"])
        self.assertEqual(payload["nextCommand"], "$verifysignal-understand")

    def test_ready_stale_accepted_and_declined_refresh_responses(self) -> None:
        create_current_understanding_workspace(self.project)
        code, out, err = self.cli(["workflow", "check", "specify", "--project", str(self.project), "--json"])
        self.assertEqual(code, 0, err)
        ready = json.loads(out)
        self.assertEqual(ready["status"], "ready")
        self.assertTrue(ready["canProceed"])
        self.assertIn("candidateUseCases", ready)

        create_stale_understanding_workspace(self.project)
        code, out, err = self.cli(["workflow", "check", "specify", "--project", str(self.project), "--json"])
        self.assertEqual(code, 0, err)
        stale = json.loads(out)
        self.assertEqual(stale["status"], "stale")
        self.assertTrue(stale["canProceed"])
        self.assertTrue(stale["requiresConfirmation"])
        self.assertEqual(stale["recommendedAction"], "refresh-understanding")

        code, out, err = self.cli([
            "workflow",
            "check",
            "specify",
            "--project",
            str(self.project),
            "--refresh-decision",
            "accepted",
            "--json",
        ])
        self.assertEqual(code, 0, err)
        accepted = json.loads(out)
        self.assertEqual(accepted["status"], "stale")
        self.assertFalse(accepted["canProceed"])
        self.assertEqual(accepted["recordedDecision"]["decision"], "accepted")
        self.assertEqual(accepted["nextCommand"], "$verifysignal-understand")

        code, out, err = self.cli([
            "workflow",
            "check",
            "specify",
            "--project",
            str(self.project),
            "--refresh-decision",
            "declined",
            "--json",
        ])
        self.assertEqual(code, 0, err)
        declined = json.loads(out)
        self.assertEqual(declined["status"], "stale")
        self.assertTrue(declined["canProceed"])
        self.assertFalse(declined["requiresConfirmation"])
        self.assertEqual(declined["recordedDecision"]["decision"], "declined")
        self.assertTrue(declined["warnings"])

    def test_later_stage_missing_artifact_matrix(self) -> None:
        self.cli(["init", str(self.project), "--integration", "codex", "--json"])
        self.cli([
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

        code, out, err = self.cli([
            "workflow",
            "check",
            "clarify",
            "--alias",
            "login",
            "--project",
            str(self.project),
            "--json",
        ])
        self.assertEqual(code, 0, err)
        clarify = json.loads(out)
        self.assertEqual(clarify["status"], "missing")
        self.assertEqual(clarify["nextCommand"], "$verifysignal-specify login")

        self.cli(["workflow", "check", "specify", "--project", str(self.project), "--json"])
        from verifysignal_spec.workflows.engine import specify

        specify(self.project, "login", "Validate login.")
        code, out, err = self.cli([
            "workflow",
            "check",
            "tasks",
            "--alias",
            "login",
            "--project",
            str(self.project),
            "--json",
        ])
        self.assertEqual(code, 0, err)
        tasks = json.loads(out)
        self.assertEqual(tasks["status"], "missing")
        self.assertEqual(tasks["nextCommand"], "$verifysignal-plan login")

    def test_unresolved_browser_target_blocks_plan_check(self) -> None:
        create_current_understanding_workspace(self.project)
        specify_payload = stage_payload(
            "specify",
            payload={
                "alias": "profile-view-unauth",
                "surface": "/profile/:id/overview",
                "behavior": "Validate public profile rendering.",
                "expectedOutcome": "Profile renders.",
                "customSourceReason": "Browser target prerequisite contract.",
            },
        )
        self.cli([
            "workflow",
            "persist",
            "specify",
            "--alias",
            "profile-view-unauth",
            "--project",
            str(self.project),
            "--payload",
            str(write_payload(self.project, "specify-browser-target", specify_payload)),
            "--json",
        ])

        code, out, err = self.cli([
            "workflow",
            "check",
            "plan",
            "--alias",
            "profile-view-unauth",
            "--project",
            str(self.project),
            "--json",
        ])

        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertEqual(payload["status"], "missing")
        self.assertEqual(payload["nextCommand"], "$verifysignal-clarify profile-view-unauth")
        self.assertIn("authoringQuestions", payload["missingArtifacts"][0])

    def test_ambiguous_alias_requires_selector(self) -> None:
        self.cli(["init", str(self.project), "--integration", "codex", "--json"])
        for alias in ["login", "checkout"]:
            self.cli([
                "workflow",
                "run",
                "verifysignal-use-case",
                "--goal",
                f"Validate {alias}.",
                "--alias",
                alias,
                "--project",
                str(self.project),
                "--json",
            ])
        code, out, err = self.cli(["workflow", "check", "plan", "--project", str(self.project), "--json"])
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertEqual(payload["status"], "ambiguous")
        self.assertTrue(payload["requiresConfirmation"])
        self.assertEqual(payload["recommendedAction"], "choose-alias")
        self.assertEqual(sorted(payload["availableAliases"]), ["checkout", "login"])
