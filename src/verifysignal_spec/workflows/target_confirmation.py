from __future__ import annotations

from pathlib import Path
from typing import Any

from verifysignal_spec.workspace.repository import (
    load_registry,
    load_use_case,
)

from .repository import load_workflow_run


def target_confirmation_blocker(
    project: Path,
    record: Any,
) -> dict[str, Any] | None:
    question = next(
        (
            item
            for item in getattr(record, "authoringQuestions", [])
            if item.id == "browser-target-environment" and item.requiresConfirmation
        ),
        None,
    )
    if not question:
        return None
    workflow = record.workflow if isinstance(record.workflow, dict) else {}
    run_id = workflow.get("lastWorkflowRunId")
    if run_id:
        try:
            confirmation = (
                load_workflow_run(project, str(run_id)).targetEnvironmentConfirmation
                or {}
            )
        except FileNotFoundError:
            confirmation = {}
        if (
            question.status == "answered"
            and confirmation.get("url")
            and confirmation.get("source") in {"direct-user", "explicit-command"}
        ):
            return None
    return {
        "code": "clarification.target-environment-confirmation-required",
        "severity": "blocker",
        "category": "target-environment",
        "message": (
            "Confirm the recommended browser target or provide another target "
            "for this workflow before browser execution."
        ),
        "questionId": question.id,
        "recommendedTarget": (question.suggestedAnswer or {}).get("baseUrl"),
        "recoveryCommand": f"/verifysignal-clarify {record.alias}",
    }


def record_for_run_request(project: Path, run_request: Path) -> Any | None:
    resolved = run_request.resolve()
    for entry in load_registry(project).get("useCases", []):
        alias = entry.get("alias") if isinstance(entry, dict) else None
        if not alias:
            continue
        try:
            record = load_use_case(project, str(alias))
        except FileNotFoundError:
            continue
        reference = getattr(record, "runRequest", None)
        if reference and (project / reference.path).resolve() == resolved:
            return record
    return None
