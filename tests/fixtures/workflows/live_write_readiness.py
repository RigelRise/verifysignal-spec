from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from verifysignal_spec import __version__ as SPEC_VERSION
from verifysignal_spec.workspace.models import (
    ArtifactReference,
    ReadinessSnapshot,
    RuntimeInputRequirement,
    UseCaseRecord,
)
from verifysignal_spec.workspace.repository import (
    artifact_fingerprints,
    init_workspace,
    save_readiness_snapshot,
    save_use_case,
)
from verifysignal_spec.workspace import layout


def create_live_write_readiness_workspace(project: Path) -> None:
    init_workspace(project, core_cmd="verifysignal-core")
    _write_artifacts(project, "about-page-unauth", {"baseUrl": "https://example.test"})
    _write_artifacts(project, "brands-search-authenticated", {"baseUrl": "https://example.test"})
    _write_artifacts(project, "add-collaboration-project", {"baseUrl": "https://example.test"})
    save_use_case(
        project,
        UseCaseRecord(
            alias="about-page-unauth",
            title="About Page",
            description="Validate the public about page.",
            targetSurface="/about",
            runRequest=ArtifactReference(path=".verifysignal/run-requests/about-page-unauth.yaml", kind="run-request", id="request.about-page-unauth", version="1.0.0"),
            mainSkill=ArtifactReference(path=".verifysignal/skills/about-page-unauth.browser.md", kind="skill", id="skill.about-page-unauth", version="1.0.0"),
            skills=[ArtifactReference(path=".verifysignal/skills/about-page-unauth.browser.md", kind="skill", id="skill.about-page-unauth", version="1.0.0")],
            runtimeInputs=[RuntimeInputRequirement(name="baseUrl", source="default", value="https://example.test")],
            sideEffects={"class": "none"},
            lastRun=_last_run("about-run"),
        ),
    )
    for alias in ["about-page-unauth", "brands-search-authenticated", "add-collaboration-project"]:
        _write_workflow_stage_artifacts(project, alias)
    save_use_case(
        project,
        UseCaseRecord(
            alias="brands-search-authenticated",
            title="Brands Search",
            description="Validate authenticated brands search.",
            targetSurface="/search/brands",
            runRequest=ArtifactReference(path=".verifysignal/run-requests/brands-search-authenticated.yaml", kind="run-request", id="request.brands-search-authenticated", version="1.0.0"),
            mainSkill=ArtifactReference(path=".verifysignal/skills/brands-search-authenticated.browser.md", kind="skill", id="skill.brands-search-authenticated", version="1.0.0"),
            skills=[ArtifactReference(path=".verifysignal/skills/brands-search-authenticated.browser.md", kind="skill", id="skill.brands-search-authenticated", version="1.0.0")],
            runtimeInputs=[RuntimeInputRequirement(name="baseUrl", source="default", value="https://example.test")],
            credentialRefs={"app": {"source": "environment", "keys": {"email": "APP_TEST_EMAIL", "password": "APP_TEST_PASSWORD"}}},
            credentialGroups=[{"name": "app"}],
            sideEffects={"class": "authenticated-read"},
            lastRun=_last_run("brands-run"),
        ),
    )
    save_use_case(
        project,
        UseCaseRecord(
            alias="add-collaboration-project",
            title="Add Collaboration Project",
            description="Publish a collaboration project.",
            targetSurface="/",
            runRequest=ArtifactReference(path=".verifysignal/run-requests/add-collaboration-project.yaml", kind="run-request", id="request.add-collaboration-project", version="1.0.0"),
            mainSkill=ArtifactReference(path=".verifysignal/skills/add-collaboration-project.browser.md", kind="skill", id="skill.add-collaboration-project", version="1.0.0"),
            skills=[ArtifactReference(path=".verifysignal/skills/add-collaboration-project.browser.md", kind="skill", id="skill.add-collaboration-project", version="1.0.0")],
            runtimeInputs=[
                RuntimeInputRequirement(name="baseUrl", source="default", value="https://example.test"),
                RuntimeInputRequirement(name="resourceName", source="generated", template="validation-resource-{{run.shortId}}", refreshOnRerunAfterCommit=True),
            ],
            credentialRefs={"app": {"source": "environment", "keys": {"email": "APP_TEST_EMAIL", "password": "APP_TEST_PASSWORD"}}},
            credentialGroups=[{"name": "app"}],
            sideEffects={
                "class": "write",
                "commitStepId": "confirm-publish-dialog",
                "allowed": [{"id": "create-project", "kind": "network", "methods": ["POST"], "urlContains": "graphql"}],
            },
            rerunPolicy={"afterNoCommit": "allowed", "afterCommit": "requires-confirmation"},
            lastRun=_last_run("write-run"),
        ),
    )


