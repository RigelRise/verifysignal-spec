from __future__ import annotations

from verifysignal_spec.commands import run as run_command
from verifysignal_spec.workspace import layout
from verifysignal_spec.workspace.models import ArtifactReference, RuntimeInputRequirement, UseCaseRecord
from verifysignal_spec.workspace.repository import init_workspace, load_supersede_reviews, load_use_case, save_use_case
from tests.fixtures.workflows.prerequisites import create_current_understanding_workspace
from tests.integration.test_workflow_run import _current_write_capabilities, _manual_cleanup_lifecycle, _write_minimal_artifacts
from verifysignal_spec.workflows.prerequisites import check_prerequisites
from tests.fixtures.workflows.entitlement_preflight_recovery import save_protected_ready_snapshot


def test_rerun_after_post_commit_write_blocks_when_policy_blocks(tmp_path, monkeypatch) -> None:
    from tests.helpers import FAKE_CORE

    monkeypatch.setenv("VERIFYSIGNAL_CORE_CMD", str(FAKE_CORE))
    init_workspace(tmp_path, core_cmd=str(FAKE_CORE))
    create_current_understanding_workspace(tmp_path)
    _write_minimal_artifacts(tmp_path, "create-resource", parameters={"baseUrl": "https://example.test"})
    _save_runnable_record(tmp_path, _write_record(after_commit="blocked"))

    result = run_command.run(tmp_path, "create-resource", interactive=False, core_cmd=str(FAKE_CORE))

    assert result["status"] == "blocked"
    assert result["rerunDecision"]["decision"] == "blocked"


def test_rerun_after_post_commit_write_refreshes_declared_generated_inputs(tmp_path, monkeypatch) -> None:
    from tests.helpers import FAKE_CORE

    monkeypatch.setenv("VERIFYSIGNAL_CORE_CMD", str(FAKE_CORE))
    init_workspace(tmp_path, core_cmd=str(FAKE_CORE))
    _write_minimal_artifacts(tmp_path, "create-resource", parameters={"baseUrl": "https://example.test"})
    _save_runnable_record(tmp_path, _write_record(after_commit="allowed-with-new-inputs", refresh_inputs=["resourceName"], core_risk="safe-with-new-inputs"))

    result = run_command.run(tmp_path, "create-resource", interactive=False, core_cmd=str(FAKE_CORE))

    assert result["status"] == "passed"
    assert result["rerunDecision"]["decision"] == "allowed-with-new-inputs"
    last_run = load_use_case(tmp_path, "create-resource").lastRun
    assert last_run
    assert last_run["resolvedRuntimeInputs"][0]["refreshed"] is True


def test_confirm_risk_approves_confirmable_write_rerun_and_continues(tmp_path, monkeypatch) -> None:
    from tests.helpers import FAKE_CORE

    monkeypatch.setenv("VERIFYSIGNAL_CORE_CMD", str(FAKE_CORE))
    init_workspace(tmp_path, core_cmd=str(FAKE_CORE))
    create_current_understanding_workspace(tmp_path)
    _write_minimal_artifacts(tmp_path, "create-resource", parameters={"baseUrl": "https://example.test"})
    record = _write_record(after_commit="allowed-with-new-inputs", refresh_inputs=["resourceName"], core_risk="requires-confirmation")
    record.status = "ready"
    _save_runnable_record(tmp_path, record)
    _write_minimal_stage_artifacts(tmp_path, "create-resource")
    confirmation_id = check_prerequisites(tmp_path, "run", alias="create-resource")["rerunDecision"]["confirmationId"]

    result = run_command.run(
        tmp_path,
        "create-resource",
        interactive=False,
        core_cmd=str(FAKE_CORE),
        confirmed_risks=[confirmation_id],
    )

    assert result["status"] == "passed"
    assert result["rerunDecision"]["decision"] == "allowed-with-new-inputs"
    reviews = load_supersede_reviews(tmp_path, "create-resource")
    assert reviews[-1].sourceRunId == "previous-run"
    assert reviews[-1].ownerDecision == "approved-rerun-after-write"


