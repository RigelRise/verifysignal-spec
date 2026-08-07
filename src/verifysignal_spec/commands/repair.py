from __future__ import annotations

from pathlib import Path
from typing import Any

from verifysignal_spec.core.adapter import CoreAdapter
from verifysignal_spec.integrations.manifests import sha256_text
from verifysignal_spec.workspace.textio import write_text_lf
from verifysignal_spec.runtime.entitlement import api_base_url_for_runtime, valid_receipt_path
from verifysignal_spec.runtime.resolver import ensure_core_runtime
from verifysignal_spec.workflows.first_run import advance_guided_first_run_state
from verifysignal_spec.workflows.models import RepairConfirmation, RepairFeedback, SafeRepairApplication
from verifysignal_spec.workflows.repair_recommendations import (
    MUTABLE_SAFE_CATEGORIES,
    classify_repair_findings,
    proposals_from_contradictions,
)
from verifysignal_spec.workflows.repository import (
    load_active_workflow_run,
    load_golden_path_state,
    save_golden_path_state,
)
from verifysignal_spec.workflows.stage_cards import repair_stage_card
from verifysignal_spec.workflows.transitions import transition_workflow
from verifysignal_spec.workspace import layout
from verifysignal_spec.workspace.models import RepairSession
from verifysignal_spec.workspace.repository import load_use_case, now_iso, save_document, save_use_case


