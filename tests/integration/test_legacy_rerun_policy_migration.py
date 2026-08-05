from __future__ import annotations

from verifysignal_spec.commands import run as run_command
from verifysignal_spec.commands.validate import run as validate_run
from verifysignal_spec.workspace.repository import load_use_case


def test_legacy_rerun_risk_safe_with_new_inputs_runs_with_refreshed_input(tmp_path, monkeypatch) -> None:
    from tests.fixtures.workflows.write_rerun_identity import committed_last_run, write_use_case_record
    from tests.helpers import FAKE_CORE

    monkeypatch.setenv("VERIFYSIGNAL_CORE_CMD", str(FAKE_CORE))
    write_use_case_record(
        tmp_path,
        rerun_policy={"rerunRisk": "safe-with-new-inputs", "refreshRuntimeInputs": ["projectTitle"]},
        last_run=committed_last_run(),
        protected_ready=True,
    )

    result = run_command.run(tmp_path, "add-collaboration-project", interactive=False, core_cmd=str(FAKE_CORE))

    assert result["status"] == "passed"
    assert result["rerunDecision"]["specDecision"] == "allowed-with-new-inputs"
    record = load_use_case(tmp_path, "add-collaboration-project")
    assert record.lastRun
    assert record.lastRun["resolvedRuntimeInputs"][0]["refreshed"] is True


def test_validation_persists_unambiguous_legacy_policy_as_canonical(tmp_path, monkeypatch) -> None:
    from tests.fixtures.workflows.write_rerun_identity import committed_last_run, write_use_case_record
    from tests.helpers import FAKE_CORE

    monkeypatch.setenv("VERIFYSIGNAL_CORE_CMD", str(FAKE_CORE))
    write_use_case_record(
        tmp_path,
        rerun_policy={"rerunRisk": "safe-with-new-inputs", "refreshRuntimeInputs": ["projectTitle"]},
        last_run=committed_last_run(),
    )

    result = validate_run(tmp_path, "add-collaboration-project", runtime_readiness=False, core_cmd=str(FAKE_CORE))

    assert result["status"] == "passed"
    policy = load_use_case(tmp_path, "add-collaboration-project").rerunPolicy
    assert policy == {
        "afterNoCommit": "allowed",
        "afterCommit": "allowed-with-new-inputs",
        "afterUnknown": "requires-confirmation",
        "refreshRuntimeInputs": ["projectTitle"],
    }
