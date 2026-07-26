from __future__ import annotations

from helpers import CliTestCase

from verifysignal_spec.workflows.prerequisites import check_prerequisites
from verifysignal_spec.workflows.stage_persistence import persist_stage
from verifysignal_spec.workspace.repository import load_use_case

from tests.fixtures.workflows.prerequisites import (
    create_current_understanding_workspace,
    create_missing_understanding_workspace,
    create_stale_understanding_workspace,
    sample_candidate,
)


class WorkflowSpecifyPrerequisitesTests(CliTestCase):
    def test_missing_understanding_guidance_is_installed_for_codex(self) -> None:
        code, _, err = self.cli(["init", str(self.project), "--integration", "codex", "--json"])
        self.assertEqual(code, 0, err)
        content = (self.project / ".agents" / "skills" / "verifysignal-specify" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("verifysignal workflow check specify --json", content)
        self.assertIn("product understanding is required", content)
        self.assertIn("candidate validation use cases", content)

    def test_specify_missing_understanding_routes_to_understand(self) -> None:
        create_missing_understanding_workspace(self.project)
        result = check_prerequisites(self.project, "specify")
        assert result["status"] == "missing"
        assert result["nextCommand"] == "/verifysignal-understand"

    def test_specify_current_understanding_surfaces_candidates(self) -> None:
        create_current_understanding_workspace(self.project, candidates=[sample_candidate("profile")])
        result = check_prerequisites(self.project, "specify")
        assert result["status"] == "ready"
        assert result["recommendedCandidate"]["candidateAlias"] == "profile"
        assert result["candidateSelectionSource"] == "workflow.recommend-first-run"
        assert result["firstRunRecommendationCommand"] == "verifysignal workflow recommend-first-run --json"
        assert result["candidateUseCases"][0]["candidateAlias"] == "profile"

    def test_specify_stale_refresh_accept_and_decline_paths(self) -> None:
        create_stale_understanding_workspace(self.project)
        stale = check_prerequisites(self.project, "specify")
        assert stale["status"] == "stale"
        assert stale["requiresConfirmation"] is True

        accepted = check_prerequisites(self.project, "specify", refresh_decision="accepted")
        assert accepted["canProceed"] is False
        assert accepted["nextCommand"] == "/verifysignal-understand"
        assert accepted["recordedDecision"]["decision"] == "accepted"

        declined = check_prerequisites(self.project, "specify", refresh_decision="declined")
        assert declined["canProceed"] is True
        assert declined["requiresConfirmation"] is False
        assert declined["recordedDecision"]["decision"] == "declined"

    def test_browser_spec_without_target_records_blocking_target_question(self) -> None:
        create_current_understanding_workspace(self.project, candidates=[sample_candidate("profile")])

        persisted = persist_stage(
            self.project,
            "specify",
            alias="profile",
            payload={
                "alias": "profile",
                "surface": "/profile/:id/overview",
                "behavior": "Validate public profile rendering.",
                "expectedOutcome": "Profile renders.",
                "customSourceReason": "Browser target prerequisite integration fixture.",
            },
        )

        assert persisted["status"] == "persisted"
        record = load_use_case(self.project, "profile")
        assert any(question.id == "browser-target-environment" for question in record.authoringQuestions)
        plan_check = check_prerequisites(self.project, "plan", alias="profile")
        assert plan_check["nextCommand"] == "/verifysignal-clarify profile"
