from __future__ import annotations

import json

from verifysignal_spec.workspace import layout
from verifysignal_spec.workspace.repository import save_use_case

from tests.fixtures.workflows.prerequisites import create_current_understanding_workspace
from tests.fixtures.workflows.side_effect_contract_alignment import confirmable_write_last_run, create_write_policy_workspace
from tests.helpers import CliTestCase


class WorkflowApproveRerunContractTest(CliTestCase):
    def test_workflow_approve_rerun_cli_persists_review(self) -> None:
        create_current_understanding_workspace(self.project)
        record = create_write_policy_workspace(self.project, last_run=confirmable_write_last_run(), protected_ready=True)
        record.status = "ready"
        save_use_case(self.project, record)
        _write_minimal_stage_artifacts(self.project, "add-collaboration-project")
        check_code, check_out, check_err = self.cli(["workflow", "check", "run", "--alias", "add-collaboration-project", "--project", str(self.project), "--json"])
        assert check_code == 2, check_err
        confirmation_id = json.loads(check_out)["rerunDecision"]["confirmationId"]

        code, out, err = self.cli(
            [
                "workflow",
                "approve-rerun",
                "--alias",
                "add-collaboration-project",
                "--confirm-risk",
                confirmation_id,
                "--project",
                str(self.project),
                "--json",
            ]
        )

        assert code == 0, err
        payload = json.loads(out)
        assert payload["status"] == "persisted"
        assert payload["review"]["sourceRunId"] == "committed-run"
        assert payload["review"]["ownerDecision"] == "approved-rerun-after-write"

    def test_workflow_approve_rerun_with_long_runid_persists(self) -> None:
        # Regression (dogfood Bug 1): a realistic ISO-timestamped runId makes the generated
        # reviewId exceed 80 chars; the filename validator rejected it with a misleading
        # "Alias must be lowercase..." error even though the id is charset-clean.
        create_current_understanding_workspace(self.project)
        long_run_id = "add-collaboration-project-20260622T185251Z"
        record = create_write_policy_workspace(
            self.project,
            last_run=confirmable_write_last_run(run_id=long_run_id),
            protected_ready=True,
        )
        record.status = "ready"
        save_use_case(self.project, record)
        _write_minimal_stage_artifacts(self.project, "add-collaboration-project")
        check_code, check_out, check_err = self.cli(["workflow", "check", "run", "--alias", "add-collaboration-project", "--project", str(self.project), "--json"])
        assert check_code == 2, check_err
        confirmation_id = json.loads(check_out)["rerunDecision"]["confirmationId"]

        code, out, err = self.cli(
            [
                "workflow",
                "approve-rerun",
                "--alias",
                "add-collaboration-project",
                "--confirm-risk",
                confirmation_id,
                "--project",
                str(self.project),
                "--json",
            ]
        )

        assert code == 0, err
        payload = json.loads(out)
        assert payload["status"] == "persisted"
        assert payload["review"]["sourceRunId"] == long_run_id


def _write_minimal_stage_artifacts(project, alias: str) -> None:
    root = layout.workflow_use_case_dir(project, alias)
    root.mkdir(parents=True, exist_ok=True)
    for name in ["spec", "plan", "tasks"]:
        (root / f"{name}.md").write_text(f"# {name}\n", encoding="utf-8")
        (root / f"{name}.yaml").write_text("{}\n", encoding="utf-8")
