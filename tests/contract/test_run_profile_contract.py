from __future__ import annotations

from verifysignal_spec.commands import run as run_command
from verifysignal_spec.workflows.stage_persistence import persist_stage
from verifysignal_spec.workspace.repository import init_workspace, load_use_case
from verifysignal_spec.workflows.transitions import transition_workflow

from tests.fixtures.workflows.entitlement_preflight_recovery import save_protected_ready_snapshot
from tests.fixtures.workflows.main_skill_run_coverage import create_main_skill_coverage_workspace
from tests.fixtures.workflows.real_run_guardrails import coherent_profile_skill, create_real_run_guardrail_workspace, run_request_payload


def test_custom_profile_is_persisted_and_passed_to_core(tmp_path, monkeypatch) -> None:
    from tests.helpers import FAKE_CORE

    monkeypatch.setenv("VERIFYSIGNAL_CORE_CMD", str(FAKE_CORE))
    monkeypatch.setenv("FAKE_VERIFYSIGNAL_MODE", "full-coverage")
    init_workspace(tmp_path, core_cmd=str(FAKE_CORE))
    create_main_skill_coverage_workspace(tmp_path)
    result = persist_stage(
        tmp_path,
        "implement",
        alias="profile-view-unauth",
        payload={
            "runRequest": run_request_payload(),
            "skills": [coherent_profile_skill()],
            "profiles": [
                {"name": "normal", "headed": False, "slowMoMs": 0},
                {"name": "debug", "headed": True, "slowMoMs": 700},
                {"name": "visual-15s", "headed": True, "slowMoMs": 15000},
            ],
        },
    )
    assert result["status"] == "persisted"
    save_protected_ready_snapshot(tmp_path, "profile-view-unauth")
    transition_workflow(
        tmp_path,
        "profile-view-unauth",
        stage="validate",
        outcome="completed",
        handoff_summary="Protected-ready profile fixture setup.",
    )

    run = run_command.run(tmp_path, "profile-view-unauth", profile_name="visual-15s", core_cmd=str(FAKE_CORE), interactive=False)

    assert run["profileSettings"] == {"profile": "visual-15s", "headed": True, "slowMoMs": 15000, "source": "workspace-profile"}
    assert run["core"]["data"]["headed"] is True
    assert run["core"]["data"]["slowMoMs"] == 15000
    record = load_use_case(tmp_path, "profile-view-unauth")
    assert record.lastRun
    assert record.lastRun["profile"] == "visual-15s"


def test_unknown_profile_lists_available_profiles(tmp_path) -> None:
    create_main_skill_coverage_workspace(tmp_path, protected_ready=True)

    try:
        run_command.run(tmp_path, "profile-view-unauth", profile_name="visual", interactive=False)
    except ValueError as exc:
        message = str(exc)
    else:  # pragma: no cover
        raise AssertionError("unknown profile should fail")

    assert "Unknown profile for profile-view-unauth: visual" in message
    assert "normal" in message


def test_debug_profile_defaults_to_900ms_slow_motion(tmp_path, monkeypatch) -> None:
    from tests.helpers import FAKE_CORE

    monkeypatch.setenv("VERIFYSIGNAL_CORE_CMD", str(FAKE_CORE))
    monkeypatch.setenv("FAKE_VERIFYSIGNAL_MODE", "full-coverage")
    create_main_skill_coverage_workspace(
        tmp_path,
        core_cmd=str(FAKE_CORE),
        protected_ready=True,
    )

    run = run_command.run(tmp_path, "profile-view-unauth", profile_name="debug", core_cmd=str(FAKE_CORE), interactive=False)

    assert run["profileSettings"] == {"profile": "debug", "headed": True, "slowMoMs": 900, "source": "default"}
    assert run["core"]["data"]["slowMoMs"] == 900


def test_normal_profile_defaults_to_zero_slow_motion(tmp_path, monkeypatch) -> None:
    from tests.helpers import FAKE_CORE

    monkeypatch.setenv("VERIFYSIGNAL_CORE_CMD", str(FAKE_CORE))
    monkeypatch.setenv("FAKE_VERIFYSIGNAL_MODE", "full-coverage")
    create_main_skill_coverage_workspace(
        tmp_path,
        core_cmd=str(FAKE_CORE),
        protected_ready=True,
    )

    run = run_command.run(tmp_path, "profile-view-unauth", profile_name="normal", core_cmd=str(FAKE_CORE), interactive=False)

    assert run["profileSettings"] == {"profile": "normal", "headed": False, "slowMoMs": 0, "source": "default"}
    assert run["core"]["data"]["slowMoMs"] == 0


def test_explicit_slow_motion_override_wins(tmp_path, monkeypatch) -> None:
    from tests.helpers import FAKE_CORE

    monkeypatch.setenv("VERIFYSIGNAL_CORE_CMD", str(FAKE_CORE))
    monkeypatch.setenv("FAKE_VERIFYSIGNAL_MODE", "full-coverage")
    create_main_skill_coverage_workspace(
        tmp_path,
        core_cmd=str(FAKE_CORE),
        protected_ready=True,
    )

    run = run_command.run(tmp_path, "profile-view-unauth", profile_name="debug", slow_mo_override=1200, core_cmd=str(FAKE_CORE), interactive=False)

    assert run["profileSettings"] == {"profile": "debug", "headed": True, "slowMoMs": 1200, "source": "cli-override", "overrides": ["slowMoMs"]}
    assert run["core"]["data"]["slowMoMs"] == 1200
