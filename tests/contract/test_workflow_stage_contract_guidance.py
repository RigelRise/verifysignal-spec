from __future__ import annotations

import json

from helpers import CliTestCase, agent_template, assert_public_workflow_contract_guidance


class WorkflowStageContractGuidanceTests(CliTestCase):
    def test_workflow_info_exposes_public_stage_payload_contracts(self) -> None:
        code, out, err = self.cli(["workflow", "info", "verifysignal-use-case", "--project", str(self.project), "--json"])

        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        contracts = payload["stagePayloadContracts"]

        self.assertEqual(contracts["schemaVersion"], "verifysignal-spec-stage-payload-contracts/v1")
        self.assertEqual(set(contracts["stages"]), {"understand", "specify", "clarify", "plan", "tasks", "implement"})
        self.assertIn("coverageInventory", contracts["byStage"]["understand"]["requiredFields"])
        self.assertIn("expectedOutcome", contracts["byStage"]["specify"]["requiredFields"])
        self.assertIn("validationGates", contracts["byStage"]["plan"]["optionalFields"])
        self.assertEqual(contracts["byStage"]["implement"]["unsupportedFieldsPolicy"], "warn")
        self.assertNotIn("stage_persistence.py", json.dumps(contracts))

    def test_generated_stage_templates_reference_public_contracts(self) -> None:
        for stage in ["specify", "clarify", "plan", "tasks", "implement"]:
            assert_public_workflow_contract_guidance(agent_template(stage))

    def test_skill_boundary_agent_parity_guidance_is_public_and_structured(self) -> None:
        code, out, err = self.cli(["workflow", "info", "verifysignal-use-case", "--project", str(self.project), "--json"])

        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        boundary = payload["stagePayloadContracts"]["skillExecutionBoundary"]
        implement_template = agent_template("implement")

        self.assertEqual(boundary["defaultMode"], "single-main")
        self.assertIn("sourceOnlySkills", boundary["planFields"])
        self.assertIn("skillComposition", boundary["implementFields"])
        self.assertIn("skill-execution.legacy-migration-required", boundary["findingCodes"])
        self.assertIn("stagePayloadContracts.skillExecutionBoundary", implement_template)
        self.assertIn("inline required reusable behavior", implement_template)
        self.assertIn("coreExecutableContract.sections.skillExecution", implement_template)