def test_confirm_risk_with_wrong_id_keeps_confirmable_rerun_blocked(tmp_path, monkeypatch) -> None:
    from tests.helpers import FAKE_CORE

    monkeypatch.setenv("VERIFYSIGNAL_CORE_CMD", str(FAKE_CORE))
    init_workspace(tmp_path, core_cmd=str(FAKE_CORE))
    _write_minimal_artifacts(tmp_path, "create-resource", parameters={"baseUrl": "https://example.test"})
    _save_runnable_record(tmp_path, _write_record(after_commit="allowed-with-new-inputs", refresh_inputs=["resourceName"], core_risk="requires-confirmation"))

    result = run_command.run(
        tmp_path,
        "create-resource",
        interactive=False,
        core_cmd=str(FAKE_CORE),
        confirmed_risks=["confirm.create-resource.rerun-after-commit.other-run"],
    )

    assert result["status"] == "blocked"
    assert result["rerunDecision"]["decision"] == "requires-confirmation"
    assert result["rerunDecision"]["confirmationId"] == "confirm.create-resource.rerun-after-commit.previous-run"
    assert result["blockers"][0]["code"] == "runtime.rerun-confirmation-required"
    assert result["nextAction"] == "verifysignal workflow approve-rerun --alias create-resource --confirm-risk confirm.create-resource.rerun-after-commit.previous-run --json"
    assert load_supersede_reviews(tmp_path, "create-resource") == []


def _write_record(*, after_commit: str, refresh_inputs: list[str] | None = None, core_risk: str = "requires-confirmation") -> UseCaseRecord:
    return UseCaseRecord(
        alias="create-resource",
        title="Create Resource",
        description="Create resource.",
        runRequest=ArtifactReference(path=".verifysignal/run-requests/create-resource.yaml", kind="run-request", id="request.create-resource", version="1.0.0"),
        mainSkill=ArtifactReference(path=".verifysignal/skills/create-resource.browser.md", kind="skill", id="skill.create-resource", version="1.0.0"),
        skills=[ArtifactReference(path=".verifysignal/skills/create-resource.browser.md", kind="skill", id="skill.create-resource", version="1.0.0")],
        runtimeInputs=[
            RuntimeInputRequirement(name="baseUrl", source="default", value="https://example.test"),
            RuntimeInputRequirement(name="resourceName", source="generated", template="VerifySignal {{run.shortId}}", refreshOnRerunAfterCommit=True),
        ],
        sideEffects={
            "class": "write",
            "commitStepId": "submit-resource",
            "allowed": [{"id": "create-resource", "kind": "network", "methods": ["POST"], "urlContains": "/resources"}],
        },
        rerunPolicy={"afterNoCommit": "allowed", "afterCommit": after_commit, "refreshInputs": refresh_inputs or []},
        sideEffectLifecycle=_manual_cleanup_lifecycle(),
        artifactCapabilities=_current_write_capabilities(),
        lastRun={
            "runId": "previous-run",
            "status": "failed",
            "startedAt": "2026-08-04T00:00:00.000000001Z",
            "completedAt": "2026-08-04T00:00:00.000000002Z",
            "postCommitInterpretation": {
                "postCommit": True,
                "sideEffectMayExist": True,
                "failurePhase": "post-commit",
                "sideEffectStatus": "likely-committed",
                "rerunRisk": core_risk,
            },
        },
    )


def _save_runnable_record(project, record: UseCaseRecord) -> None:
    record.status = "ready"
    save_use_case(project, record)
    save_protected_ready_snapshot(project, record.alias, side_effect_class="write")


def _write_minimal_stage_artifacts(project, alias: str) -> None:
    root = layout.workflow_use_case_dir(project, alias)
    root.mkdir(parents=True, exist_ok=True)
    for name in ["spec", "plan", "tasks"]:
        (root / f"{name}.md").write_text(f"# {name}\n", encoding="utf-8")
        (root / f"{name}.yaml").write_text("{}\n", encoding="utf-8")
