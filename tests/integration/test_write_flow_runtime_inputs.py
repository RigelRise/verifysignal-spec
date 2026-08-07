from __future__ import annotations

import json
from pathlib import Path

from verifysignal_spec.commands import run as run_command
from verifysignal_spec.workspace.models import ArtifactReference, RuntimeInputRequirement, UseCaseRecord
from verifysignal_spec.workspace.repository import init_workspace, save_use_case
from tests.fixtures.workflows.entitlement_preflight_recovery import save_protected_ready_snapshot
from tests.integration.test_workflow_run import _write_minimal_artifacts


def test_generated_input_is_resolved_for_core_without_rewriting_authored_request(tmp_path, monkeypatch) -> None:
    from tests.helpers import FAKE_CORE

    monkeypatch.setenv("VERIFYSIGNAL_CORE_CMD", str(FAKE_CORE))
    init_workspace(tmp_path, core_cmd=str(FAKE_CORE))
    authored = _write_minimal_artifacts(tmp_path, "create-resource", parameters={"baseUrl": "https://example.test"})
    original = authored.read_text(encoding="utf-8")
    save_use_case(
        tmp_path,
        UseCaseRecord(
            alias="create-resource",
            title="Create Resource",
            description="Create resource.",
            runRequest=ArtifactReference(path=".verifysignal/run-requests/create-resource.yaml", kind="run-request", id="request.create-resource", version="1.0.0"),
            mainSkill=ArtifactReference(path=".verifysignal/skills/create-resource.browser.md", kind="skill", id="skill.create-resource", version="1.0.0"),
            skills=[ArtifactReference(path=".verifysignal/skills/create-resource.browser.md", kind="skill", id="skill.create-resource", version="1.0.0")],
            runtimeInputs=[
                RuntimeInputRequirement(name="baseUrl", source="default", value="https://example.test"),
                RuntimeInputRequirement(name="resourceName", source="generated", template="VerifySignal {{run.shortId}}", refreshOnRerunAfterCommit=True),
            ],
            sideEffects={"class": "none"},
        ),
    )
    save_protected_ready_snapshot(tmp_path, "create-resource")

    result = run_command.run(tmp_path, "create-resource", interactive=False, core_cmd=str(FAKE_CORE))

    assert result["status"] == "passed"
    assert authored.read_text(encoding="utf-8") == original
    prepared_path = Path(result["core"]["data"]["args"][1])
    prepared = json.loads(prepared_path.read_text(encoding="utf-8"))
    assert prepared["parameters"]["resourceName"].startswith("VerifySignal ")
