from __future__ import annotations

import json

from verifysignal_spec.commands import run as run_command
from verifysignal_spec.commands import validate as validate_command
from verifysignal_spec.workspace.artifacts import render_run_request
from verifysignal_spec.workspace.repository import load_use_case, save_use_case

from tests.fixtures.workflows.side_effect_contract_alignment import create_write_policy_workspace, templated_confirmation_policy
from tests.fixtures.workflows.entitlement_preflight_recovery import save_protected_ready_snapshot
from tests.helpers import FAKE_CORE, assert_prepared_confirmation_value


def test_run_prepares_resolved_confirmation_values_before_core_execution(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("VERIFYSIGNAL_CORE_CMD", str(FAKE_CORE))
    monkeypatch.setenv("VERIFYSIGNAL_RUNTIME_CACHE_DIR", str(tmp_path / "runtime-cache"))
    record = create_write_policy_workspace(tmp_path, side_effects=templated_confirmation_policy())
    record.sideEffectLifecycle = {"cleanupPolicy": "manual", "cleanupRequired": True, "instructions": "Delete created project."}
    record.artifactCapabilities = {
        "capabilities": [
            "explicit-confirmation",
            "write-activity-interpretation",
            "side-effect-lifecycle",
            "resource-identity",
            "generated-runtime-inputs",
        ]
    }
    save_use_case(tmp_path, record)
    (tmp_path / record.runRequest.path).write_text(
        render_run_request(record, parameters={"baseUrl": "https://example.test"}),
        encoding="utf-8",
    )
    save_protected_ready_snapshot(tmp_path, record.alias, side_effect_class="write")

    result = run_command.run(tmp_path, "add-collaboration-project", interactive=False, core_cmd=str(FAKE_CORE))

    assert result["status"] == "passed"
    prepared = list((tmp_path / ".verifysignal/runs/add-collaboration-project").glob("*.run-request.json"))
    assert prepared
    document = json.loads(prepared[0].read_text(encoding="utf-8"))
    generated_title = document["parameters"]["projectTitle"]
    assert_prepared_confirmation_value(document, "published-title-confirmed", "expectedContains", generated_title)


def test_validate_blocks_unresolved_confirmation_placeholder_before_authoring_check(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("VERIFYSIGNAL_CORE_CMD", str(FAKE_CORE))
    monkeypatch.setenv("VERIFYSIGNAL_RUNTIME_CACHE_DIR", str(tmp_path / "runtime-cache"))
    record = create_write_policy_workspace(
        tmp_path,
        side_effects=templated_confirmation_policy(placeholder="{{parameters.missingTitle}}"),
    )
    record.status = "ready"
    save_use_case(tmp_path, record)
    save_protected_ready_snapshot(tmp_path, record.alias, side_effect_class="write")

    result = validate_command.run(tmp_path, "add-collaboration-project", runtime_readiness=True, core_cmd=str(FAKE_CORE))

    assert result["status"] == "blocked"
    assert any(item["code"] == "runtime.confirmation-placeholder-unresolved" for item in result["blockers"])
    saved = load_use_case(tmp_path, "add-collaboration-project")
    assert saved.lastRun is None


def test_repeated_validate_replaces_its_private_prepared_request_without_a_collision(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("VERIFYSIGNAL_CORE_CMD", str(FAKE_CORE))
    monkeypatch.setenv("VERIFYSIGNAL_RUNTIME_CACHE_DIR", str(tmp_path / "runtime-cache"))
    record = create_write_policy_workspace(
        tmp_path,
        side_effects=templated_confirmation_policy(),
    )
    record.status = "ready"
    save_use_case(tmp_path, record)

    first = validate_command.run(
        tmp_path,
        record.alias,
        runtime_readiness=True,
        core_cmd=str(FAKE_CORE),
    )
    second = validate_command.run(
        tmp_path,
        record.alias,
        runtime_readiness=True,
        core_cmd=str(FAKE_CORE),
    )

    assert first["status"] == "passed"
    assert second["status"] == "passed"
    prepared = (
        tmp_path
        / ".verifysignal"
        / "readiness"
        / record.alias
        / f"{record.alias}-validation.run-request.json"
    )
    assert prepared.is_file()
