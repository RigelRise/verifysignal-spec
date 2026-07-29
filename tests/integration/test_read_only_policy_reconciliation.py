from __future__ import annotations

from tests.fixtures.workflows.main_skill_run_coverage import ALIAS, create_main_skill_coverage_workspace
from verifysignal_spec.commands import run as run_command
from verifysignal_spec.workspace.repository import load_use_case, save_use_case
from verifysignal_spec.workflows.repository import save_golden_path_state


def test_read_only_violation_prevents_strict_pass_persists_policy_and_blocks_blind_rerun(
    tmp_path,
    monkeypatch,
) -> None:
    from tests.helpers import FAKE_CORE

    monkeypatch.setenv("VERIFYSIGNAL_CORE_CMD", str(FAKE_CORE))
    monkeypatch.setenv("FAKE_VERIFYSIGNAL_MODE", "full-coverage-side-effect-violation")
    create_main_skill_coverage_workspace(tmp_path)
    record = load_use_case(tmp_path, ALIAS)
    record.sideEffects = _read_only_policy()
    save_use_case(tmp_path, record)
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

    second = run_command.run(tmp_path, ALIAS, interactive=False, core_cmd=str(FAKE_CORE))

    assert second["status"] == "blocked"
    assert second["coreBrowserStatus"] == "blocked"
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
    create_main_skill_coverage_workspace(tmp_path)
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
