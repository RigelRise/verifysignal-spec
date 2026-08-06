from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from tests.fixtures.workflows.entitlement_preflight_recovery import (
    save_protected_ready_snapshot,
    write_active_run_documents,
)
from tests.fixtures.workflows.main_skill_run_coverage import (
    ALIAS,
    create_main_skill_coverage_workspace,
)
from verifysignal_spec.commands import run as run_command
from verifysignal_spec.commands import workflow as workflow_command
from verifysignal_spec.runtime.models import (
    ManagedRuntimeReadinessResult,
    RuntimeSetupBlocker,
)
from verifysignal_spec.workspace import layout
from verifysignal_spec.workspace.models import AuthoringQuestion
from verifysignal_spec.workspace.repository import (
    load_document,
    load_use_case,
    now_iso,
    save_document,
    save_use_case,
)
from verifysignal_spec.workflows.engine import create_workflow_run
from verifysignal_spec.workflows.models import WORKFLOW_STAGES, WorkflowRun
from verifysignal_spec.workflows.repository import (
    link_workflow_reference,
    load_active_workflow_run,
    save_workflow_run,
    save_workflow_state,
    state_document,
)


@pytest.mark.parametrize(
    "corruption",
    [
        "invalid-status",
        "invalid-current-stage",
        "empty-stage-states",
        "duplicate-stage-state",
    ],
)
def test_matching_workflow_authority_rejects_invalid_run_invariants(
    tmp_path: Path,
    corruption: str,
) -> None:
    run = _create_runnable_workflow_authority(tmp_path)
    document = _run_document(tmp_path, run.runId)
    _corrupt_workflow_run(document, corruption)
    save_document(layout.workflow_run_path(tmp_path, run.runId), document)

    with pytest.raises(ValueError):
        load_active_workflow_run(tmp_path, ALIAS)


def test_newer_invalid_matching_authority_outranks_stale_confirmed_reference_and_fails_closed(
    tmp_path: Path,
) -> None:
    older = _create_runnable_workflow_authority(tmp_path)
    older_document = _run_document(tmp_path, older.runId)
    older_document["updatedAt"] = "2026-08-05T00:00:00.000000001Z"
    save_document(
        layout.workflow_run_path(tmp_path, older.runId),
        older_document,
    )

    newer_document = deepcopy(older_document)
    newer_document.update(
        {
            "runId": "wf-newer-invalid-profile-view-unauth",
            "status": "teleported",
            "updatedAt": "2026-08-05T00:00:00.000000002Z",
        }
    )
    newer_document.pop("targetEnvironmentConfirmation", None)
    save_document(
        layout.workflow_run_path(tmp_path, newer_document["runId"]),
        newer_document,
    )

    record = load_use_case(tmp_path, ALIAS)
    assert isinstance(record.workflow, dict)
    record.workflow["lastWorkflowRunId"] = older.runId
    save_use_case(tmp_path, record)
    save_protected_ready_snapshot(tmp_path, ALIAS)

    checked = workflow_command.check(tmp_path, "run", alias=ALIAS)

    assert checked["status"] == "blocked"
    assert checked["canProceed"] is False
    assert checked["blockers"][0]["code"] == "workflow.authority-invalid"
    assert checked["blockers"][0]["currentStage"] == "unknown"


def test_corrupt_different_alias_candidate_does_not_block_valid_authority(
    tmp_path: Path,
) -> None:
    valid = _create_runnable_workflow_authority(tmp_path)
    corrupt_document = _run_document(tmp_path, valid.runId)
    corrupt_document.update(
        {
            "runId": "wf-corrupt-different-alias",
            "useCaseAlias": "different-alias",
            "status": "teleported",
            "currentStage": "launch",
            "stageStates": [],
            "updatedAt": "2099-08-05T00:00:00.000000009Z",
        }
    )
    save_document(
        layout.workflow_run_path(tmp_path, corrupt_document["runId"]),
        corrupt_document,
    )

    authoritative = load_active_workflow_run(tmp_path, ALIAS)

    assert authoritative is not None
    assert authoritative.runId == valid.runId


