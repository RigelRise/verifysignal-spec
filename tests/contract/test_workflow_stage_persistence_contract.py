from __future__ import annotations

import json
import os

from helpers import CliTestCase, assert_no_core_contract_snapshots

from tests.fixtures.workflows.main_skill_run_coverage import HELPER_SKILL_PATH, MAIN_SKILL_PATH, create_main_skill_coverage_workspace
from tests.fixtures.workflows.guardrails import stage_payload, write_payload
from tests.fixtures.workflows.prerequisites import create_current_understanding_workspace
from verifysignal_spec.workspace.repository import load_document, load_refresh_impact


class WorkflowStagePersistenceContractTests(CliTestCase):
    def test_workflow_info_defaults_to_current_workflow_and_includes_browser_authoring_contract(self) -> None:
        self.cli(["init", str(self.project), "--integration", "codex", "--json"])

        code, out, err = self.cli(["workflow", "info", "--project", str(self.project), "--json"])

        self.assertEqual(code, 0, err)
        result = json.loads(out)
        self.assertEqual(result["schemaVersion"], "verifysignal-spec-workflow-info/v1")
        self.assertEqual(result["workflowId"], "verifysignal-use-case")
        contract = result["browserAuthoringContract"]
        self.assertEqual(contract["source"], "core-public-contract")
        self.assertIn("navigate", contract["validActions"])
        self.assertIn("text", contract["validAssertionKinds"])
        self.assertIn("method", contract["validNetworkMatchKeys"])
        self.assertIn("stepsReferenceNamedTargets", contract["targetRules"])
        self.assertEqual(result["coreExecutableContract"]["source"], "core-public-contract")
        self.assertIn("runRequest", result["coreExecutableContract"]["sections"])
        self.assertIn("skill", result["coreExecutableContract"]["sections"])

    def test_workflow_info_includes_live_write_readiness_stage_fields(self) -> None:
        self.cli(["init", str(self.project), "--integration", "codex", "--json"])

        code, out, err = self.cli(["workflow", "info", "--project", str(self.project), "--json"])

        self.assertEqual(code, 0, err)
        result = json.loads(out)
        clarify = result["stagePayloadContracts"]["byStage"]["clarify"]["optionalFields"]
        implement = result["stagePayloadContracts"]["byStage"]["implement"]["optionalFields"]
        self.assertIn("credentialReadinessHints", clarify)
        self.assertIn("sideEffectLifecycle", clarify)
        self.assertIn("credentialReadinessHints", implement)
        self.assertIn("sideEffectLifecycle", implement)
        self.assertIn("artifactCapabilities", implement)

    def test_workflow_info_projects_current_core_contract_shape(self) -> None:
        os.environ["FAKE_VERIFYSIGNAL_MODE"] = "current-contract"
        self.cli(["init", str(self.project), "--integration", "codex", "--json"])

        code, out, err = self.cli(["workflow", "info", "--project", str(self.project), "--json"])

        self.assertEqual(code, 0, err)
        result = json.loads(out)
        authoring = result["browserAuthoringContract"]
        core = result["coreExecutableContract"]
        self.assertIn("urlContains", authoring["validNetworkMatchKeys"])
        self.assertIn("request.id", core["sections"]["runRequest"]["fieldNames"])

    def test_workflow_info_projects_current_field_schema_and_credential_metadata(self) -> None:
        os.environ["FAKE_VERIFYSIGNAL_MODE"] = "current-contract"
        self.cli(["init", str(self.project), "--integration", "codex", "--json"])

        code, out, err = self.cli(["workflow", "info", "--project", str(self.project), "--json"])

        self.assertEqual(code, 0, err)
        result = json.loads(out)
        core = result["coreExecutableContract"]
        self.assertEqual(core["sections"]["runRequest"]["artifactSchemaVersion"], "qa-run-request/v1")
        self.assertEqual(core["sections"]["skill"]["artifactSchemaVersion"], "qa-skill/v1")
        self.assertIn("request.id", core["sections"]["runRequest"]["fieldNames"])
        self.assertIn("browser.targets", core["sections"]["skill"]["fieldNames"])
        self.assertIn("environment", core["sections"]["credentials"]["sourceNames"])
        self.assertEqual(core["sections"]["credentials"]["placeholderSyntax"], "{{credentials.<group>.<field>}}")

    def test_workflow_info_does_not_persist_core_contract_projection_cache(self) -> None:
        os.environ["FAKE_VERIFYSIGNAL_MODE"] = "current-contract"
        self.cli(["init", str(self.project), "--integration", "codex", "--json"])

        code, _out, err = self.cli(["workflow", "info", "--project", str(self.project), "--json"])

        self.assertEqual(code, 0, err)
        assert_no_core_contract_snapshots(self.project)

    def test_understand_persists_product_context_and_inventory(self) -> None:
        payload = stage_payload(
            "understand",
            payload={
                "repositorySummary": "Example app.",
                "localStartInstructions": "npm run dev",
                "generatedGitHash": "abc123",
                "coverageInventory": {
                    "generatedAt": "2026-05-25T00:00:00Z",
                    "generatedGitHash": "abc123",
                    "gitAvailable": True,
                    "items": [
                        {
                            "id": "route-login",
                            "surfaceType": "route",
                            "path": "/login",
                            "title": "Login",
                            "sourceRefs": ["app/login/page.tsx"],
                            "candidateUseCaseRefs": ["login"],
                            "priority": "high",
                        }
                    ],
                    "candidateUseCases": [
                        {
                            "alias": "login",
                            "surface": "/login",
                            "behavior": "Validate login.",
                            "sourceInventoryItems": ["route-login"],
                            "rationale": "Critical auth entry point.",
                            "confidence": "high",
                        }
                    ],
                },
                "refreshImpacts": [
                    {
                        "alias": "existing-write-flow",
                        "status": "unaffected",
                        "reason": "Refresh only touched unrelated public routes.",
                        "recommendedAction": "none",
                    }
                ],
            },
        )
        code, out, err = self.cli([
            "workflow",
            "persist",
            "understand",
            "--project",
            str(self.project),
            "--scope",
            "all",
            "--payload",
            str(write_payload(self.project, "understand", payload)),
            "--json",
        ])
        self.assertEqual(code, 0, err)
        result = json.loads(out)
        self.assertEqual(result["schemaVersion"], "verifysignal-spec-workflow-stage-persistence-result/v1")
        self.assertEqual(result["status"], "persisted")
        self.assertTrue((self.project / ".verifysignal/product-context.yaml").exists())
        self.assertTrue((self.project / ".verifysignal/workflows/understanding.md").exists())
        impact = load_refresh_impact(self.project, "existing-write-flow")
        self.assertIsNotNone(impact)
        self.assertEqual(impact.status, "unaffected")
        self.assertEqual(impact.recommendedAction, "none")

    def test_plan_blocks_unresolved_environment_dependent_clarification(self) -> None:
        self.cli(["init", str(self.project), "--integration", "codex", "--json"])
        specify_payload = stage_payload(
            "specify",
            payload={
                "alias": "login",
                "surface": "/login",
                "behavior": "Validate login.",
                "expectedOutcome": "User reaches the dashboard.",
                "customSourceReason": "Manual test fixture.",
            },
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
            str(write_payload(self.project, "specify", specify_payload)),
            "--json",
        ])
        clarify_payload = stage_payload(
            "clarify",
            payload={
                "alias": "login",
                "questions": [
                    {
                        "id": "q1",
                        "prompt": "Which credential group should be used?",
                        "reason": "Credential context changes runtime setup.",
                        "affects": "credentials",
                        "environmentDependent": True,
                    }
                ],
                "answers": [
                    {
                        "questionId": "browser-target-environment",
                        "answerSummary": "Use https://app.example.test for this workflow.",
                        "confirmationSource": "direct-user",
                    }
                ],
                "blockingQuestionsResolved": False,
            },
        )
        self.cli([
            "workflow",
            "persist",
            "clarify",
            "--alias",
            "login",
            "--project",
            str(self.project),
            "--payload",
            str(write_payload(self.project, "clarify", clarify_payload)),
            "--json",
        ])

        plan_payload = stage_payload(
            "plan",
            payload={
                "alias": "login",
                "runRequest": ".verifysignal/run-requests/login.yaml",
                "reusableSkills": [".verifysignal/skills/login.browser.md"],
                "runtimeInputs": [],
                "unresolvedBlockingClarifications": [{"id": "q1"}],
            },
        )
        code, out, err = self.cli([
            "workflow",
            "persist",
            "plan",
            "--alias",
            "login",
            "--project",
            str(self.project),
            "--payload",
            str(write_payload(self.project, "plan", plan_payload)),
            "--json",
        ])
        self.assertEqual(code, 2, err)
        result = json.loads(out)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["blockers"][0]["code"], "clarification.unresolved-blocking")

    def test_resolved_browser_target_is_preserved_from_clarify_to_plan(self) -> None:
        create_current_understanding_workspace(self.project)
        specify_payload = stage_payload(
            "specify",
            payload={
                "alias": "profile",
                "surface": "/profile/:id/overview",
                "behavior": "Validate profile.",
                "expectedOutcome": "Profile renders.",
                "customSourceReason": "Stage handoff target fixture.",
            },
        )
        self.cli([
            "workflow",
            "persist",
            "specify",
            "--alias",
            "profile",
            "--project",
            str(self.project),
            "--payload",
            str(write_payload(self.project, "specify-target-handoff", specify_payload)),
            "--json",
        ])
        clarify_payload = stage_payload(
            "clarify",
            payload={
                "alias": "profile",
                "answers": [
                    {
                        "questionId": "browser-target-environment",
                        "answerSummary": "Use https://app.example.test as the staging target.",
                        "confirmationSource": "direct-user",
                    }
                ],
            },
        )
        self.cli([
            "workflow",
            "persist",
            "clarify",
            "--alias",
            "profile",
            "--project",
            str(self.project),
            "--payload",
            str(write_payload(self.project, "clarify-target-handoff", clarify_payload)),
            "--json",
        ])
        plan_payload = stage_payload(
            "plan",
            payload={
                "alias": "profile",
                "runRequest": ".verifysignal/run-requests/profile.yaml",
                "reusableSkills": [".verifysignal/skills/profile.browser.md"],
                "runtimeInputs": [{"name": "baseUrl", "required": True}],
            },
        )

        code, out, err = self.cli([
            "workflow",
            "persist",
            "plan",
            "--alias",
            "profile",
            "--project",
            str(self.project),
            "--payload",
            str(write_payload(self.project, "plan-target-handoff", plan_payload)),
            "--json",
        ])

        self.assertEqual(code, 0, err)
        result = json.loads(out)
        self.assertEqual(result["status"], "persisted")
        plan = load_document(self.project / ".verifysignal/workflows/use-cases/profile/plan.yaml")
        self.assertEqual(plan["runtimeInputs"][0]["value"], "https://app.example.test")

    def test_workflow_show_and_status_alias_read_persisted_use_case_context(self) -> None:
        self.cli(["init", str(self.project), "--integration", "codex", "--json"])
        specify_payload = stage_payload(
            "specify",
            payload={
                "alias": "login",
                "surface": "/login",
                "behavior": "Validate login.",
                "expectedOutcome": "User reaches the dashboard.",
                "customSourceReason": "Manual test fixture.",
            },
        )
        code, out, err = self.cli([
            "workflow",
            "persist",
            "specify",
            "--alias",
            "login",
            "--project",
            str(self.project),
            "--payload",
            str(write_payload(self.project, "specify", specify_payload)),
            "--json",
        ])
        self.assertEqual(code, 0, err)

        code, out, err = self.cli(["workflow", "show", "--alias", "login", "--project", str(self.project), "--json"])
        self.assertEqual(code, 0, err)
        shown = json.loads(out)
        self.assertEqual(shown["schemaVersion"], "verifysignal-spec-workflow-show/v1")
        self.assertEqual(shown["useCase"]["alias"], "login")
        self.assertTrue(shown["documents"]["specify"]["exists"])
        self.assertIn("Validate login.", shown["documents"]["specify"]["content"])

        code, out, err = self.cli(["workflow", "status", "--alias", "login", "--project", str(self.project), "--json"])
        self.assertEqual(code, 0, err)
        status = json.loads(out)
        self.assertEqual(status["schemaVersion"], "verifysignal-spec-workflow-status/v1")
        self.assertEqual(status["useCaseAlias"], "login")

        code, out, err = self.cli(["workflow", "status", "login", "--project", str(self.project), "--json"])
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["useCaseAlias"], "login")

    def test_implement_blocks_when_planned_main_skill_is_missing(self) -> None:
        create_main_skill_coverage_workspace(self.project)
        payload = stage_payload(
            "implement",
            payload={
                "runRequest": ".verifysignal/run-requests/profile-view-unauth.yaml",
                "skills": [{"path": HELPER_SKILL_PATH, "kind": "skill", "browser": {"targets": {}, "steps": [], "assertions": []}}],
            },
        )

        code, out, err = self.cli(
            [
                "workflow",
                "persist",
                "implement",
                "--alias",
                "profile-view-unauth",
                "--project",
                str(self.project),
                "--payload",
                str(write_payload(self.project, "implement-missing-main", payload)),
                "--json",
            ]
        )

        self.assertEqual(code, 2, err)
        result = json.loads(out)
        self.assertEqual(result["status"], "blocked")
        self.assertIn(MAIN_SKILL_PATH, result["blockers"][0]["message"])

    def test_implement_reorders_helper_first_payload_to_planned_main_skill(self) -> None:
        create_main_skill_coverage_workspace(self.project)
        payload = stage_payload(
            "implement",
            payload={
                "runRequest": ".verifysignal/run-requests/profile-view-unauth.yaml",
                "skills": [
                    {"path": HELPER_SKILL_PATH, "kind": "skill", "browser": {"targets": {}, "steps": [], "assertions": []}},
                    {
                        "path": MAIN_SKILL_PATH,
                        "kind": "skill",
                        "intent": {"id": "skill.validate-profile-view-unauth-flow", "version": "3.0.0"},
                        "browser": {
                            "targets": {"profileName": {"css": "h2", "domainSemantics": "Profile name"}},
                            "steps": [],
                            "assertions": [
                                {"id": "name", "kind": "visible", "target": "profileName", "gateId": "overview-data-card"},
                                {"id": "project", "kind": "visible", "target": "profileName", "gateId": "projects-tab-content"},
                                {"id": "query", "kind": "visible", "target": "profileName", "gateId": "overview-profile-query"},
                            ],
                        },
                    },
                ],
            },
        )

        code, out, err = self.cli(
            [
                "workflow",
                "persist",
                "implement",
                "--alias",
                "profile-view-unauth",
                "--project",
                str(self.project),
                "--payload",
                str(write_payload(self.project, "implement-reorder-main", payload)),
                "--json",
            ]
        )

        self.assertEqual(code, 0, err)
        result = json.loads(out)
        self.assertEqual(result["status"], "persisted")
        record = json.loads((self.project / ".verifysignal/use-cases/profile-view-unauth.yaml").read_text(encoding="utf-8"))
        self.assertEqual(record["mainSkill"]["path"], MAIN_SKILL_PATH)
        self.assertEqual(record["skills"][0]["path"], MAIN_SKILL_PATH)
        self.assertEqual(record["mainSkill"]["version"], "3.0.0")

    def test_implement_preserves_run_request_content_parameters(self) -> None:
        create_main_skill_coverage_workspace(self.project)
        payload = stage_payload(
            "implement",
            payload={
                "runRequest": {
                    "path": ".verifysignal/run-requests/profile-view-unauth.yaml",
                    "kind": "run-request",
                    "content": {
                        "schemaVersion": "qa-run-request/v1",
                        "request": {"id": "request.profile-view-unauth", "name": "Profile View Unauth", "version": "3.0.0"},
                        "target": "browser",
                        "validationScope": "feature-level",
                        "skills": [{"id": "skill.validate-profile-view-unauth-flow", "version": "3.0.0"}],
                        "parameters": {"baseUrl": "https://app.example.test"},
                    },
                },
                "skills": [
                    {
                        "path": MAIN_SKILL_PATH,
                        "kind": "skill",
                        "intent": {"id": "skill.validate-profile-view-unauth-flow", "version": "3.0.0"},
                        "browser": {
                            "targets": {"profileName": {"css": "h2", "domainSemantics": "Profile name"}},
                            "steps": [],
                            "assertions": [
                                {"id": "name", "kind": "visible", "target": "profileName", "gateId": "overview-data-card"},
                                {"id": "project", "kind": "visible", "target": "profileName", "gateId": "projects-tab-content"},
                                {"id": "query", "kind": "visible", "target": "profileName", "gateId": "overview-profile-query"},
                            ],
                        },
                    }
                ],
            },
        )

        code, out, err = self.cli(
            [
                "workflow",
                "persist",
                "implement",
                "--alias",
                "profile-view-unauth",
                "--project",
                str(self.project),
                "--payload",
                str(write_payload(self.project, "implement-preserve-params", payload)),
                "--json",
            ]
        )

        self.assertEqual(code, 0, err)
        run_request = json.loads((self.project / ".verifysignal/run-requests/profile-view-unauth.yaml").read_text(encoding="utf-8"))
        self.assertEqual(run_request["parameters"]["baseUrl"], "https://app.example.test")
        self.assertEqual(run_request["skills"][0]["version"], "3.0.0")
