from __future__ import annotations

import time

from helpers import FAKE_CORE
from verifysignal_spec.core.adapter import CoreAdapter
from verifysignal_spec.core.executable_contract import CommandContractReuse
from verifysignal_spec.workflows.authoring_coherence import evaluate_implementation_coherence
from verifysignal_spec.workspace.repository import init_workspace
from verifysignal_spec.workflows.evidence import extract_core_runtime_evidence, normalize_planned_gates
from verifysignal_spec.workflows.gate_coverage import calculate_gate_coverage, coverage_status
from verifysignal_spec.workflows.readiness import validation_readiness
from verifysignal_spec.workflows.repair_recommendations import recommend_repairs_for_gate_coverage
from verifysignal_spec.workflows.engine import create_workflow_run, generate_tasks, implement_artifacts, plan_artifacts, specify, workflow_list
from verifysignal_spec.workflows.prerequisites import check_prerequisites
from verifysignal_spec.workflows.transitions import transition_workflow
from tests.fixtures.workflows.real_run_guardrails import coherent_profile_skill, create_real_run_guardrail_workspace, run_request_payload
from tests.fixtures.workflows.skill_execution_boundary import create_planned_workspace


def test_workflow_status_list_handles_50_runs_under_one_second(tmp_path) -> None:
    init_workspace(tmp_path)
    for index in range(50):
        create_workflow_run(tmp_path, f"Validate behavior {index}.", alias=f"case-{index}", integration="codex")
    started = time.monotonic()
    result = workflow_list(tmp_path)
    elapsed = time.monotonic() - started
    assert len(result["runs"]) == 50
    assert elapsed < 1.0


def test_representative_workflow_checks_complete_under_one_second(tmp_path) -> None:
    init_workspace(tmp_path)
    create_workflow_run(tmp_path, "Validate login.", alias="login", integration="codex")
    specify(tmp_path, "login", "Validate login.")
    plan_artifacts(tmp_path, "login")
    generate_tasks(tmp_path, "login")
    implement_artifacts(tmp_path, "login")
    for stage in ("specify", "clarify", "plan", "tasks", "implement"):
        transition_workflow(
            tmp_path,
            "login",
            stage=stage,
            outcome="completed",
            handoff_summary="Performance fixture setup.",
        )

    started = time.monotonic()
    results = [
        check_prerequisites(tmp_path, "specify"),
        check_prerequisites(tmp_path, "clarify", alias="login"),
        check_prerequisites(tmp_path, "tasks", alias="login"),
        check_prerequisites(tmp_path, "validate", alias="login"),
    ]
    elapsed = time.monotonic() - started
    assert [result["status"] for result in results] == ["ready", "ready", "ready", "ready"]
    assert elapsed < 1.0


def test_validation_readiness_check_completes_under_one_second_without_core(tmp_path) -> None:
    init_workspace(tmp_path, core_cmd="missing-verifysignal-core-for-test")
    create_workflow_run(tmp_path, "Validate login.", alias="login", integration="codex")
    specify(tmp_path, "login", "Validate login.")
    plan_artifacts(tmp_path, "login")
    generate_tasks(tmp_path, "login")
    implement_artifacts(tmp_path, "login")

    started = time.monotonic()
    result = validation_readiness(tmp_path, alias="login")
    elapsed = time.monotonic() - started
    assert result["schemaVersion"] == "verifysignal-spec-validation-readiness/v1"
    assert elapsed < 1.0


def test_authoring_coherence_completes_under_one_second(tmp_path) -> None:
    create_real_run_guardrail_workspace(tmp_path)

    started = time.monotonic()
    result = evaluate_implementation_coherence(
        tmp_path,
        "profile-view-unauth",
        {"runRequest": run_request_payload(), "skills": [coherent_profile_skill()]},
    )
    elapsed = time.monotonic() - started

    assert result.status == "passed"
    assert elapsed < 1.0


def test_runtime_coverage_classification_and_repair_recommendations_stay_under_one_second() -> None:
    gates, _warnings = normalize_planned_gates(
        [
            {"id": f"gate-{index}", "description": f"Required rendered result {index}", "required": True}
            for index in range(100)
        ]
    )
    core_result = {
        "status": "passed",
        "data": {
            "gateEvidence": [
                {"id": f"assert-{index}", "source": "assertion", "gateId": f"gate-{index}", "status": "passed", "target": f"target-{index}"}
                for index in range(50)
            ]
        },
    }

    started = time.monotonic()
    inventory = extract_core_runtime_evidence(core_result, known_gate_ids={gate.id for gate in gates})
    coverage = calculate_gate_coverage(gates, inventory)
    status = coverage_status("passed", coverage)
    recommendations = recommend_repairs_for_gate_coverage(coverage, gates, source_run_id="run-1")
    elapsed = time.monotonic() - started

    assert status == "incomplete"
    assert len(recommendations) == 50
    assert elapsed < 1.0


def test_core_contract_projection_reuses_discovery_within_one_command_only() -> None:
    adapter = CoreAdapter(executable=str(FAKE_CORE))
    first_command = CommandContractReuse()
    second_command = CommandContractReuse()

    first_projection = first_command.get_or_discover(
        runtime_identity=str(FAKE_CORE),
        core_version="0.1.0",
        public_contract_version="verifysignal-public-cli-json/v1",
        discover=adapter.contracts,
    )
    second_projection = first_command.get_or_discover(
        runtime_identity=str(FAKE_CORE),
        core_version="0.1.0",
        public_contract_version="verifysignal-public-cli-json/v1",
        discover=adapter.contracts,
    )
    third_projection = second_command.get_or_discover(
        runtime_identity=str(FAKE_CORE),
        core_version="0.1.0",
        public_contract_version="verifysignal-public-cli-json/v1",
        discover=adapter.contracts,
    )

    assert first_projection == second_projection
    assert third_projection == first_projection
    assert first_command.discovery_count == 1
    assert second_command.discovery_count == 1


def test_execution_boundary_overhead_adds_less_than_fifty_ms_without_core_discovery(tmp_path, monkeypatch) -> None:
    from verifysignal_spec.workspace.repository import load_use_case
    from verifysignal_spec.workflows.skill_execution_boundary import resolve_execution_boundary

    create_planned_workspace(tmp_path)
    record = load_use_case(tmp_path, "brands-search-authenticated")
    core_contract = {"sections": {"skillExecution": {"status": "unsupported", "multiSkillSupported": False}}}

    def fail_contracts(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("execution-boundary resolution must not discover Core contracts")

    monkeypatch.setattr(CoreAdapter, "contracts", fail_contracts)
    started = time.monotonic()
    for _ in range(100):
        decision = resolve_execution_boundary(record, core_contract=core_contract)
    elapsed = time.monotonic() - started

    assert decision.executableSkills[0].path.endswith("validate-brands-search-authenticated-flow.browser.md")
    assert elapsed < 0.05
