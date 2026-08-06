from __future__ import annotations

from verifysignal_spec.workflows.stage_persistence import persist_stage
from verifysignal_spec.workspace.repository import load_document, load_use_case
from tests.fixtures.workflows.skill_execution_boundary import (
    ALIAS,
    LOGIN_SKILL_PATH,
    MAIN_SKILL_PATH,
    create_planned_workspace,
    implementation_payload,
)


def test_source_only_not_in_run_request(tmp_path, monkeypatch) -> None:
    from tests.helpers import FAKE_CORE

    monkeypatch.setenv("VERIFYSIGNAL_CORE_CMD", str(FAKE_CORE))
    create_planned_workspace(tmp_path, core_cmd=str(FAKE_CORE))

    result = persist_stage(tmp_path, "implement", alias=ALIAS, payload=implementation_payload(composed_main=True))

    assert result["status"] == "persisted"
    run_request = load_document(tmp_path / f".verifysignal/run-requests/{ALIAS}.yaml")
    assert run_request["skills"] == [{"id": "skill.validate-brands-search-authenticated-flow", "version": "1.0.0"}]
    record = load_use_case(tmp_path, ALIAS)
    assert [skill.path for skill in record.sourceOnlySkills] == [LOGIN_SKILL_PATH]
    assert (tmp_path / LOGIN_SKILL_PATH).exists()


def test_compose_login_into_main(tmp_path, monkeypatch) -> None:
    from tests.helpers import FAKE_CORE

    monkeypatch.setenv("VERIFYSIGNAL_CORE_CMD", str(FAKE_CORE))
    create_planned_workspace(tmp_path, core_cmd=str(FAKE_CORE))

    result = persist_stage(tmp_path, "implement", alias=ALIAS, payload=implementation_payload(composed_main=False))

    assert result["status"] == "persisted"
    main_skill = (tmp_path / MAIN_SKILL_PATH).read_text(encoding="utf-8")
    assert "open-signin" in main_skill
    assert "fill-email" in main_skill
    assert "open-brands" in main_skill
    assert main_skill.index("open-signin") < main_skill.index("open-brands")
    assert "{{credentials.app.password}}" in main_skill
    assert "APP_TEST_PASSWORD" not in main_skill


def test_source_skill_gate_evidence_does_not_satisfy_required_gate_without_main_mapping(tmp_path, monkeypatch) -> None:
    from tests.helpers import FAKE_CORE

    monkeypatch.setenv("VERIFYSIGNAL_CORE_CMD", str(FAKE_CORE))
    create_planned_workspace(tmp_path, core_cmd=str(FAKE_CORE))
    payload = implementation_payload(composed_main=False)
    payload["skills"][0]["browser"]["assertions"] = [
        assertion
        for assertion in payload["skills"][0]["browser"]["assertions"]
        if assertion.get("gateId") != "login-succeeds"
    ]

    result = persist_stage(tmp_path, "implement", alias=ALIAS, payload=payload)

    assert result["status"] == "persisted"
    record = load_use_case(tmp_path, ALIAS)
    coverage = record.validation["authoringCoherence"]["gateCoverage"]
    assert next(item for item in coverage if item["gateId"] == "login-succeeds")["status"] == "exercised"