def save_ready_snapshot(project: Path, alias: str, *, checked_at: str | None = None, side_effect_class: str = "none") -> None:
    from verifysignal_spec.workspace.repository import load_use_case

    record = load_use_case(project, alias)
    save_readiness_snapshot(
        project,
        ReadinessSnapshot(
            alias=alias,
            status="ready",
            checkedAt=checked_at or datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            commandCompatibilityStatus="passed",
            trustMaterialStatus="ready",
            protectedOperationStatus="passed",
            readinessScope="protected-operation",
            artifactFingerprints=artifact_fingerprints(project, record),
            specVersion=SPEC_VERSION,
            artifactContractVersion="verifysignal-spec-use-case/v1",
            targetProjectRevision=None,
            testedCodeScopeStatus="unknown",
            environmentBoundCredentialGroups=["app"] if record.credentialRefs else [],
            sideEffectClass=side_effect_class,
        ),
    )


def old_checked_at(*, days: int = 0, hours: int = 0) -> str:
    return (datetime.now(UTC) - timedelta(days=days, hours=hours)).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _last_run(run_id: str) -> dict[str, Any]:
    return {
        "runId": run_id,
        "status": "passed",
        "coreStatus": "passed",
        "coverageStatus": "complete",
        "profile": "debug",
    }


def _write_artifacts(project: Path, alias: str, parameters: dict[str, str]) -> None:
    (project / ".verifysignal/run-requests").mkdir(parents=True, exist_ok=True)
    (project / ".verifysignal/skills").mkdir(parents=True, exist_ok=True)
    (project / f".verifysignal/run-requests/{alias}.yaml").write_text(
        json.dumps(
            {
                "schemaVersion": "qa-run-request/v1",
                "request": {"id": f"request.{alias}", "name": alias},
                "target": "browser",
                "validationScope": "feature-level",
                "skills": [{"id": f"skill.{alias}", "version": "1.0.0"}],
                "parameters": parameters,
            }
        ),
        encoding="utf-8",
    )


def _write_workflow_stage_artifacts(project: Path, alias: str) -> None:
    root = layout.workflow_use_case_dir(project, alias)
    root.mkdir(parents=True, exist_ok=True)
    for stage, content in {
        "spec.md": f"# Spec\n\n{alias}\n",
        "plan.md": f"# Plan\n\n{alias}\n",
        "plan.yaml": json.dumps({"useCaseAlias": alias}),
        "tasks.md": f"# Tasks\n\n{alias}\n",
        "tasks.yaml": json.dumps({"useCaseAlias": alias, "tasks": []}),
        "handoff.md": f"# Handoff\n\n{alias}\n",
    }.items():
        (root / stage).write_text(content, encoding="utf-8")
    (project / f".verifysignal/skills/{alias}.browser.md").write_text(
        f"""# {alias}

```yaml
schemaVersion: qa-skill/v1
skill:
  id: skill.{alias}
  version: 1.0.0
  kind: browser
  name: {alias}
browser:
  steps:
    - id: open
      action: navigate
      value: "{{{{parameters.baseUrl}}}}"
  assertions: []
```
""",
        encoding="utf-8",
    )
