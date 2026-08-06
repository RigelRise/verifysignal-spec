from __future__ import annotations

from tests.fixtures.workflows.entitlement_preflight_recovery import save_protected_ready_snapshot
from tests.fixtures.workflows.main_skill_run_coverage import ALIAS, create_main_skill_coverage_workspace
from tests.fixtures.workflows.prerequisites import create_current_understanding_workspace
from verifysignal_spec.commands import run as run_command
from verifysignal_spec.workspace import layout
from verifysignal_spec.workspace.repository import load_use_case, save_use_case
from verifysignal_spec.workflows.prerequisites import check_prerequisites
from verifysignal_spec.workflows.repository import save_golden_path_state
from verifysignal_spec.workflows.transitions import transition_workflow


def test_read_only_violation_prevents_strict_pass_persists_policy_and_blocks_blind_rerun(
    tmp_path,
    monkeypatch,
) -> None:
    from tests.helpers import FAKE_CORE

    monkeypatch.setenv("VERIFYSIGNAL_CORE_CMD", str(FAKE_CORE))
    monkeypatch.setenv("FAKE_VERIFYSIGNAL_MODE", "full-coverage-side-effect-violation")
    create_current_understanding_workspace(tmp_path)
    create_main_skill_coverage_workspace(tmp_path, protected_ready=True)
    _write_minimal_stage_artifacts(tmp_path, ALIAS)
    record = load_use_case(tmp_path, ALIAS)
    record.sideEffects = _read_only_policy()
    save_use_case(tmp_path, record)
    save_protected_ready_snapshot(tmp_path, ALIAS)
    _accept_golden_path(tmp_path)

    first = run_command.run(tmp_path, ALIAS, interactive=False, core_cmd=str(FAKE_CORE))

    assert first["coreBrowserStatus"] == "passed"
    assert first["specCoverageStatus"] == "complete"
    assert first["firstRunStatus"] == "failed"
    assert first["strictPass"] is False
    persisted = load_use_case(tmp_path, ALIAS)
    assert persisted.lastRun
    assert persisted.lastRun["sideEffectPolicy"] == _read_only_policy()
    assert persisted.lastRun["sideEffects"]["violations"][0]["code"] == "side-effect-class-none-violation"
    persisted.status = "ready"
    save_use_case(tmp_path, persisted)
    transition_workflow(
        tmp_path,
        ALIAS,
        stage="repair",
        outcome="completed",
        handoff_summary="Policy-reconciliation fixture repair was reviewed.",
    )
    transition_workflow(
        tmp_path,
        ALIAS,
        stage="validate",
        outcome="completed",
        handoff_summary="Policy-reconciliation fixture is protected-ready.",
    )

    workflow = check_prerequisites(tmp_path, "run", alias=ALIAS)

    second = run_command.run(tmp_path, ALIAS, interactive=False, core_cmd=str(FAKE_CORE))

    assert workflow["recommendedAction"] == "review-or-supersede-write-outcome"
    assert workflow["nextCommand"] == (
        f"verifysignal workflow supersede-write-outcome --alias {ALIAS} --json"
    )
    assert second["status"] == "blocked"
    assert second["coreBrowserStatus"] == "blocked"
    assert second["recommendedAction"] == "review-or-supersede-write-outcome"
    assert second["nextAction"] == (
        f"verifysignal workflow supersede-write-outcome --alias {ALIAS} --json"
    )
    assert any(
        blocker["code"] == "runtime.side-effect-observation-review-required"
        for blocker in second["blockers"]
    )


def test_explicit_policy_change_allows_one_new_run_and_requires_clean_evidence_for_strict_pass(
    tmp_path,
    monkeypatch,
) -> None:
    from tests.helpers import FAKE_CORE

    monkeypatch.setenv("VERIFYSIGNAL_CORE_CMD", str(FAKE_CORE))
    monkeypatch.setenv("FAKE_VERIFYSIGNAL_MODE", "full-coverage-clean-side-effects")
    create_current_understanding_workspace(tmp_path)
    create_main_skill_coverage_workspace(tmp_path, protected_ready=True)
    _write_minimal_stage_artifacts(tmp_path, ALIAS)
    previous_policy = _read_only_policy()
    current_policy = {
        **previous_policy,
        "allowed": [
            {
                "id": "declared-read-infrastructure",
                "kind": "network",
                "methods": ["POST"],
                "urlContains": "/api/read-infrastructure",
                "timing": "any",
            }
        ],
    }
    record = load_use_case(tmp_path, ALIAS)
    record.sideEffects = current_policy
    record.lastRun = {
        "runId": "previous-violation",
        "sideEffectPolicy": previous_policy,
        "sideEffects": {
            "violations": [
                {
                    "code": "side-effect-class-none-violation",
                    "severity": "warning",
                    "message": "Unexpected POST",
                }
            ]
        },
        "postCommitInterpretation": {
            "sideEffectStatus": "violated",
            "rerunRisk": "blocked",
        },
    }
    save_use_case(tmp_path, record)
    save_protected_ready_snapshot(tmp_path, ALIAS)
    _accept_golden_path(tmp_path)

    result = run_command.run(tmp_path, ALIAS, interactive=False, core_cmd=str(FAKE_CORE))

    assert result["coreBrowserStatus"] == "passed"
    assert result["firstRunStatus"] == "passed"
    assert result["strictPass"] is True
    persisted = load_use_case(tmp_path, ALIAS)
    assert persisted.lastRun
    assert persisted.lastRun["sideEffectPolicy"] == current_policy
    assert persisted.lastRun["sideEffects"]["violations"] == []


def _read_only_policy() -> dict:
    return {
        "class": "none",
        "mode": "observe",
        "allowed": [],
        "forbidden": [],
        "confirmationSignals": [],
    }


def _accept_golden_path(project) -> None:
    save_golden_path_state(
        project,
        {
            "selectedCandidate": ALIAS,
            "recommendationStatus": "accepted",
            "repairFeedback": [],
        },
    )


def _write_minimal_stage_artifacts(project, alias: str) -> None:
    root = layout.workflow_use_case_dir(project, alias)
    root.mkdir(parents=True, exist_ok=True)
    for stage in ("spec", "plan", "tasks"):
        (root / f"{stage}.md").write_text(f"# {stage}\n", encoding="utf-8")
        if stage != "spec":
            (root / f"{stage}.yaml").write_text("{}\n", encoding="utf-8")