def run(project: Path, alias: str, from_report: str | None = None, approve: bool = False, core_cmd: str | None = None, api_base_url: str | None = None) -> dict[str, Any]:
    record = load_use_case(project, alias)
    source = "report-inspection" if from_report else "authoring-validation"
    findings: list[dict[str, Any]]
    if from_report:
        managed_runtime = ensure_core_runtime(project, explicit_core_cmd=core_cmd, api_base_url=api_base_url, context="repair")
        if managed_runtime.status != "ready":
            payload = _runtime_setup_blocked_payload(managed_runtime)
            return {"alias": alias, **payload, "repair": payload}
        entitlement_api_base_url = api_base_url_for_runtime(managed_runtime, api_base_url)
        result = CoreAdapter(
            executable=managed_runtime.runtimeCommand,
            cwd=project,
        ).inspect_report(
            Path(from_report),
            entitlement_receipt=valid_receipt_path(entitlement_api_base_url),
            entitlement_api_base_url=entitlement_api_base_url,
        )
        findings = list(result.get("data", {}).get("findings", []))
    else:
        findings = list(
            record.validation.get("data", {}).get(
                "findings",
                record.validation.get("findings", record.validation.get("core", {}).get("data", {}).get("findings", [])),
            )
        )
    if not from_report and not findings:
        managed_runtime = ensure_core_runtime(project, explicit_core_cmd=core_cmd, api_base_url=api_base_url, context="repair")
        if managed_runtime.status != "ready":
            payload = _runtime_setup_blocked_payload(managed_runtime)
            return {"alias": alias, **payload, "repair": payload}

    contradictions = []
    if record.lastRun and isinstance(record.lastRun.get("runtimeContradictions"), list):
        contradictions = list(record.lastRun.get("runtimeContradictions") or [])
        findings.extend(
            {
                "severity": "warning",
                "code": "runtime-contradiction",
                "artifact": ".verifysignal/workflows",
                "path": item.get("gateId"),
                "message": item.get("observedEvidence", "Runtime evidence contradicted the planned gate."),
                "suggestedFix": item.get("recommendation", "replan"),
            }
            for item in contradictions
        )
    proposals = [
        {
            "artifact": finding.get("artifact") or (record.runRequest.path if record.runRequest else f".verifysignal/use-cases/{alias}.yaml"),
            "field": finding.get("path"),
            "reason": finding.get("message", "Core finding requires review."),
            "expectedEffect": finding.get("suggestedFix", "Update the artifact and revalidate."),
        }
        for finding in findings
    ]
    if contradictions:
        from verifysignal_spec.workflows.models import RuntimeContradiction

        proposals.extend(
            proposals_from_contradictions(
                [
                    RuntimeContradiction(
                        id=str(item.get("id", "")),
                        gateId=str(item.get("gateId", "")),
                        observedEvidence=str(item.get("observedEvidence", "")),
                        expectedEvidence=str(item.get("expectedEvidence", "")),
                        recommendation=item.get("recommendation", "replan"),
                        sourceRunId=item.get("sourceRunId"),
                    )
                    for item in contradictions
                ]
            )
        )
    proposals = proposals or [
        {
            "artifact": record.runRequest.path if record.runRequest else f".verifysignal/use-cases/{alias}.yaml",
            "field": None,
            "reason": "No deterministic finding was available.",
            "expectedEffect": "Review the use case and run validation again.",
        }
    ]
    recommendations = classify_repair_findings(findings)
    if not recommendations and proposals:
        recommendations = classify_repair_findings(
            [
                {
                    "code": proposal.get("field") or "manual-review",
                    "message": f"{proposal.get('reason', '')} {proposal.get('expectedEffect', '')}",
                    "artifact": proposal.get("artifact"),
                    "path": proposal.get("field"),
                }
                for proposal in proposals
            ]
        )
    auto_applicable = [item for item in recommendations if item.category == "safe-artifact-repair" and not item.requiresUserDecision]
    blocked = [
        item
        for item in recommendations
        if item.category in {"clarification-required", "replan-required", "unsupported"}
        or item.requiresUserDecision
    ]
    # Attempt the actual artifact mutation for each auto-applicable safe repair. A repair is
    # reported as `applied` ONLY when a deterministic re-render produced a verified byte
    # change (proven by before/after SHA-256); otherwise it is `proposed` — the described
    # fix must still be applied by the caller. This closes the P0 where repair claimed
    # `applied` without ever changing an artifact.
    # The mutation actually writes the artifact, so it requires explicit --approve. Without it an
    # auto-applicable safe repair stays `proposed` (exit 4): the caller must approve before repair
    # rewrites a run-request/skill on disk. (P0: an un-approved repair silently rewrote artifacts.)
    mutations: dict[str, dict[str, Any]] = {}
    if not blocked and approve:
        for item in auto_applicable:
            mutation = _apply_safe_artifact_repair(project, record, item)
            if mutation:
                mutations[item.id] = mutation
    any_applied = bool(mutations)
    revalidation = _revalidate_after_mutation(project, alias, core_cmd, api_base_url) if any_applied else None
    applied_validation_status = revalidation.get("status", "not-run") if revalidation else "not-run"
    # Success is a POSITIVE predicate: only a revalidation that actually PASSED proves the mutation
    # closed the gap. Every other outcome is non-success BY CONSTRUCTION — including "not-run", which
    # is what _revalidate_after_mutation returns when it swallows a CRASH. The previous
    # `== "failed"` check enumerated failure instead, so a crash (and any future status) fell through
    # to a clean `applied`/remainingGaps:[]/exit-0 — the same fail-open class it was meant to seal.
    revalidation_succeeded = bool(revalidation and revalidation.get("status") == "passed")
    revalidation_failed = bool(revalidation and revalidation.get("status") == "failed")
    applications = [
        SafeRepairApplication(
            recommendationId=item.id,
            applied=item.id in mutations,
            changedArtifacts=mutations[item.id]["changed"] if item.id in mutations else [],
            validationStatus=applied_validation_status if item.id in mutations else "not-run",
            beforeSha256=mutations[item.id]["before"] if item.id in mutations else None,
            afterSha256=mutations[item.id]["after"] if item.id in mutations else None,
            remainingGaps=[] if (item.id in mutations and revalidation_succeeded) else [item.id],
        ).to_dict()
        for item in recommendations
        if item.category == "safe-artifact-repair"
    ]
    repair_confirmations = [
        RepairConfirmation(
            id=f"confirm-{item.id}",
            findingId=(item.sourceFeedback[0] if item.sourceFeedback else item.id),
            category=item.runtimeCategory or item.safeCategory or item.category,
            confirmationSource="explicit-command",
            confirmationTextSummary="Repair was explicitly approved, but the change still requires scoped artifact work and revalidation.",
            approvedScope=item.affectedArtifacts or [item.action],
            affectedArtifacts=item.affectedArtifacts,
            revalidationRequired=True,
            status="pending",
        ).to_dict()
        for item in recommendations
        if approve and item.requiresUserDecision
    ]
    repair_feedback = [
        RepairFeedback(
            repairId=item.id,
            category=item.runtimeCategory or item.safeCategory or item.category,
            autonomy=item.autonomy,
            safeMechanical=item.safeMechanical,
            before=item.summary or "Runtime feedback identified a repairable issue.",
            after=item.action if item.autonomy == "auto-applied" else None,
            intentPreserved=item.intentPreserved,
            confirmationRequired=item.requiresUserDecision,
            revalidationStatus="not-run",
            rerunStatus="not-run",
            nextAction=f"Run `verifysignal validate {alias} --runtime-readiness --json`, then rerun.",
        ).to_dict()
        for item in recommendations
    ]
    stage_cards = [
        repair_stage_card(
            category=item.runtimeCategory or item.safeCategory or item.category,
            autonomy=item.autonomy,
            before=item.summary or "Runtime feedback identified a repairable issue.",
            after=item.action if item.autonomy == "auto-applied" else item.blockedReason or item.action,
            next_action=f"Run `verifysignal validate {alias} --runtime-readiness --json`, then rerun.",
        )
        for item in recommendations
        # `propose-only` still gets a card (the fix is real and worth showing) — but the card's own
        # summary renders "<category> repair is propose-only", so it describes rather than claims done.
        if item.autonomy in {"auto-applied", "propose-only"}
    ]
    session = RepairSession(
        repairId=f"{alias}-{now_iso().replace(':', '').replace('-', '')}",
        useCaseAlias=alias,
        source=source,
        findings=findings,
        proposals=proposals,
        recommendations=[item.to_dict() for item in recommendations],
        repairConfirmations=repair_confirmations,
        applications=applications,
        repairFeedback=repair_feedback,
        stageCards=stage_cards,
        approvalStatus=(
            "revalidation-failed"
            if any_applied and revalidation_failed
            # Applied, but revalidation could not run (crash → "not-run") — we cannot claim the gap
            # closed, so report it honestly rather than as a clean `applied`.
            else "revalidation-unavailable"
            if any_applied and not revalidation_succeeded
            else "applied"
            if any_applied
            else "conflict"
            if approve and blocked
            else "proposed"
            if auto_applicable and not blocked
            else "approved"
            if approve
            else "pending"
        ),
        nextAction=f"Run `verifysignal validate {alias} --runtime-readiness --json`, then rerun.",
    )
    if any_applied:
        session.appliedAt = now_iso()
        session.revalidation = revalidation
        session.readyForRun = False
    elif auto_applicable and not blocked:
        session.readyForRun = False
        session.revalidation = {
            "status": "not-run",
            "message": "Safe mechanical repair could not be applied deterministically; apply the described change, then revalidate and rerun.",
        }
    elif blocked:
        session.readyForRun = False
        session.revalidation = {
            "status": "not-run",
            "message": "Repair changes approved intent or is unsupported; return to clarification or planning.",
        }
    record.repair = {"repairId": session.repairId, "approvalStatus": session.approvalStatus}
    save_use_case(project, record)
    repair_path = layout.repair_path(project, session.repairId)
    save_document(repair_path, session.to_dict())
    _update_first_run_repair_state(project, alias, repair_feedback, session.approvalStatus)
    active_run = load_active_workflow_run(project, alias)
    if any_applied and active_run is not None and active_run.currentStage == "repair":
        transition_workflow(
            project,
            alias,
            stage="repair",
            outcome="completed",
            document_path=layout.to_project_relative(project, repair_path),
            handoff_summary=(
                "A scoped repair was persisted; protected validation is "
                "required before another browser run."
            ),
        )
    return {"alias": alias, "repair": session.to_dict()}


