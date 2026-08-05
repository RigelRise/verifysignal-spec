from __future__ import annotations

from verifysignal_spec.commands import validate as validate_command
from verifysignal_spec.workspace import layout
from verifysignal_spec.workflows.prerequisites import check_prerequisites
from verifysignal_spec.workspace.repository import save_use_case

from tests.fixtures.workflows.side_effect_contract_alignment import (
    blocked_write_last_run,
    confirmable_write_last_run,
    create_write_policy_workspace,
    unsupported_dom_last_run,
)
from tests.fixtures.workflows.prerequisites import create_current_understanding_workspace


def test_validate_blocks_runtime_unsupported_confirmation_signal(tmp_path, monkeypatch) -> None:
    from tests.helpers import FAKE_CORE

    monkeypatch.setenv("VERIFYSIGNAL_CORE_CMD", str(FAKE_CORE))
    record = create_write_policy_workspace(
        tmp_path,
        side_effects={
            "class": "write",
            "mode": "enforce",
            "commitStepId": "confirm-publish-dialog",
            "allowed": [{"id": "allow-backend-graphql", "kind": "network", "methods": ["POST"], "urlContains": "be.example.test/graphql"}],
            "confirmationSignals": [{"id": "published-title-rendered", "type": "dom", "target": "publishedProjectTitle"}],
        },
        last_run=unsupported_dom_last_run(),
    )
    record.status = "ready"
    save_use_case(tmp_path, record)

    result = validate_command.run(tmp_path, "add-collaboration-project", runtime_readiness=True, core_cmd=str(FAKE_CORE))

    assert result["status"] == "blocked"
    if any(item["code"] == "workspace.structural-blocked" for item in result["blockers"]):
        findings = result["structuralValidation"]["findings"]
        assert any(item["code"] == "side-effect-confirmation-signal-unsupported" and item["path"] == "sideEffects.confirmationSignals[0].type" for item in findings)
    else:
        assert any(item["code"] == "runtime.unsupported-confirmation-signal" for item in result["blockers"])


def test_workflow_check_run_surfaces_same_blocked_rerun_decision_as_run_preflight(tmp_path) -> None:
    create_current_understanding_workspace(tmp_path)
    record = create_write_policy_workspace(tmp_path, last_run=blocked_write_last_run(), protected_ready=True)
    record.status = "ready"
    save_use_case(tmp_path, record)
    _write_minimal_stage_artifacts(tmp_path, "add-collaboration-project")

    result = check_prerequisites(tmp_path, "run", alias="add-collaboration-project")

    assert result["status"] == "blocked"
    assert result["canProceed"] is False
    assert result["rerunDecision"]["decision"] == "blocked"
    assert result["recommendedAction"] == "review-or-supersede-write-outcome"


def test_workflow_check_run_blocks_confirmable_write_rerun_with_guided_approval(tmp_path) -> None:
    create_current_understanding_workspace(tmp_path)
    record = create_write_policy_workspace(tmp_path, last_run=confirmable_write_last_run(), protected_ready=True)
    record.status = "ready"
    save_use_case(tmp_path, record)
    _write_minimal_stage_artifacts(tmp_path, "add-collaboration-project")

    result = check_prerequisites(tmp_path, "run", alias="add-collaboration-project")

    assert result["status"] == "blocked"
    assert result["canProceed"] is False
    assert result["requiresConfirmation"] is True
    assert result["recommendedAction"] == "approve-rerun"
    assert result["rerunDecision"]["decision"] == "requires-confirmation"
    assert result["rerunDecision"]["confirmationId"] == "confirm.add-collaboration-project.rerun-after-commit.committed-run"
    assert result["confirmation"]["id"] == result["rerunDecision"]["confirmationId"]
    assert result["blockers"][0]["code"] == "runtime.rerun-confirmation-required"
    assert "verifysignal workflow approve-rerun --alias add-collaboration-project" in result["nextCommand"]
    assert result["rerunDecision"]["confirmationId"] in result["nextCommand"]


def _write_minimal_stage_artifacts(project, alias: str) -> None:
    root = layout.workflow_use_case_dir(project, alias)
    root.mkdir(parents=True, exist_ok=True)
    for name in ["spec", "plan", "tasks"]:
        (root / f"{name}.md").write_text(f"# {name}\n", encoding="utf-8")
        (root / f"{name}.yaml").write_text("{}\n", encoding="utf-8")
