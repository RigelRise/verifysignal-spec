from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from verifysignal_spec.workspace.models import ArtifactReference, RuntimeInputRequirement, UseCaseRecord
from verifysignal_spec.workspace.repository import init_workspace, save_use_case
from tests.fixtures.workflows.entitlement_preflight_recovery import save_protected_ready_snapshot


def write_minimal_artifacts(project: Path, alias: str, *, parameters: dict[str, str] | None = None) -> Path:
    (project / ".verifysignal/run-requests").mkdir(parents=True, exist_ok=True)
    (project / ".verifysignal/skills").mkdir(parents=True, exist_ok=True)
    request_path = project / f".verifysignal/run-requests/{alias}.yaml"
    request_path.write_text(
        json.dumps(
            {
                "schemaVersion": "qa-run-request/v1",
                "request": {"id": f"request.{alias}", "name": alias.replace("-", " ").title()},
                "target": "browser",
                "validationScope": "feature-level",
                "skills": [{"id": f"skill.{alias}", "version": "1.0.0"}],
                "parameters": parameters or {"baseUrl": "https://example.test"},
            }
        ),
        encoding="utf-8",
    )
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
    return request_path


def write_use_case_record(
    project: Path,
    *,
    alias: str = "add-collaboration-project",
    rerun_policy: dict[str, Any] | None = None,
    last_run: dict[str, Any] | None = None,
    runtime_inputs: list[RuntimeInputRequirement] | None = None,
    resource_identity: dict[str, Any] | None = None,
    protected_ready: bool = False,
) -> UseCaseRecord:
    init_workspace(project, core_cmd="verifysignal-core")
    write_minimal_artifacts(project, alias)
    record = UseCaseRecord(
        alias=alias,
        title="Add Collaboration Project",
        description="Publish a collaboration project.",
        targetSurface="/",
        runRequest=ArtifactReference(path=f".verifysignal/run-requests/{alias}.yaml", kind="run-request", id=f"request.{alias}", version="1.0.0"),
        mainSkill=ArtifactReference(path=f".verifysignal/skills/{alias}.browser.md", kind="skill", id=f"skill.{alias}", version="1.0.0"),
        skills=[ArtifactReference(path=f".verifysignal/skills/{alias}.browser.md", kind="skill", id=f"skill.{alias}", version="1.0.0")],
        runtimeInputs=runtime_inputs
        or [
            RuntimeInputRequirement(name="baseUrl", source="default", value="https://example.test"),
            RuntimeInputRequirement(
                name="projectTitle",
                source="generated",
                value="VerifySignal collab seed",
                refreshOnRerunAfterCommit=True,
            ),
        ],
        sideEffects={
            "class": "write",
            "commitStepId": "confirm-publish-dialog",
            "allowed": [{"id": "create-project", "kind": "network", "methods": ["POST"], "urlContains": "/graphql"}],
        },
        sideEffectLifecycle={
            "cleanupPolicy": "manual",
            "cleanupRequired": True,
            "trackingIntent": "manual-db-cleanup",
            "instructions": "Remove the created test resource manually.",
        },
        artifactCapabilities={
            "capabilities": ["explicit-confirmation", "side-effect-lifecycle", "write-activity-interpretation"]
        },
        rerunPolicy=rerun_policy,
        lastRun=last_run,
    )
    if resource_identity:
        record.resourceIdentity = resource_identity  # type: ignore[attr-defined]
    save_use_case(project, record)
    if protected_ready:
        save_protected_ready_snapshot(project, alias, side_effect_class="write")
    return record


def committed_last_run(*, value: str = "VerifySignal collab seed", run_id: str = "previous-run") -> dict[str, Any]:
    return {
        "runId": run_id,
        "status": "passed",
        "startedAt": "2026-08-04T00:00:00.000000001Z",
        "completedAt": "2026-08-04T00:00:00.000000002Z",
        "coreStatus": "passed",
        "coverageStatus": "complete",
        "resolvedRuntimeInputs": [
            {
                "name": "projectTitle",
                "value": value,
                "source": "generated",
                "runId": run_id,
                "targetScope": "https://example.test",
                "useCaseAlias": "add-collaboration-project",
                "refreshed": True,
                "committed": True,
            }
        ],
        "postCommitInterpretation": {
            "postCommit": True,
            "sideEffectMayExist": True,
            "sideEffectStatus": "committed-confirmed",
            "failurePhase": "post-commit",
            "rerunRisk": "safe-with-new-inputs",
        },
    }


def discarded_last_run(*, value: str = "VerifySignal collab seed", run_id: str = "discarded-run") -> dict[str, Any]:
    payload = committed_last_run(value=value, run_id=run_id)
    payload["status"] = "failed"
    payload["coreStatus"] = "failed"
    payload["coverageStatus"] = "not-run"
    payload["resolvedRuntimeInputs"][0]["committed"] = False
    payload["resolvedRuntimeInputs"][0]["status"] = "discarded"
    payload["postCommitInterpretation"] = {
        "postCommit": False,
        "sideEffectMayExist": False,
        "sideEffectStatus": "not-started",
        "failurePhase": "pre-commit",
        "rerunRisk": "safe",
    }
    return payload


def assert_no_secret_values(data: Any) -> None:
    serialized = json.dumps(data, sort_keys=True)
    assert "APP_TEST_PASSWORD" not in serialized
    assert "password-value" not in serialized
    assert "Bearer " not in serialized
