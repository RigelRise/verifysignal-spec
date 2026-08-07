from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from verifysignal_spec.workspace.models import ArtifactReference, UseCaseRecord
from verifysignal_spec.workspace.repository import init_workspace, save_use_case
from verifysignal_spec.workflows.engine import create_workflow_run
from verifysignal_spec.workflows.models import ArtifactPlan
from verifysignal_spec.workflows.repository import save_artifact_plan
from verifysignal_spec.workflows.transitions import transition_workflow


ALIAS = "brands-search-authenticated"
MAIN_SKILL_PATH = ".verifysignal/skills/validate-brands-search-authenticated-flow.browser.md"
LOGIN_SKILL_PATH = ".verifysignal/skills/login-feats-credentials.browser.md"
MAIN_SKILL_ID = "skill.validate-brands-search-authenticated-flow"
LOGIN_SKILL_ID = "skill.login-app-credentials"


def main_browser(*, include_login: bool = False) -> dict[str, Any]:
    targets = {
        "loggedInNav": {"css": 'a[href="/messages"]'},
        "brandsTab": {"text": "Brands"},
    }
    steps: list[dict[str, Any]] = []
    if include_login:
        targets.update(login_browser()["targets"])
        steps.extend(login_browser()["steps"])
    steps.extend(
        [
            {"id": "open-brands", "action": "navigate", "value": "{{parameters.baseUrl}}/search/brands"},
            {"id": "wait-brands", "action": "waitForText", "target": "brandsTab", "value": "Brands", "gateId": "brands-authenticated-surface"},
        ]
    )
    return {
        "targets": targets,
        "steps": steps,
        "assertions": [
            {"id": "logged-in-nav-visible", "kind": "visible", "target": "loggedInNav", "gateId": "login-succeeds"},
            {"id": "brands-tab-visible", "kind": "visible", "target": "brandsTab", "gateId": "brands-authenticated-surface"},
        ],
    }


def login_browser() -> dict[str, Any]:
    return {
        "targets": {
            "emailInput": {"testId": "email-input"},
            "passwordInput": {"testId": "password-input"},
            "submit": {"css": 'button[type="submit"]'},
            "loggedInNav": {"css": 'a[href="/messages"]'},
        },
        "steps": [
            {"id": "open-signin", "action": "navigate", "value": "{{parameters.baseUrl}}/sign-in/email"},
            {"id": "fill-email", "action": "fill", "target": "emailInput", "value": "{{credentials.app.email}}"},
            {"id": "click-email", "action": "click", "target": "submit"},
            {"id": "fill-password", "action": "fill", "target": "passwordInput", "value": "{{credentials.app.password}}"},
            {"id": "click-signin", "action": "click", "target": "submit"},
        ],
        "assertions": [
            {"id": "login-helper-nav-visible", "kind": "visible", "target": "loggedInNav", "gateId": "login-succeeds"}
        ],
    }


def implementation_payload(*, composed_main: bool = False) -> dict[str, Any]:
    return {
        "alias": ALIAS,
        "runRequest": {
            "path": f".verifysignal/run-requests/{ALIAS}.yaml",
            "parameters": {"baseUrl": "https://app.example.test"},
        },
        "runtimeInputs": [{"name": "baseUrl", "required": True, "value": "https://app.example.test"}],
        "credentialRefs": {"app": {"source": "environment", "keys": {"email": "APP_TEST_EMAIL", "password": "APP_TEST_PASSWORD"}}},
        "skills": [
            {"path": MAIN_SKILL_PATH, "id": MAIN_SKILL_ID, "version": "1.0.0", "browser": main_browser(include_login=composed_main)},
            {"path": LOGIN_SKILL_PATH, "id": LOGIN_SKILL_ID, "version": "1.0.0", "browser": login_browser()},
        ],
        "skillComposition": {
            "mode": "inline-into-main",
            "mainSkillPath": MAIN_SKILL_PATH,
            "sourceSkillPaths": [LOGIN_SKILL_PATH],
            "credentialReferencePolicy": "preserve-placeholders",
            "gateEvidenceMappings": [{"sourceSkillPath": LOGIN_SKILL_PATH, "sourceGateId": "login-succeeds", "gateId": "login-succeeds"}],
        },
    }


def create_planned_workspace(project: Path, *, core_cmd: str | None = None) -> None:
    init_workspace(project, core_cmd=core_cmd)
    save_use_case(
        project,
        UseCaseRecord(
            alias=ALIAS,
            title="Brands Search Authenticated",
            description="Validate authenticated brands search.",
            targetSurface="/search/brands",
            runRequest=ArtifactReference(path=f".verifysignal/run-requests/{ALIAS}.yaml", kind="run-request", id=f"request.{ALIAS}"),
            mainSkill=ArtifactReference(path=MAIN_SKILL_PATH, kind="skill", id=MAIN_SKILL_ID, version="1.0.0"),
            skills=[ArtifactReference(path=MAIN_SKILL_PATH, kind="skill", id=MAIN_SKILL_ID, version="1.0.0")],
        ),
    )
    save_artifact_plan(
        project,
        ArtifactPlan(
            useCaseAlias=ALIAS,
            runRequest=f".verifysignal/run-requests/{ALIAS}.yaml",
            mainSkill=MAIN_SKILL_PATH,
            supportingSkills=[LOGIN_SKILL_PATH],
            sourceOnlySkills=[LOGIN_SKILL_PATH],
            skillComposition={
                "mode": "inline-into-main",
                "mainSkillPath": MAIN_SKILL_PATH,
                "sourceSkillPaths": [LOGIN_SKILL_PATH],
            },
            gateEvidenceMappings=[
                {"sourceSkillPath": LOGIN_SKILL_PATH, "sourceGateId": "login-succeeds", "gateId": "login-succeeds"}
            ],
            runtimeInputs=[{"name": "baseUrl", "required": True, "value": "https://app.example.test"}],
            validationGates=[
                {"id": "login-succeeds", "required": True, "description": "Login succeeds"},
                {"id": "brands-authenticated-surface", "required": True, "description": "Brands tab renders authenticated"},
            ],
        ),
    )
    create_workflow_run(
        project,
        "Validate authenticated brands search.",
        alias=ALIAS,
        integration="codex",
    )
    for stage in ("specify", "clarify", "plan", "tasks"):
        transition_workflow(
            project,
            ALIAS,
            stage=stage,
            outcome="completed",
            handoff_summary="Canonical skill-boundary fixture setup.",
        )


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