def test_newest_authority_ordering_preserves_nanosecond_precision(
    tmp_path: Path,
) -> None:
    older = _create_runnable_workflow_authority(tmp_path)
    older_document = _run_document(tmp_path, older.runId)
    older_document["updatedAt"] = "2026-08-05T00:00:00.000000001Z"
    save_document(
        layout.workflow_run_path(tmp_path, older.runId),
        older_document,
    )

    newer_document = deepcopy(older_document)
    newer_document.update(
        {
            "runId": "wf-newer-by-one-nanosecond",
            "updatedAt": "2026-08-05T00:00:00.000000002Z",
        }
    )
    save_document(
        layout.workflow_run_path(tmp_path, newer_document["runId"]),
        newer_document,
    )

    authoritative = load_active_workflow_run(tmp_path, ALIAS)

    assert authoritative is not None
    assert authoritative.runId == newer_document["runId"]


def test_invalid_authority_blocks_protected_check_and_direct_run_before_core(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = _create_runnable_workflow_authority(tmp_path)
    document = _run_document(tmp_path, run.runId)
    _corrupt_workflow_run(document, "duplicate-stage-state")
    save_document(layout.workflow_run_path(tmp_path, run.runId), document)
    calls = {"runtimeResolution": 0, "coreAdapter": 0}

    def unexpected_runtime(*_args: object, **_kwargs: object) -> object:
        calls["runtimeResolution"] += 1
        return ManagedRuntimeReadinessResult.blocked(
            RuntimeSetupBlocker(
                code="test.core-resolution-reached",
                message="Invalid authority reached Core runtime resolution.",
            )
        )

    def unexpected_core_adapter(*_args: object, **_kwargs: object) -> object:
        calls["coreAdapter"] += 1
        raise AssertionError("Invalid authority must not invoke Core.")

    monkeypatch.setattr(run_command, "ensure_core_runtime", unexpected_runtime)
    monkeypatch.setattr(run_command, "CoreAdapter", unexpected_core_adapter)

    checked = workflow_command.check(tmp_path, "run", alias=ALIAS)
    executed = run_command.run(tmp_path, ALIAS, interactive=False)

    assert calls == {"runtimeResolution": 0, "coreAdapter": 0}
    assert checked["status"] == "blocked"
    assert executed["status"] == "blocked"
    assert checked["blockers"][0] == executed["blockers"][0]
    blocker = executed["blockers"][0]
    assert blocker["code"] == "workflow.authority-invalid"
    assert blocker["currentStage"] == "unknown"
    assert blocker["requestedStage"] == "run"


def _create_runnable_workflow_authority(project: Path) -> WorkflowRun:
    create_main_skill_coverage_workspace(project)
    run = create_workflow_run(
        project,
        "Validate a public profile page.",
        alias=ALIAS,
        integration="codex",
    )
    write_active_run_documents(project, ALIAS)
    current_index = WORKFLOW_STAGES.index("run")
    completed_at = now_iso()
    for index, stage in enumerate(run.stageStates):
        stage.status = "completed" if index < current_index else "pending"
        stage.completedAt = completed_at if index < current_index else None
        stage.blockers = []
    run.currentStage = "run"
    run.status = "paused"
    run.completedAt = None
    run.nextCommand = f"/verifysignal-run {ALIAS}"
    run.targetEnvironmentConfirmation = {
        "questionId": "browser-target-environment",
        "url": "https://app.example.test",
        "source": "direct-user",
        "confirmedAt": "2026-08-05T00:00:00Z",
    }
    save_workflow_run(project, run)
    link_workflow_reference(project, ALIAS, run, run.status)
    save_workflow_state(
        project,
        ALIAS,
        state_document(project, ALIAS, run),
    )

    record = load_use_case(project, ALIAS)
    record.authoringQuestions = [
        AuthoringQuestion(
            id="browser-target-environment",
            prompt="Which target should this workflow validate?",
            status="answered",
            answerSummary="https://app.example.test",
            affects="runtimeInputs.baseUrl",
            requiresConfirmation=True,
            confirmationSource="direct-user",
        )
    ]
    save_use_case(project, record)
    save_protected_ready_snapshot(project, ALIAS)
    return run


def _run_document(project: Path, run_id: str) -> dict[str, Any]:
    document = load_document(layout.workflow_run_path(project, run_id))
    assert isinstance(document, dict)
    return document


def _corrupt_workflow_run(document: dict[str, Any], corruption: str) -> None:
    if corruption == "invalid-status":
        document["status"] = "teleported"
        return
    if corruption == "invalid-current-stage":
        document["currentStage"] = "launch"
        return
    if corruption == "empty-stage-states":
        document["stageStates"] = []
        return
    if corruption == "duplicate-stage-state":
        stage_states = document["stageStates"]
        assert isinstance(stage_states, list) and stage_states
        stage_states.append(deepcopy(stage_states[0]))
        return
    raise AssertionError(f"Unsupported corruption fixture: {corruption}")
