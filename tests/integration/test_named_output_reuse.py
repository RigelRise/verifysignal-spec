from __future__ import annotations

from verifysignal_spec.workspace.repository import publish_named_outputs, resolve_named_output


def test_later_use_case_resolves_published_named_output(tmp_path) -> None:
    publish_named_outputs(
        tmp_path,
        [
            {
                "name": "createdProjectUrl",
                "value": "https://app.example.test/project/verifysignal-collab-abc123",
                "sourceBinding": "finalUrl",
                "publishedByRunId": "run-1",
                "useCaseAlias": "add-collaboration-project",
                "targetScope": "https://app.example.test",
                "resourceType": "collaboration-project",
            }
        ],
    )

    output = resolve_named_output(tmp_path, "createdProjectUrl", use_case_alias="add-collaboration-project", target_scope="https://app.example.test")

    assert output["value"].endswith("/verifysignal-collab-abc123")


def test_run_resolves_named_output_runtime_input_before_core(tmp_path, monkeypatch) -> None:
    import json

    from verifysignal_spec.commands import run as run_command
    from verifysignal_spec.workspace.models import ArtifactReference, RuntimeInputRequirement, UseCaseRecord
    from verifysignal_spec.workspace.repository import init_workspace, save_use_case
    from tests.fixtures.workflows.entitlement_preflight_recovery import save_protected_ready_snapshot
    from tests.helpers import FAKE_CORE

    monkeypatch.setenv("VERIFYSIGNAL_CORE_CMD", str(FAKE_CORE))
    init_workspace(tmp_path, core_cmd=str(FAKE_CORE))
    publish_named_outputs(
        tmp_path,
        [
            {
                "name": "createdProjectUrl",
                "value": "https://app.example.test/project/verifysignal-collab-abc123",
                "sourceBinding": "finalUrl",
                "publishedByRunId": "run-1",
                "useCaseAlias": "add-collaboration-project",
                "targetScope": "https://app.example.test",
                "resourceType": "collaboration-project",
            }
        ],
    )
    (tmp_path / ".verifysignal/run-requests").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".verifysignal/skills").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".verifysignal/run-requests/project-details.yaml").write_text(
        json.dumps(
            {
                "schemaVersion": "qa-run-request/v1",
                "request": {"id": "request.project-details", "name": "Project Details"},
                "target": "browser",
                "validationScope": "feature-level",
                "skills": [{"id": "skill.project-details", "version": "1.0.0"}],
                "parameters": {},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / ".verifysignal/skills/project-details.browser.md").write_text(
        """# Project details

```yaml
schemaVersion: qa-skill/v1
skill:
  id: skill.project-details
  version: 1.0.0
  kind: browser
  name: Project details
browser:
  steps:
    - id: open
      action: navigate
      value: "{{parameters.createdProjectUrl}}"
  assertions: []
```
""",
        encoding="utf-8",
    )
    save_use_case(
        tmp_path,
        UseCaseRecord(
            alias="project-details",
            title="Project Details",
            description="Validate created project details.",
            runRequest=ArtifactReference(path=".verifysignal/run-requests/project-details.yaml", kind="run-request", id="request.project-details", version="1.0.0"),
            mainSkill=ArtifactReference(path=".verifysignal/skills/project-details.browser.md", kind="skill", id="skill.project-details", version="1.0.0"),
            skills=[ArtifactReference(path=".verifysignal/skills/project-details.browser.md", kind="skill", id="skill.project-details", version="1.0.0")],
            runtimeInputs=[RuntimeInputRequirement(name="createdProjectUrl", source="named-output", value="createdProjectUrl")],
            sideEffects={"class": "none"},
        ),
    )
    save_protected_ready_snapshot(tmp_path, "project-details")

    result = run_command.run(tmp_path, "project-details", interactive=False, core_cmd=str(FAKE_CORE))

    assert result["status"] == "passed"
    prepared = list((tmp_path / ".verifysignal/runs/project-details").glob("*.run-request.json"))
    assert prepared
    params = json.loads(prepared[0].read_text(encoding="utf-8"))["parameters"]
    assert params["createdProjectUrl"] == "https://app.example.test/project/verifysignal-collab-abc123"


def test_validate_shows_named_output_availability_without_values(tmp_path, monkeypatch) -> None:
    from verifysignal_spec.commands.validate import run as validate_run
    from verifysignal_spec.workspace.repository import load_use_case, save_use_case
    from tests.fixtures.workflows.write_rerun_identity import write_use_case_record
    from tests.helpers import FAKE_CORE

    monkeypatch.setenv("VERIFYSIGNAL_CORE_CMD", str(FAKE_CORE))
    write_use_case_record(tmp_path, rerun_policy={"afterCommit": "blocked"})
    record = load_use_case(tmp_path, "add-collaboration-project")
    record.runtimeOutputs = [
        {
            "name": "createdProjectUrl",
            "source": "finalUrl",
            "publishAsNamedOutput": True,
            "value": "https://app.example.test/project/secret-test-resource",
        }
    ]
    save_use_case(tmp_path, record)

    result = validate_run(tmp_path, "add-collaboration-project", runtime_readiness=False, core_cmd=str(FAKE_CORE))

    assert result["namedOutputs"] == [{"name": "createdProjectUrl", "source": "finalUrl"}]
    assert "secret-test-resource" not in str(result["namedOutputs"])
