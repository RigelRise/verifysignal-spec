from __future__ import annotations

from verifysignal_spec.workspace.repository import init_workspace
from verifysignal_spec.workflows.engine import create_workflow_run
from verifysignal_spec.workflows.stage_persistence import persist_stage
from verifysignal_spec.workflows.transitions import transition_workflow

from tests.fixtures.workflows.real_run_guardrails import (
    coherent_profile_skill,
    create_real_run_guardrail_workspace,
    navigation_only_skill,
    run_request_payload,
)
from tests.helpers import FAKE_CORE


def _prepare_implementation_stage(project) -> None:
    create_real_run_guardrail_workspace(project)
    init_workspace(project, core_cmd=str(FAKE_CORE))
    create_workflow_run(
        project,
        "Validate a public profile page.",
        alias="profile-view-unauth",
        integration="codex",
    )
    for stage in ("specify", "clarify", "plan", "tasks"):
        transition_workflow(
            project,
            "profile-view-unauth",
            stage=stage,
            outcome="completed",
            handoff_summary="Canonical page-view fixture setup.",
        )


def test_navigation_only_artifact_blocks_before_execution(tmp_path) -> None:
    _prepare_implementation_stage(tmp_path)

    result = persist_stage(
        tmp_path,
        "implement",
        alias="profile-view-unauth",
        payload={"runRequest": run_request_payload(), "skills": [navigation_only_skill()]},
    )

    assert result["status"] == "blocked"
    assert any("specific UI evidence" in blocker["message"] for blocker in result["blockers"])


def test_specific_ui_and_network_evidence_persists(tmp_path) -> None:
    _prepare_implementation_stage(tmp_path)

    result = persist_stage(
        tmp_path,
        "implement",
        alias="profile-view-unauth",
        payload={"runRequest": run_request_payload(), "skills": [coherent_profile_skill()]},
    )

    assert result["status"] == "persisted"
