from __future__ import annotations

import json

from helpers import FAKE_CORE, CliTestCase


class WorkflowCoreContractGuidanceTests(CliTestCase):
    def test_workflow_info_separates_spec_policy_and_redacted_core_contract(self) -> None:
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

        code, out, err = self.cli(["workflow", "info", "--project", str(self.project), "--json"])

        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertEqual(payload["coreExecutableContract"]["source"], "core-public-contract")
        self.assertEqual(payload["specWorkflowPolicy"]["source"], "verifysignal-spec")
        self.assertIn("gate-adequacy", {item["name"] for item in payload["specWorkflowPolicy"]["policies"]})
        self.assertNotIn("validActions", json.dumps(payload["specWorkflowPolicy"]))
        self.assertEqual(payload["coreExecutableContract"]["runtimeIdentity"], "[redacted]")
        policy = payload["coreExecutableContract"]["sections"]["publicRedactionPolicy"]
        self.assertIn("rawValue", policy["publicErrorShape"]["forbiddenFields"])
        self.assertIn("signedUrl", policy["safeEvidenceReferences"]["forbiddenFields"])
        self.assertNotIn("redactFields", policy)