def _runtime_setup_blocked_payload(managed_runtime: Any) -> dict[str, Any]:
    runtime_payload = managed_runtime.to_dict()
    is_core_missing = any(blocker.get("code") == "core.missing" for blocker in runtime_payload.get("blockers", []))
    return {
        "status": "blocked",
        "findings": [],
        "applications": [],
        "rootCauseCategory": "environment-setup",
        "message": "No deterministic artifact finding is available; Core setup is required." if is_core_missing else "No deterministic artifact finding is available; VerifySignal runtime setup is required.",
        "managedRuntimeReadiness": runtime_payload,
        "blockers": runtime_payload.get("blockers", []),
        "nextCommand": managed_runtime.nextAction,
    }


def _update_first_run_repair_state(project: Path, alias: str, repair_feedback: list[dict[str, Any]], approval_status: str) -> None:
    state = load_golden_path_state(project)
    if state.get("selectedCandidate") != alias:
        return
    state["repairFeedback"] = repair_feedback
    if approval_status == "applied":
        state["firstRunStatus"] = "repairing"
        state["stage"] = "repairing"
        state["status"] = "repairing"
        state["resumeCommand"] = f"verifysignal validate {alias} --runtime-readiness --json"
    save_golden_path_state(project, state)
    if approval_status == "applied":
        advance_guided_first_run_state(
            project,
            alias,
            stage="repairing",
            first_run_status="repairing",
            resume_command=f"verifysignal validate {alias} --runtime-readiness --json",
            summary="Safe repair was applied; revalidation and rerun are required before reporting success.",
            status_marker="[REPAIR]",
        )


