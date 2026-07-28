from __future__ import annotations

import json
import os

from helpers import CliTestCase

from tests.fixtures.workflows.guardrails import create_ready_use_case_workspace, create_registry_missing_record_path
from tests.fixtures.workflows.main_skill_run_coverage import create_main_skill_coverage_workspace
from tests.fixtures.workflows.skill_execution_boundary import ALIAS, LOGIN_SKILL_ID, MAIN_SKILL_ID, create_planned_workspace, implementation_payload
from verifysignal_spec.workflows.stage_persistence import persist_stage
from verifysignal_spec.workspace.repository import load_document, save_document


class ValidationReadinessContractTests(CliTestCase):
    def test_structural_validation_runs_when_core_is_missing(self) -> None:
        create_ready_use_case_workspace(self.project, "login")
        workspace_path = self.project / ".verifysignal/workspace.yaml"
        workspace = load_document(workspace_path)
        workspace["coreCommand"] = "missing-verifysignal-core-for-test"
        save_document(workspace_path, workspace)
        code, out, err = self.cli([
            "workflow",
            "check",
            "validate",
            "--alias",
            "login",
            "--project",
            str(self.project),
            "--json",
        ])
        self.assertEqual(code, 2, err)
        result = json.loads(out)
        self.assertEqual(result["schemaVersion"], "verifysignal-spec-validation-readiness/v1")
        self.assertEqual(result["structuralValidation"]["status"], "pass")
        self.assertEqual(result["coreReadiness"]["status"], "missing")
        self.assertEqual(result["coreReadiness"]["contractVersion"], "verifysignal-public-cli-json/v1")
        self.assertIn("report.inspect", result["coreReadiness"]["requiredOperationsByName"])
        self.assertIn("complete VerifySignal validation and browser execution experience", result["coreReadiness"]["message"])
        blocker = next(item for item in result["blockers"] if item["code"] == "core.missing")
        self.assertEqual(blocker["category"], "environment")
        self.assertEqual(blocker["recoveryCommand"], "verifysignal core setup --json")
        self.assertFalse(blocker["repairable"])

    def test_core_compatibility_fields_are_reported_when_core_is_available(self) -> None:
        create_ready_use_case_workspace(self.project, "login")
        code, out, err = self.cli([
            "workflow",
            "check",
            "validate",
            "--alias",
            "login",
            "--project",
            str(self.project),
            "--json",
        ])
        self.assertEqual(code, 0, err)
        result = json.loads(out)
        self.assertEqual(result["coreReadiness"]["status"], "available")
        self.assertEqual(result["coreReadiness"]["contractVersion"], "verifysignal-public-cli-json/v1")
        self.assertEqual(result["coreReadiness"]["missingOperations"], [])
        self.assertEqual(result["coreReadiness"]["requiredOperationsByName"]["authoring-check"]["schemaName"], "verifysignal.authoring-check/v1")

    def test_structural_readiness_exposes_runtime_boundary_and_exact_next_action(self) -> None:
        create_ready_use_case_workspace(self.project, "login")

        code, out, err = self.cli([
            "workflow",
            "check",
            "validate",
            "--alias",
            "login",
            "--project",
            str(self.project),
            "--json",
        ])

        self.assertEqual(code, 0, err)
        result = json.loads(out)
        self.assertEqual(result["readinessScope"], "structural")
        self.assertTrue(result["runtimeReadinessRequired"])
        self.assertEqual(result["runtimeReadinessStatus"], "not-run")
        self.assertEqual(
            result["runtimeReadinessCommand"],
            "verifysignal validate login --runtime-readiness --json",
        )
        self.assertEqual(result["nextAction"], result["runtimeReadinessCommand"])
        self.assertIn("entitlement readiness have not run", result["readinessSummary"])
        self.assertNotIn("complete runtime readiness passed", result["readinessSummary"].lower())

    def test_blocked_structural_readiness_preserves_recovery_before_runtime_validation(self) -> None:
        create_ready_use_case_workspace(self.project, "login")
        workspace_path = self.project / ".verifysignal/workspace.yaml"
        workspace = load_document(workspace_path)
        workspace["coreCommand"] = "missing-verifysignal-core-for-test"
        save_document(workspace_path, workspace)

        code, out, err = self.cli([
            "workflow",
            "check",
            "validate",
            "--alias",
            "login",
            "--project",
            str(self.project),
            "--json",
        ])

        self.assertEqual(code, 2, err)
        result = json.loads(out)
        self.assertEqual(result["readinessScope"], "structural")
        self.assertEqual(result["runtimeReadinessStatus"], "not-run")
        self.assertEqual(
            result["runtimeReadinessCommand"],
            "verifysignal validate login --runtime-readiness --json",
        )
        self.assertEqual(result["nextAction"], "verifysignal core setup --json")
        self.assertIn("must be resolved first", result["readinessSummary"])

    def test_core_incompatible_schema_reports_public_operation_details(self) -> None:
        create_ready_use_case_workspace(self.project, "login")
        os.environ["FAKE_VERIFYSIGNAL_MODE"] = "incompatible-run-schema"

        code, out, err = self.cli([
            "workflow",
            "check",
            "validate",
            "--alias",
            "login",
            "--project",
            str(self.project),
            "--json",
        ])

        self.assertEqual(code, 2, err)
        result = json.loads(out)
        self.assertEqual(result["coreReadiness"]["status"], "incompatible")
        self.assertEqual(result["coreReadiness"]["incompatibleOperations"][0]["operationName"], "run")
        self.assertEqual(result["coreReadiness"]["incompatibleOperations"][0]["actualSchema"], "verifysignal.run/v2")
        self.assertIn("Upgrade VerifySignal Core", result["coreReadiness"]["recoveryAction"])

    def test_malformed_registry_returns_migration_plan(self) -> None:
        create_registry_missing_record_path(self.project, "login")
        code, out, err = self.cli([
            "workflow",
            "check",
            "validate",
            "--alias",
            "login",
            "--project",
            str(self.project),
            "--json",
        ])
        self.assertEqual(code, 2, err)
        result = json.loads(out)
        self.assertEqual(result["status"], "blocked")
        plans = result["structuralValidation"]["migrationPlans"]
        self.assertEqual(plans[0]["id"], "migrate-registry-record-path-login")

    def test_migration_requires_current_approved_plan(self) -> None:
        create_registry_missing_record_path(self.project, "login")
        code, out, err = self.cli([
            "workflow",
            "migrate",
            "--approve",
            "migrate-registry-record-path-login",
            "--project",
            str(self.project),
            "--json",
        ])
        self.assertEqual(code, 0, err)
        result = json.loads(out)
        self.assertEqual(result["schemaVersion"], "verifysignal-spec-workflow-migration-result/v1")
        self.assertEqual(result["status"], "applied")

        code, out, err = self.cli([
            "workflow",
            "migrate",
            "--approve",
            "migrate-registry-record-path-login",
            "--project",
            str(self.project),
            "--json",
        ])
        self.assertEqual(code, 2, err)
        self.assertEqual(json.loads(out)["status"], "blocked")

    def test_validate_output_describes_authored_evidence_not_executed_browser_flow(self) -> None:
        create_main_skill_coverage_workspace(self.project)

        code, out, err = self.cli([
            "validate",
            "profile-view-unauth",
            "--project",
            str(self.project),
            "--runtime-readiness",
            "--json",
        ])

        self.assertEqual(code, 0, err)
        result = json.loads(out)
        self.assertEqual(result["authoredEvidenceCoverageStatus"], "complete")
        self.assertEqual(result["runtimeReadinessStatus"], "passed")
        self.assertFalse(result["fullBrowserFlowExecuted"])
        self.assertIn("mapped authored evidence", result["readinessSummary"])
        self.assertIn("full browser flow has not executed", result["readinessSummary"])

    def test_execution_boundary_blocks_legacy_multi_skill_run_request_when_core_is_unsupported(self) -> None:
        create_planned_workspace(self.project)
        result = persist_stage(self.project, "implement", alias=ALIAS, payload=implementation_payload(composed_main=True))
        self.assertEqual(result["status"], "persisted")
        run_request_path = self.project / f".verifysignal/run-requests/{ALIAS}.yaml"
        run_request = load_document(run_request_path)
        run_request["skills"] = [
            {"id": MAIN_SKILL_ID, "version": "1.0.0"},
            {"id": LOGIN_SKILL_ID, "version": "1.0.0"},
        ]
        save_document(run_request_path, run_request)

        code, out, err = self.cli([
            "workflow",
            "check",
            "validate",
            "--alias",
            ALIAS,
            "--project",
            str(self.project),
            "--json",
        ])

        self.assertEqual(code, 2, err)
        payload = json.loads(out)
        self.assertEqual(payload["status"], "blocked")
        blocker = next(item for item in payload["blockers"] if item["code"] == "skill-execution.legacy-migration-required")
        self.assertEqual(blocker["category"], "skill-execution-boundary")
        self.assertIn("source-only", blocker["message"])
