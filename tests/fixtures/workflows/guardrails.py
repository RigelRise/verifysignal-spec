from __future__ import annotations

from pathlib import Path
from typing import Any

from verifysignal_spec.workspace import layout
from verifysignal_spec.workspace.models import ArtifactReference, UseCaseRecord
from verifysignal_spec.workspace.repository import init_workspace, load_registry, save_document, save_registry, save_use_case


def create_ready_use_case_workspace(
    project: Path,
    alias: str = "login",
    *,
    core_cmd: str | None = None,
) -> Path:
    init_workspace(project, core_cmd=core_cmd)
    run_request = f"{layout.WORKSPACE_DIR}/{layout.RUN_REQUESTS_DIR}/{alias}.yaml"
    skill = f"{layout.WORKSPACE_DIR}/{layout.SKILLS_DIR}/{alias}.browser.md"
    record = UseCaseRecord(
        alias=alias,
        title="Login",
        description="Validate login.",
        status="ready",
        runRequest=ArtifactReference(path=run_request, kind="run-request", generated=True),
        mainSkill=ArtifactReference(path=skill, kind="skill", generated=True),
        skills=[ArtifactReference(path=skill, kind="skill", generated=True)],
    )
    save_use_case(project, record)
    (project / run_request).parent.mkdir(parents=True, exist_ok=True)
    (project / run_request).write_text('{"schemaVersion":"qa-run-request/v1"}\n', encoding="utf-8")
    (project / skill).write_text("---\nschemaVersion: qa-skill/v1\n---\n# Login\n", encoding="utf-8")
    return project


def create_registry_missing_record_path(project: Path, alias: str = "login") -> Path:
    init_workspace(project)
    registry = load_registry(project)
    registry["useCases"] = [{"alias": alias, "title": "Login", "status": "draft"}]
    save_registry(project, registry)
    return project


def stage_payload(stage: str, alias: str = "login", **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "stage": stage,
        "alias": alias,
        "requestedAt": "2026-05-25T00:00:00Z",
        "payload": {},
    }
    payload.update(overrides)
    return payload


def write_payload(project: Path, name: str, payload: dict[str, Any]) -> Path:
    path = project / f"{name}.json"
    save_document(path, payload)
    return path
