from __future__ import annotations

import json
from pathlib import Path

from verifysignal_spec.workspace.models import ArtifactReference, UseCaseRecord
from verifysignal_spec.workspace.repository import init_workspace, save_use_case
from verifysignal_spec.workflows.models import ArtifactPlan
from verifysignal_spec.workflows.repository import save_artifact_plan
from tests.fixtures.workflows.entitlement_preflight_recovery import save_protected_ready_snapshot


ALIAS = "profile-view-unauth"
MAIN_SKILL_ID = "skill.validate-profile-view-unauth-flow"
HELPER_SKILL_ID = "skill.discover-profile"
MAIN_SKILL_PATH = ".verifysignal/skills/validate-profile-view-unauth-flow.browser.md"
HELPER_SKILL_PATH = ".verifysignal/skills/discover-profile.browser.md"


def create_main_skill_coverage_workspace(
    project: Path,
    *,
    alias: str = ALIAS,
    helper_first: bool = True,
    legacy_multi_skill_run_request: bool = False,
    core_cmd: str | None = None,
    protected_ready: bool = False,
) -> Path:
    init_workspace(project, core_cmd=core_cmd)
    (project / ".verifysignal/run-requests").mkdir(parents=True, exist_ok=True)
    (project / ".verifysignal/skills").mkdir(parents=True, exist_ok=True)
    (project / f".verifysignal/run-requests/{alias}.yaml").write_text(
        json.dumps(run_request(alias, helper_first=helper_first, include_helper=legacy_multi_skill_run_request)),
        encoding="utf-8",
    )
    (project / HELPER_SKILL_PATH).write_text(skill_markdown(HELPER_SKILL_ID, "Discover Profile", []), encoding="utf-8")
    (project / MAIN_SKILL_PATH).write_text(
        skill_markdown(MAIN_SKILL_ID, "Validate Profile View Unauth", ["overview-data-card", "projects-tab-content", "overview-profile-query"]),
        encoding="utf-8",
    )
    skills = [
        ArtifactReference(path=HELPER_SKILL_PATH, kind="skill", id=HELPER_SKILL_ID, version="1.0.0"),
        ArtifactReference(path=MAIN_SKILL_PATH, kind="skill", id=MAIN_SKILL_ID, version="2.1.0"),
    ]
    if not helper_first:
        skills.reverse()
    save_use_case(
        project,
        UseCaseRecord(
            alias=alias,
            title="Profile View Unauth",
            description="Validate a public profile page.",
            runRequest=ArtifactReference(path=f".verifysignal/run-requests/{alias}.yaml", kind="run-request", id=f"request.{alias}", version="1.0.0"),
            mainSkill=ArtifactReference(path=MAIN_SKILL_PATH, kind="skill", id=MAIN_SKILL_ID, version="2.1.0"),
            skills=skills,
            sourceOnlySkills=[ArtifactReference(path=HELPER_SKILL_PATH, kind="skill", id=HELPER_SKILL_ID, version="1.0.0")],
        ),
    )
    save_artifact_plan(
        project,
        ArtifactPlan(
            useCaseAlias=alias,
            runRequest=f".verifysignal/run-requests/{alias}.yaml",
            mainSkill=MAIN_SKILL_PATH,
            supportingSkills=[HELPER_SKILL_PATH],
            runtimeInputs=[{"name": "baseUrl", "required": True, "default": "https://app.example.test"}],
            validationGates=[
                {"id": "overview-data-card", "description": "Profile data card renders", "required": True},
                {"id": "projects-tab-content", "description": "Projects tab renders", "required": True},
                {"id": "overview-profile-query", "description": "Profile backend query completes", "required": True},
                {"id": "about-tab-content", "description": "About tab renders", "required": False, "condition": "About tab is visible for this profile."},
            ],
        ),
    )
    if protected_ready:
        save_protected_ready_snapshot(project, alias)
    return project


def run_request(alias: str = ALIAS, *, helper_first: bool = True, include_helper: bool = False) -> dict[str, object]:
    skills = [
        {"id": HELPER_SKILL_ID, "version": "1.0.0"},
        {"id": MAIN_SKILL_ID, "version": "2.1.0"},
    ]
    if not helper_first:
        skills.reverse()
    if not include_helper:
        skills = [{"id": MAIN_SKILL_ID, "version": "2.1.0"}]
    return {
        "schemaVersion": "qa-run-request/v1",
        "request": {"id": f"request.{alias}", "name": "Profile View Unauth"},
        "target": "browser",
        "validationScope": "feature-level",
        "mainSkill": MAIN_SKILL_ID,
        "skills": skills,
        "parameters": {"baseUrl": "https://app.example.test"},
    }


def skill_markdown(skill_id: str, name: str, gate_ids: list[str]) -> str:
    steps = [{"id": "open", "action": "navigate", "value": "{{parameters.baseUrl}}/profile/casey-morgan/overview"}]
    assertions = [
        {"id": f"assert-{gate_id}", "kind": "visible", "target": "profileName", "gateId": gate_id}
        for gate_id in gate_ids
    ]
    return """# {name}

```yaml
schemaVersion: qa-skill/v1
skill:
  id: {skill_id}
  version: 1.0.0
  kind: browser
  name: {name}
browser:
  targets:
    profileName:
      css: h2
      domainSemantics: Profile name in the data card
  steps: {steps}
  assertions: {assertions}
```
""".format(
        name=name,
        skill_id=skill_id,
        steps=json.dumps(steps),
        assertions=json.dumps(assertions),
    )
