from __future__ import annotations

import json

from verifysignal_spec.commands import run as run_command
from verifysignal_spec.commands.validate import run as validate_run
from tests.fixtures.workflows.main_skill_run_coverage import create_main_skill_coverage_workspace


def test_validate_blocks_when_core_contract_required_section_missing(tmp_path, monkeypatch) -> None:
    from tests.helpers import FAKE_CORE

    monkeypatch.setenv("VERIFYSIGNAL_CORE_CMD", str(FAKE_CORE))
    monkeypatch.setenv("FAKE_VERIFYSIGNAL_MODE", "contracts-missing-browser")
    create_main_skill_coverage_workspace(tmp_path)

    result = validate_run(tmp_path, "profile-view-unauth", runtime_readiness=True, core_cmd=str(FAKE_CORE))

    assert result["status"] == "blocked"
    assert result["blockers"][0]["code"] == "core-contract.section-missing"
    assert result["blockers"][0]["repairable"] is False


def test_run_blocks_when_core_contract_required_section_malformed(tmp_path, monkeypatch) -> None:
    from tests.helpers import FAKE_CORE

    monkeypatch.setenv("VERIFYSIGNAL_CORE_CMD", str(FAKE_CORE))
    monkeypatch.setenv("FAKE_VERIFYSIGNAL_MODE", "contracts-malformed-browser")
    create_main_skill_coverage_workspace(
        tmp_path,
        core_cmd=str(FAKE_CORE),
        protected_ready=True,
    )

    result = run_command.run(tmp_path, "profile-view-unauth", interactive=False, core_cmd=str(FAKE_CORE))

    assert result["status"] == "blocked"
    assert result["coreStatus"] == "blocked"
    assert result["blockers"][0]["code"] == "core-contract.section-malformed"


def test_missing_contracts_operation_blocks_executable_validation(tmp_path, monkeypatch) -> None:
    from tests.helpers import FAKE_CORE

    monkeypatch.setenv("VERIFYSIGNAL_CORE_CMD", str(FAKE_CORE))
    monkeypatch.setenv("FAKE_VERIFYSIGNAL_MODE", "missing-contracts-operation")
    create_main_skill_coverage_workspace(tmp_path)

    result = validate_run(tmp_path, "profile-view-unauth", runtime_readiness=True, core_cmd=str(FAKE_CORE))

    assert result["status"] == "blocked"
    assert result["blockers"][0]["code"] == "core-contract.bootstrap-incompatible"


def test_legacy_executable_artifacts_block_without_rewrite(tmp_path, monkeypatch) -> None:
    from tests.helpers import FAKE_CORE

    monkeypatch.setenv("VERIFYSIGNAL_CORE_CMD", str(FAKE_CORE))
    create_main_skill_coverage_workspace(tmp_path)
    run_request_path = tmp_path / ".verifysignal/run-requests/profile-view-unauth.yaml"
    legacy_content = json.dumps(
        {
            "schemaVersion": "legacy-run-request/v0",
            "request": {"id": "request.profile-view-unauth", "name": "Profile"},
            "skills": [{"id": "skill.profile-view-unauth", "version": "1.0.0"}],
        },
        indent=2,
    )
    run_request_path.write_text(legacy_content, encoding="utf-8")

    result = validate_run(tmp_path, "profile-view-unauth", runtime_readiness=True, core_cmd=str(FAKE_CORE))

    assert result["status"] == "blocked"
    assert result["blockers"][0]["code"] == "core-contract.legacy-artifact"
    assert run_request_path.read_text(encoding="utf-8") == legacy_content