def _apply_safe_artifact_repair(project: Path, record: Any, recommendation: Any) -> dict[str, Any] | None:
    """Deterministically apply a safe-artifact-repair, returning the before/after SHA-256 of
    every artifact whose bytes changed, or None when no verified mutation was produced (the fix
    is then reported as ``proposed``).

    ``main-skill-ordering`` is a run-request *ordering* fix: the planned main skill must lead the
    executable skill list. The fix SURGICALLY reorders only the on-disk run-request's ``skills``
    array, preserving the exact skill set and every other authored field (``parameters`` values,
    ``mainSkill``, ``target``, ``validationScope``, ``schemaVersion``, ...). It does NOT
    regenerate the run-request from the record — the ``UseCaseRecord`` does not hold authored
    parameter VALUES (e.g. ``baseUrl``), so a from-scratch re-render would wipe them (the same
    data-loss class this repair must avoid). Skill ``.browser.md`` bodies are likewise never
    rewritten (they carry authored ``targets``/``steps``/``assertions``/``gateId`` the record
    does not hold). ``selector-ambiguity``/``wait-strategy`` need live page/DOM context and
    ``run-profile-defaults`` does not render into an artifact, so those return None.
    """
    # Dispatch off the SAME set that drives the `auto-applied` label (see MUTABLE_SAFE_CATEGORIES), so a
    # category can never be labeled auto-applied without a real mutator here, and vice versa.
    if recommendation.safeCategory not in MUTABLE_SAFE_CATEGORIES:
        return None
    if not record.mainSkill or not (record.runRequest and record.runRequest.generated):
        return None
    path = record.runRequest.path
    run_path = layout.project_relative_path(project, path)
    if not run_path.exists():
        return None
    before_text = run_path.read_text(encoding="utf-8")
    # Parse as JSON — the canonical generated run-request format. A run-request that is not JSON
    # (e.g. a hand-authored YAML file) is left untouched (reported `proposed`) rather than risking
    # a lossy or crashing round-trip. Parsing as JSON also guarantees only JSON-serializable
    # types, so the re-serialization below can never raise on a YAML-native scalar (e.g. a date).
    import json

    try:
        parsed = json.loads(before_text)
    except (ValueError, TypeError):
        return None
    if not isinstance(parsed, dict) or not isinstance(parsed.get("skills"), list):
        return None
    main_id = record.mainSkill.id
    if not main_id:
        return None  # No stable identity to reorder against — an id-less ref must not match None.
    skills = parsed["skills"]
    main_refs = [ref for ref in skills if isinstance(ref, dict) and ref.get("id") == main_id]
    if not main_refs:
        # The main skill is not an executable participant here; there is no safe, lossless
        # ordering edit to make (removing/adding executable skills is not mechanical). Propose.
        return None
    others = [ref for ref in skills if not (isinstance(ref, dict) and ref.get("id") == main_id)]
    reordered = [*main_refs, *others]
    if reordered == skills:
        return None  # Already main-first — nothing to reorder.
    parsed["skills"] = reordered
    after_text = json.dumps(parsed, indent=2, ensure_ascii=False) + "\n"
    if after_text == before_text:
        return None
    before = sha256_text(before_text)
    # LF: `after` is hashed from the string, so the file has to carry those exact bytes or the
    # reported hash does not describe the file it names.
    write_text_lf(run_path, after_text)
    after = sha256_text(after_text)
    return {"changed": [path], "before": {path: before}, "after": {path: after}}


def _revalidate_after_mutation(project: Path, alias: str, core_cmd: str | None, api_base_url: str | None) -> dict[str, str]:
    from verifysignal_spec.commands import validate as validate_command

    try:
        result = validate_command.run(project, alias, core_cmd=core_cmd, api_base_url=api_base_url)
    except Exception as error:  # noqa: BLE001 - revalidation must never crash repair reporting
        return {"status": "not-run", "message": f"Revalidation could not run after the applied mutation: {error}."}
    core_status = str(result.get("status") or "")
    status = (
        "passed"
        if core_status in {"ready", "passed"}
        else "failed"
        if core_status in {"blocked", "failed", "error"}
        else "not-run"
    )
    return {
        "status": status,
        "coreStatus": core_status or "unknown",
        "message": "Revalidation ran after the applied artifact mutation; rerun is still required before reporting success.",
    }
