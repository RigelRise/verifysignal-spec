from __future__ import annotations

from verifysignal_spec.workspace.repository import init_workspace, load_use_case
from verifysignal_spec.workflows.engine import create_workflow_run, generate_tasks, implement_artifacts, plan_artifacts, validate_stage
from verifysignal_spec.workflows.models import ArtifactPlan
from verifysignal_spec.workflows.repository import save_artifact_plan
from verifysignal_spec.workflows.stage_persistence import persist_stage
from verifysignal_spec.workflows.transitions import transition_workflow
from tests.fixtures.workflows.main_skill_run_coverage import create_main_skill_coverage_workspace
from tests.helpers import FAKE_CORE


def test_implement_creates_draft_artifacts(tmp_path) -> None:
    init_workspace(tmp_path, core_cmd=str(FAKE_CORE))
    create_workflow_run(tmp_path, "Validate login.", alias="login", integration="codex")
    plan_artifacts(tmp_path, "login")
    generate_tasks(tmp_path, "login")
    result = implement_artifacts(tmp_path, "login")
    assert result["status"] == "draft"
    assert (tmp_path / ".verifysignal" / "run-requests" / "login.yaml").exists()
    assert load_use_case(tmp_path, "login").status == "draft"


def test_implemented_browser_artifacts_require_runtime_readiness_validation(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("VERIFYSIGNAL_CORE_CMD", str(FAKE_CORE))
    create_main_skill_coverage_workspace(tmp_path, core_cmd=str(FAKE_CORE))
    create_workflow_run(
        tmp_path,
        "Validate a public profile page.",
        alias="profile-view-unauth",
        integration="codex",
    )
    _advance_to_implement(tmp_path, "profile-view-unauth")
    transition_workflow(
        tmp_path,
        "profile-view-unauth",
        stage="implement",
        outcome="completed",
    )

    result = validate_stage(tmp_path, "profile-view-unauth", core_cmd=str(FAKE_CORE))

    assert result["status"] == "passed"
    assert result["runtimeReadiness"]["status"] == "passed"
    assert result["runtimeReadiness"]["fullBrowserFlowExecuted"] is False


def test_write_implementation_requires_resource_identity(tmp_path) -> None:
    init_workspace(tmp_path, core_cmd=str(FAKE_CORE))
    create_workflow_run(tmp_path, "Create resource.", alias="create-resource", integration="codex")
    _save_create_resource_plan(tmp_path)
    _advance_to_implement(tmp_path, "create-resource")

    result = persist_stage(tmp_path, "implement", alias="create-resource", payload=_write_implement_payload(include_identity=False, generated_identity=False))

    assert result["status"] == "invalid"
    assert result["blockers"][0]["code"] == "payload.invalid"
    assert "resourceIdentity" in result["blockers"][0]["message"]


def test_write_implementation_persists_resource_identity(tmp_path) -> None:
    init_workspace(tmp_path, core_cmd=str(FAKE_CORE))
    create_workflow_run(tmp_path, "Create resource.", alias="create-resource", integration="codex")
    _save_create_resource_plan(tmp_path)
    _advance_to_implement(tmp_path, "create-resource")

    result = persist_stage(tmp_path, "implement", alias="create-resource", payload=_write_implement_payload(include_identity=True))

    assert result["status"] == "persisted"
    record = load_use_case(tmp_path, "create-resource")
    assert record.resourceIdentity["identityInput"] == "resourceName"
    assert "resource-identity" in record.artifactCapabilities["stamp"]["capabilities"]


def test_write_implementation_infers_high_confidence_generated_identity(tmp_path) -> None:
    init_workspace(tmp_path, core_cmd=str(FAKE_CORE))
    create_workflow_run(tmp_path, "Create resource.", alias="create-resource", integration="codex")
    _save_create_resource_plan(tmp_path)
    _advance_to_implement(tmp_path, "create-resource")

    result = persist_stage(tmp_path, "implement", alias="create-resource", payload=_write_implement_payload(include_identity=False))

    assert result["status"] == "persisted"
    identity = load_use_case(tmp_path, "create-resource").resourceIdentity
    assert identity["identityStrategy"] == "generated-input"
    assert identity["identityInput"] == "resourceName"
    assert identity["confidence"] == "high"


def test_repersist_implement_preserves_parameter_values(tmp_path) -> None:
    # Regression (dogfood Bug 2): re-persisting implement with runtimeInputs that omit `value`
    # (persistValue:false-style) must NOT zero previously author-supplied parameter values.
    init_workspace(tmp_path, core_cmd=str(FAKE_CORE))
    create_workflow_run(tmp_path, "Validate labelled page.", alias="labelled-page", integration="codex")
    save_artifact_plan(
        tmp_path,
        ArtifactPlan(
            useCaseAlias="labelled-page",
            runRequest=".verifysignal/run-requests/labelled-page.yaml",
            mainSkill=".verifysignal/skills/labelled-page.browser.md",
            runtimeInputs=[
                {"name": "baseUrl", "source": "default", "value": "https://example.test"},
                {"name": "label", "source": "prompt"},
            ],
            validationGates=[{"id": "page-visible", "required": True}],
        ),
    )
    _advance_to_implement(tmp_path, "labelled-page")

    def _payload(with_value: bool) -> dict:
        label_input = {"name": "label", "source": "prompt", "required": True}
        if with_value:
            label_input["value"] = "Hello Label"
        return {
            "runRequest": {"path": ".verifysignal/run-requests/labelled-page.yaml"},
            "runtimeInputs": [
                {"name": "baseUrl", "source": "default", "value": "https://example.test"},
                label_input,
            ],
            "skills": [
                {
                    "path": ".verifysignal/skills/labelled-page.browser.md",
                    "kind": "skill",
                    "intent": {
                        "browser": {
                            "targets": {"page": {"css": "body"}},
                            "steps": [{"id": "open", "action": "navigate", "value": "{{parameters.baseUrl}}"}],
                            "assertions": [{"id": "page-visible", "kind": "visible", "target": "page", "gateId": "page-visible"}],
                        }
                    },
                }
            ],
            "sideEffects": {"class": "none"},
        }

    first = persist_stage(tmp_path, "implement", alias="labelled-page", payload=_payload(with_value=True))
    assert first["status"] == "persisted", first
    run_request_path = tmp_path / ".verifysignal" / "run-requests" / "labelled-page.yaml"
    assert "Hello Label" in run_request_path.read_text()

    create_workflow_run(
        tmp_path,
        "Validate labelled page.",
        alias="labelled-page",
        integration="codex",
    )
    _advance_to_implement(tmp_path, "labelled-page")
    second = persist_stage(tmp_path, "implement", alias="labelled-page", payload=_payload(with_value=False))
    assert second["status"] == "persisted", second
    assert "Hello Label" in run_request_path.read_text()


def _save_create_resource_plan(tmp_path) -> None:
    save_artifact_plan(
        tmp_path,
        ArtifactPlan(
            useCaseAlias="create-resource",
            runRequest=".verifysignal/run-requests/create-resource.yaml",
            mainSkill=".verifysignal/skills/create-resource.browser.md",
            runtimeInputs=[
                {"name": "baseUrl", "source": "default", "value": "https://example.test"},
                {"name": "resourceName", "source": "generated", "template": "resource-{{run.shortId}}", "refreshOnRerunAfterCommit": True},
            ],
            validationGates=[{"id": "created-page-visible", "required": True}],
        ),
    )


def _advance_to_implement(project, alias: str) -> None:
    for stage in ["specify", "clarify", "plan", "tasks"]:
        transition_workflow(
            project,
            alias,
            stage=stage,
            outcome="completed",
        )


def _write_implement_payload(*, include_identity: bool, generated_identity: bool = True) -> dict:
    runtime_inputs = [{"name": "baseUrl", "source": "default", "value": "https://example.test"}]
    if generated_identity:
        runtime_inputs.append({"name": "resourceName", "source": "generated", "template": "resource-{{run.shortId}}", "refreshOnRerunAfterCommit": True})
    payload = {
        "runRequest": {"path": ".verifysignal/run-requests/create-resource.yaml"},
        "runtimeInputs": runtime_inputs,
        "skills": [
            {
                "path": ".verifysignal/skills/create-resource.browser.md",
                "kind": "skill",
                "intent": {
                    "browser": {
                        "targets": {"page": {"css": "body"}},
                        "steps": [{"id": "open", "action": "navigate", "value": "{{parameters.baseUrl}}"}],
                        "assertions": [{"id": "page-visible", "kind": "visible", "target": "page", "gateId": "created-page-visible"}],
                    }
                },
            }
        ],
        "sideEffects": {
            "class": "write",
            "commitStepId": "submit-resource",
            "allowed": [{"id": "create-resource", "kind": "network", "methods": ["POST"], "urlContains": "/resources"}],
        },
        "sideEffectLifecycle": {"cleanupPolicy": "manual", "cleanupRequired": True, "instructions": "Delete the test resource manually."},
        "rerunPolicy": {"afterCommit": "allowed-with-new-inputs", "refreshRuntimeInputs": ["resourceName"]},
    }
    if include_identity:
        payload["resourceIdentity"] = {
            "resourceType": "resource",
            "identityStrategy": "generated-input",
            "identityInput": "resourceName",
            "collisionPolicy": "avoid",
            "targetScope": "https://example.test",
            "confidence": "confirmed",
        }
    return payload
