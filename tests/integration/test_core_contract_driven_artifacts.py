from __future__ import annotations

import json

from verifysignal_spec.workflows.stage_persistence import persist_stage
from verifysignal_spec.workflows.engine import create_workflow_run
from verifysignal_spec.workflows.transitions import transition_workflow
from verifysignal_spec.workspace.repository import init_workspace, load_document
from tests.helpers import FAKE_CORE


def _prepare_project(project) -> None:
    init_workspace(project, core_cmd=str(FAKE_CORE))
    create_workflow_run(
        project,
        "Create a collaboration project.",
        alias="add-collaboration-project",
        integration="codex",
    )
    specified = persist_stage(
        project,
        "specify",
        alias="add-collaboration-project",
        payload={
            "alias": "add-collaboration-project",
            "surface": "/manage/project/add",
            "behavior": "Create a collaboration project.",
            "expectedOutcome": "Project page renders.",
            "customSourceReason": "Authenticated credential fixture.",
        },
    )
    assert specified["status"] == "persisted"
    clarified = persist_stage(
        project,
        "clarify",
        alias="add-collaboration-project",
        payload={
            "answers": [
                {
                    "questionId": "browser-target-environment",
                    "answerSummary": "https://app.example.test",
                    "confirmationSource": "direct-user",
                }
            ]
        },
    )
    assert clarified["status"] == "persisted"
    planned = persist_stage(
        project,
        "plan",
        alias="add-collaboration-project",
        payload={
            "runRequest": ".verifysignal/run-requests/add-collaboration-project.yaml",
            "mainSkill": ".verifysignal/skills/validate-add-collaboration-project-flow.browser.md",
            "reusableSkills": [".verifysignal/skills/validate-add-collaboration-project-flow.browser.md"],
            "runtimeInputs": [{"name": "baseUrl", "value": "https://app.example.test"}],
            "unresolvedBlockingClarifications": [],
        },
    )
    assert planned["status"] == "persisted"
    transition_workflow(
        project,
        "add-collaboration-project",
        stage="tasks",
        outcome="completed",
        handoff_summary="Canonical Core-contract fixture setup.",
    )


def test_authenticated_artifact_generation_uses_core_credential_contract(tmp_path) -> None:
    _prepare_project(tmp_path)

    result = persist_stage(
        tmp_path,
        "implement",
        alias="add-collaboration-project",
        payload={
            "runRequest": {"path": ".verifysignal/run-requests/add-collaboration-project.yaml"},
            "credentialRefs": {
                "e2eUser": {
                    "source": "environment",
                    "keys": {"email": "E2E_USER_EMAIL", "password": "E2E_USER_PASSWORD"},
                }
            },
            "skills": [
                {
                    "path": ".verifysignal/skills/validate-add-collaboration-project-flow.browser.md",
                    "kind": "skill",
                    "browser": {
                        "targets": {
                            "emailInput": {"testId": "email-input"},
                            "passwordInput": {"testId": "password-input"},
                        },
                        "steps": [
                            {"id": "fill-email", "action": "fill", "target": "emailInput", "value": "{{credentials.e2eUser.email}}"},
                            {"id": "fill-password", "action": "fill", "target": "passwordInput", "value": "{{credentials.e2eUser.password}}"},
                        ],
                    },
                }
            ],
        },
    )

    assert result["status"] == "persisted"
    run_request = json.loads((tmp_path / ".verifysignal/run-requests/add-collaboration-project.yaml").read_text())
    skill = (tmp_path / ".verifysignal/skills/validate-add-collaboration-project-flow.browser.md").read_text()
    use_case = load_document(tmp_path / ".verifysignal/use-cases/add-collaboration-project.yaml")

    assert run_request["credentialRefs"]["e2eUser"]["keys"]["email"] == "E2E_USER_EMAIL"
    assert "{{credentials.e2eUser.email}}" in skill
    assert "{{credentials.e2eUser.password}}" in skill
    assert "user@example.com" not in json.dumps(run_request)
    assert use_case["credentialRefs"]["e2eUser"]["source"] == "environment"
    assert all(item["name"] not in {"userEmail", "userPassword"} for item in use_case.get("runtimeInputs", []))


def test_implement_persistence_accepts_core_added_browser_action(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("VERIFYSIGNAL_CORE_CMD", str(FAKE_CORE))
    monkeypatch.setenv("FAKE_VERIFYSIGNAL_MODE", "contract-drift")
    _prepare_project(tmp_path)

    result = persist_stage(
        tmp_path,
        "implement",
        alias="add-collaboration-project",
        payload={
            "runRequest": {"path": ".verifysignal/run-requests/add-collaboration-project.yaml"},
            "skills": [
                {
                    "path": ".verifysignal/skills/validate-add-collaboration-project-flow.browser.md",
                    "kind": "skill",
                    "browser": {
                        "targets": {"searchBox": {"testId": "search-box"}},
                        "steps": [{"id": "press-enter", "action": "press", "target": "searchBox", "value": "Enter"}],
                    },
                }
            ],
        },
    )

    assert result["status"] == "persisted"


def test_implement_persistence_rejects_core_removed_browser_action(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("VERIFYSIGNAL_CORE_CMD", str(FAKE_CORE))
    monkeypatch.setenv("FAKE_VERIFYSIGNAL_MODE", "contract-drift")
    _prepare_project(tmp_path)

    result = persist_stage(
        tmp_path,
        "implement",
        alias="add-collaboration-project",
        payload={
            "runRequest": {"path": ".verifysignal/run-requests/add-collaboration-project.yaml"},
            "skills": [
                {
                    "path": ".verifysignal/skills/validate-add-collaboration-project-flow.browser.md",
                    "kind": "skill",
                    "browser": {
                        "steps": [{"id": "legacy-repeat", "action": "repeatUntil", "until": {"text": "Done"}, "do": {"action": "click"}}],
                    },
                }
            ],
        },
    )

    assert result["status"] == "invalid"
    assert "repeatUntil" in result["blockers"][0]["message"]
