from __future__ import annotations

import contextlib
import io
import json

from verifysignal_spec.cli import main
from verifysignal_spec.workflows.stage_persistence import persist_stage
from verifysignal_spec.workspace.repository import init_workspace
from verifysignal_spec.workflows.transitions import transition_workflow

from tests.fixtures.workflows.entitlement_preflight_recovery import save_protected_ready_snapshot, write_active_run_documents
from tests.fixtures.workflows.main_skill_run_coverage import create_main_skill_coverage_workspace
from tests.fixtures.workflows.real_run_guardrails import coherent_profile_skill, create_real_run_guardrail_workspace, run_request_payload


def test_cli_runs_custom_visual_profile_for_one_use_case(tmp_path, monkeypatch) -> None:
    from tests.helpers import FAKE_CORE

    monkeypatch.setenv("VERIFYSIGNAL_CORE_CMD", str(FAKE_CORE))
    monkeypatch.setenv("FAKE_VERIFYSIGNAL_MODE", "full-coverage")
    init_workspace(tmp_path, core_cmd=str(FAKE_CORE))
    create_main_skill_coverage_workspace(tmp_path, core_cmd=str(FAKE_CORE))
    persist_stage(
        tmp_path,
        "implement",
        alias="profile-view-unauth",
        payload={
            "runRequest": run_request_payload(),
            "skills": [coherent_profile_skill()],
            "profiles": [
                {"name": "normal", "headed": False, "slowMoMs": 0},
                {"name": "visual-15s", "headed": True, "slowMoMs": 15000},
            ],
        },
    )
    write_active_run_documents(tmp_path, "profile-view-unauth")
    save_protected_ready_snapshot(tmp_path, "profile-view-unauth")
    transition_workflow(
        tmp_path,
        "profile-view-unauth",
        stage="validate",
        outcome="completed",
        handoff_summary="Protected-ready CLI profile fixture setup.",
    )

    code = main(["run", "profile-view-unauth", "--project", str(tmp_path), "--profile", "visual-15s", "--non-interactive", "--json"])

    assert code == 0


def test_cli_blocks_unknown_custom_profile(tmp_path) -> None:
    create_main_skill_coverage_workspace(tmp_path, protected_ready=True)

    code = main(["run", "profile-view-unauth", "--project", str(tmp_path), "--profile", "visual", "--non-interactive"])

    assert code != 0


def test_cli_debug_profile_summary_uses_observable_default(tmp_path, monkeypatch) -> None:
    from tests.helpers import FAKE_CORE

    monkeypatch.setenv("VERIFYSIGNAL_CORE_CMD", str(FAKE_CORE))
    monkeypatch.setenv("FAKE_VERIFYSIGNAL_MODE", "full-coverage")
    create_main_skill_coverage_workspace(
        tmp_path,
        core_cmd=str(FAKE_CORE),
        protected_ready=True,
    )
    stdout = io.StringIO()

    with contextlib.redirect_stdout(stdout):
        code = main(["run", "profile-view-unauth", "--project", str(tmp_path), "--profile", "debug", "--non-interactive", "--json"])

    assert code == 0
    payload = json.loads(stdout.getvalue())
    assert payload["profileSettings"] == {"profile": "debug", "headed": True, "slowMoMs": 900, "source": "default"}


def test_cli_slow_mo_override_is_reported_and_forwarded(tmp_path, monkeypatch) -> None:
    from tests.helpers import FAKE_CORE

    monkeypatch.setenv("VERIFYSIGNAL_CORE_CMD", str(FAKE_CORE))
    monkeypatch.setenv("FAKE_VERIFYSIGNAL_MODE", "full-coverage")
    create_main_skill_coverage_workspace(
        tmp_path,
        core_cmd=str(FAKE_CORE),
        protected_ready=True,
    )
    stdout = io.StringIO()

    with contextlib.redirect_stdout(stdout):
        code = main(["run", "profile-view-unauth", "--project", str(tmp_path), "--profile", "debug", "--slow-mo", "1200", "--non-interactive", "--json"])

    assert code == 0
    payload = json.loads(stdout.getvalue())
    assert payload["profileSettings"] == {"profile": "debug", "headed": True, "slowMoMs": 1200, "source": "cli-override", "overrides": ["slowMoMs"]}
    assert payload["core"]["data"]["slowMoMs"] == 1200
