from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from verifysignal_spec.commands.runtime_inputs import resolve_runtime_inputs
from verifysignal_spec.commands.run_request_preparation import (
    PreparedRunRequestOwnership,
    cleanup_owned_prepared_run_request,
    confirmation_placeholder_blockers,
    prepared_output_dir_is_safe,
    prepare_run_request_document,
    release_prepared_run_request_ownership,
    write_owned_prepared_run_request,
    write_prepared_run_request,
)
from verifysignal_spec.core.adapter import CoreAdapter, core_status
from verifysignal_spec.core.errors import CoreMissingError
from verifysignal_spec.core.executable_contract import project_core_contract
from verifysignal_spec.core.outcomes import normalize_core_outcome
from verifysignal_spec.runtime.entitlement import api_base_url_for_runtime, valid_receipt_path
from verifysignal_spec.runtime.env_file import (
    EnvironmentFileError,
    declared_environment_keys,
    git_exposure_warnings,
    load_environment_file,
    resolve_environment_file_path,
)
from verifysignal_spec.runtime.resolver import ensure_core_runtime
from verifysignal_spec.runtime.telemetry import ping_outcome, send_usage_ping
from verifysignal_spec.workflows.browser_authoring import resolve_effective_profile_settings
from verifysignal_spec.workflows.evidence import extract_core_runtime_evidence, normalize_planned_gates
from verifysignal_spec.workflows.first_run import classify_first_run_status, golden_path_state, update_golden_path_run_state
from verifysignal_spec.workflows.gate_coverage import calculate_gate_coverage, coverage_status
from verifysignal_spec.workflows.models import GateCoverageResult, GoldenPathRunState, RepairRecommendation, RunOutcomeSummary
from verifysignal_spec.workflows.repair_recommendations import recommend_repairs_for_gate_coverage
from verifysignal_spec.workflows.readiness import executable_contract_blockers, legacy_executable_artifact_blockers, managed_runtime_contract_blockers
from verifysignal_spec.workflows.stage_cards import run_result_card
from verifysignal_spec.workflows.target_confirmation import target_confirmation_blocker
from verifysignal_spec.workflows.repository import load_artifact_plan
from verifysignal_spec.workspace.models import ArtifactReference, LastCoreAttempt, RerunPolicy, RunHistoryEntry
from verifysignal_spec.workspace import layout
from verifysignal_spec.workspace.repository import (
    calculate_run_confirmation_requirements,
    clear_last_core_attempt,
    core_attempt_iso,
    load_document,
    load_readiness_snapshot,
    load_use_case,
    now_iso,
    record_run,
    refresh_collision_findings,
    load_supersede_reviews,
    reconcile_active_confirmation,
    resolve_artifacts,
    resolve_named_output,
    save_last_core_attempt,
    save_supersede_review,
    side_effect_class,
    side_effect_lifecycle_summary,
    snapshot_invalidation_reasons,
)
from verifysignal_spec.workspace.models import PostCommitInterpretation
from verifysignal_spec.workflows.write_safety import (
    build_rerun_approval_review,
    canonical_side_effect_policy_snapshot,
    evaluate_rerun_decision as _evaluate_rerun_decision,
)
from verifysignal_spec.workflows.run_preflight import build_run_preflight, local_run_policy_blockers


_DEFAULT_PREPARED_WRITER = write_prepared_run_request


def run(
    project: Path,
    alias: str,
    profile_name: str = "normal",
    interactive: bool = True,
    core_cmd: str | None = None,
    api_base_url: str | None = None,
    slow_mo_override: int | None = None,
    confirmed_risks: list[str] | None = None,
    record: bool = False,
    replay: str | Path | None = None,
    env_file: Path | None = None,
) -> dict[str, Any]:
    # The loaded use case is `use_case`, not `record`: `record` is the --record flag, and this module
    # also imports `record_run`. The overloaded name is not cosmetic — a local `record` holding the
    # (always truthy) use case silently shadowed this flag and made EVERY run pass --record to Core.
    use_case = load_use_case(project, alias)
    target_blocker = target_confirmation_blocker(project, use_case)
    profile = next((item for item in use_case.profiles if item.name == profile_name), None)
    if profile is None:
        available = ", ".join(item.name for item in use_case.profiles) or "normal"
        raise ValueError(f"Unknown profile for {alias}: {profile_name}. Available profiles: {available}.")
    reviews = load_supersede_reviews(project, alias)
    local_policy_blockers = local_run_policy_blockers(
        use_case,
        supersede_reviews=reviews,
    )
    readiness_snapshot = load_readiness_snapshot(project, alias)
    preflight = build_run_preflight(
        {
            "targetBlocker": target_blocker,
            "missingArtifacts": _missing_local_run_artifacts(project, use_case),
            "policyBlockers": local_policy_blockers,
            "confirmationRequirements": calculate_run_confirmation_requirements(project, use_case),
            "confirmedRisks": list(confirmed_risks or []),
            "readinessInvalidationReasons": (
                snapshot_invalidation_reasons(project, use_case, readiness_snapshot)
                if readiness_snapshot is not None
                else []
            ),
        },
        use_case,
        readiness_snapshot,
        {},
        reviews,
    )
    rerun_guard = preflight["rerunDecision"]
    first_preflight_blocker = preflight["blockers"][0] if preflight.get("blockers") else None
    if (
        isinstance(first_preflight_blocker, dict)
        and first_preflight_blocker.get("code") == "runtime.rerun-confirmation-required"
        and rerun_guard.get("confirmationId") in set(confirmed_risks or [])
    ):
        review = build_rerun_approval_review(
            use_case,
            rerun_guard,
            created_at=now_iso(),
            created_by="run --confirm-risk",
        )
        save_supersede_review(project, alias, review)
        reviews = load_supersede_reviews(project, alias)
        preflight = build_run_preflight(
            {
                "targetBlocker": target_blocker,
                "missingArtifacts": _missing_local_run_artifacts(project, use_case),
                "policyBlockers": local_policy_blockers,
                "confirmationRequirements": calculate_run_confirmation_requirements(project, use_case),
                "confirmedRisks": list(confirmed_risks or []),
                "readinessInvalidationReasons": (
                    snapshot_invalidation_reasons(project, use_case, readiness_snapshot)
                    if readiness_snapshot is not None
                    else []
                ),
            },
            use_case,
            readiness_snapshot,
            {},
            reviews,
        )
        rerun_guard = preflight["rerunDecision"]
    reconcile_active_confirmation(project, alias, preflight.get("confirmation"))
    if not preflight["canProceed"]:
        blocker = preflight["blockers"][0]
        return {
            "alias": alias,
            "status": "blocked",
            "coreStatus": "not-run",
            "coverageStatus": "not-run",
            "coreBrowserStatus": "blocked",
            "specCoverageStatus": "not-run",
            "profile": profile_name,
            "rerunDecision": rerun_guard,
            "requiresConfirmation": bool(preflight["requiresConfirmation"]),
            "confirmation": preflight.get("confirmation"),
            "blockers": preflight["blockers"],
            "reason": blocker.get("message"),
            "recommendedAction": preflight.get("recommendedAction"),
            "nextAction": preflight["nextAction"],
        }

    environment_values: dict[str, str] = {}
    environment_warnings: list[dict[str, str]] = []
    if env_file:
        try:
            env_file_path = resolve_environment_file_path(project, env_file)
            environment_values = load_environment_file(
                env_file_path,
                declared_keys=declared_environment_keys(use_case),
            )
            environment_warnings = git_exposure_warnings(project, env_file_path)
        except EnvironmentFileError as exc:
            return {
                "alias": alias,
                "status": "blocked",
                "coreStatus": "not-run",
                "coverageStatus": "not-run",
                "blockers": [exc.blocker()],
                "reason": exc.message,
                "valuesIncluded": False,
            }
    # --record/--replay are optional Core run MODES: require the advertised capability only when the
    # flag is actually passed, so an older Core blocks with a clear code instead of failing inside run.
    run_mode_capability = "run-record" if record else ("run-replay" if replay else None)
    managed_runtime = ensure_core_runtime(
        project, explicit_core_cmd=core_cmd, api_base_url=api_base_url, context="run", required_capability=run_mode_capability
    )
    if managed_runtime.status != "ready":
        contract_blockers = managed_runtime_contract_blockers(managed_runtime)
        if contract_blockers:
            return {
                "alias": alias,
                "status": "blocked",
                "coreStatus": "blocked",
                "coverageStatus": "not-run",
                "coreBrowserStatus": "blocked",
                "specCoverageStatus": "not-run",
                "managedRuntimeReadiness": managed_runtime.to_dict(),
                "blockers": [blocker.to_dict() for blocker in contract_blockers],
                "reason": contract_blockers[0].message,
                "nextAction": f"verifysignal workflow check run --alias {alias} --json",
            }
        if any(blocker.code == "core.missing" for blocker in managed_runtime.blockers):
            raise CoreMissingError(f"{managed_runtime.message} verifysignal core setup --json")
        return {
            "alias": alias,
            "status": "blocked",
            "coreStatus": "blocked",
            "coverageStatus": "not-run",
            "coreBrowserStatus": "blocked",
            "specCoverageStatus": "not-run",
            "managedRuntimeReadiness": managed_runtime.to_dict(),
            "blockers": [blocker.to_dict() for blocker in managed_runtime.blockers],
            "reason": managed_runtime.message,
            "nextAction": managed_runtime.nextAction,
        }
    core_contract = _core_contract(project, managed_runtime.runtimeCommand)
    use_case, run_request, main_skill, skills = resolve_artifacts(project, alias, core_contract=core_contract)
    profile_settings_model = resolve_effective_profile_settings(profile, slow_mo_override=slow_mo_override)
    contract_blockers = [
        *legacy_executable_artifact_blockers(run_request, main_skill, skills),
        *executable_contract_blockers(project, managed_runtime.runtimeCommand, alias=alias, core_contract=core_contract),
    ]
    if contract_blockers:
        return {
            "alias": alias,
            "status": "blocked",
            "coreStatus": "blocked",
            "coverageStatus": "not-run",
            "coreBrowserStatus": "blocked",
            "specCoverageStatus": "not-run",
            "selectedMainSkill": _selected_main_skill(use_case.mainSkill, main_skill),
            "profile": profile_name,
            "profileSettings": profile_settings_model.to_dict(),
            "managedRuntimeReadiness": managed_runtime.to_dict(),
            "blockers": [blocker.to_dict() for blocker in contract_blockers],
            "reason": contract_blockers[0].message,
            "nextAction": f"verifysignal workflow check run --alias {alias} --json",
        }
    prepared_run_id = f"{alias}-{now_iso().replace(':', '').replace('-', '')}"
    named_output_values, named_output_error = _named_output_runtime_values(project, use_case)
    if named_output_error:
        return {
            "alias": alias,
            "status": "blocked",
            "coreStatus": "blocked",
            "coverageStatus": "not-run",
            "coreBrowserStatus": "blocked",
            "specCoverageStatus": "not-run",
            "selectedMainSkill": _selected_main_skill(use_case.mainSkill, main_skill),
            "profile": profile_name,
            "profileSettings": profile_settings_model.to_dict(),
            "managedRuntimeReadiness": managed_runtime.to_dict(),
            "blockers": [
                {
                    "code": "runtime.named-output-resolution-failed",
                    "severity": "blocker",
                    "category": "named-output",
                    "message": named_output_error,
                    "recoveryCommand": f"verifysignal workflow check run --alias {alias} --json",
                }
            ],
            "reason": named_output_error,
            "nextAction": "Publish or disambiguate the named output before running.",
        }
    runtime_values = resolve_runtime_inputs(
        use_case.runtimeInputs,
        interactive=interactive,
        provided={**_run_request_parameters(run_request), **named_output_values},
        run_id=prepared_run_id,
        refresh_names=rerun_guard.get("refreshRuntimeInputs", []),
    )
    collision_findings = _generated_binding_collision_findings(project, use_case, runtime_values)
    if collision_findings:
        return {
            "alias": alias,
            "status": "blocked",
            "coreStatus": "blocked",
            "coverageStatus": "not-run",
            "coreBrowserStatus": "blocked",
            "specCoverageStatus": "not-run",
            "selectedMainSkill": _selected_main_skill(use_case.mainSkill, main_skill),
            "profile": profile_name,
            "profileSettings": profile_settings_model.to_dict(),
            "managedRuntimeReadiness": managed_runtime.to_dict(),
            "rerunDecision": rerun_guard,
            "blockers": [
                {
                    "code": f"runtime.{item.get('code')}",
                    "severity": "blocker",
                    "category": item.get("category", "generated-binding"),
                    "message": item.get("message"),
                    "recoveryCommand": f"verifysignal workflow check run --alias {alias} --json",
                }
                for item in collision_findings
            ],
            "reason": collision_findings[0]["message"],
            "nextAction": "Adjust generated runtime input template or seed before running again.",
        }
    output_dir = project / ".verifysignal" / "runs" / alias
    if not prepared_output_dir_is_safe(project, output_dir):
        return _prepared_request_ownership_blocker(alias, profile_name, rerun_guard)
    prepared_document, confirmation_findings, prepared_changed = prepare_run_request_document(run_request, runtime_values)
    if confirmation_findings:
        blockers = confirmation_placeholder_blockers(confirmation_findings)
        return {
            "alias": alias,
            "status": "blocked",
            "coreStatus": "blocked",
            "coverageStatus": "not-run",
            "coreBrowserStatus": "blocked",
            "specCoverageStatus": "not-run",
            "selectedMainSkill": _selected_main_skill(use_case.mainSkill, main_skill),
            "profile": profile_name,
            "profileSettings": profile_settings_model.to_dict(),
            "managedRuntimeReadiness": managed_runtime.to_dict(),
            "rerunDecision": rerun_guard,
            "blockers": blockers,
            "reason": blockers[0]["message"],
            "nextAction": blockers[0].get("nextAction") or f"verifysignal workflow check run --alias {alias} --json",
        }
    writer_override = (
        write_prepared_run_request
        if write_prepared_run_request is not _DEFAULT_PREPARED_WRITER
        else None
    )
    prepared_ownership = (
        write_owned_prepared_run_request(
            project,
            output_dir,
            prepared_run_id,
            prepared_document,
            **({"writer": writer_override} if writer_override is not None else {}),
        )
        if prepared_changed and prepared_document is not None
        else PreparedRunRequestOwnership(
            path=run_request,
            createdByThisInvocation=False,
        )
    )
    if prepared_changed and not prepared_ownership.createdByThisInvocation:
        return _prepared_request_ownership_blocker(alias, profile_name, rerun_guard)
    prepared_run_request = prepared_ownership.path
    try:
        result = CoreAdapter(executable=managed_runtime.runtimeCommand, cwd=project).run(
            prepared_run_request,
            main_skill,
            skills,
            output_dir=output_dir,
            headed=profile_settings_model.headed,
            slow_mo_ms=profile_settings_model.slowMoMs,
            record=record,
            replay=replay,
            env={**runtime_values, **environment_values},
            entitlement_receipt=valid_receipt_path(
                api_base_url_for_runtime(managed_runtime, api_base_url),
            ),
        )
        normalized_outcome = normalize_core_outcome("run", result)
    except BaseException:
        cleanup_owned_prepared_run_request(project, prepared_ownership)
        raise
    if not normalized_outcome.eligibleForRunPersistence:
        cleanup_owned_prepared_run_request(project, prepared_ownership)
        explicitly_not_started = bool(
            normalized_outcome.executionKnown
            and normalized_outcome.executionStarted is False
            and normalized_outcome.sideEffectMayExist is False
        )
        attempt = LastCoreAttempt(
            attemptedAt=core_attempt_iso(),
            operation="run",
            schema=normalized_outcome.schema,
            status=normalized_outcome.status,
            errorCode=normalized_outcome.errorCode,
            executionState="not-started" if explicitly_not_started else "unknown",
            sideEffectMayExist=normalized_outcome.sideEffectMayExist,
        )
        save_last_core_attempt(project, alias, attempt)
        updated_use_case = load_use_case(project, alias)
        updated_readiness = load_readiness_snapshot(project, alias)
        attempt_preflight = build_run_preflight(
            {
                "confirmationRequirements": calculate_run_confirmation_requirements(project, updated_use_case),
                "confirmedRisks": [],
                "readinessInvalidationReasons": (
                    snapshot_invalidation_reasons(project, updated_use_case, updated_readiness)
                    if updated_readiness is not None
                    else []
                ),
            },
            updated_use_case,
            updated_readiness,
            {},
            load_supersede_reviews(project, alias),
        )
        reconcile_active_confirmation(project, alias, attempt_preflight.get("confirmation"))
        blocker_code = normalized_outcome.blockerCode or "core.contract-invalid"
        reason = (
            "Core trust could not be verified before execution."
            if blocker_code == "entitlement.unverifiable"
            else "Core returned a response that is not eligible for run persistence."
        )
        next_action = (
            "verifysignal core update --json"
            if blocker_code in {"entitlement.unverifiable", "core.contract-invalid", "core.incompatible"}
            else f"verifysignal workflow check run --alias {alias} --json"
        )
        return {
            "alias": alias,
            "status": "blocked",
            "coreStatus": "not-started" if explicitly_not_started else "execution-unknown",
            "coverageStatus": "not-run",
            "coreBrowserStatus": "not-run",
            "specCoverageStatus": "not-run",
            "profile": profile_name,
            "managedRuntimeReadiness": managed_runtime.to_dict(),
            "lastCoreAttempt": attempt.to_dict(),
            "rerunDecision": attempt_preflight["rerunDecision"],
            "requiresConfirmation": bool(attempt_preflight["requiresConfirmation"]),
            "confirmation": attempt_preflight.get("confirmation"),
            "blockers": [
                {
                    "code": blocker_code,
                    "severity": "blocker",
                    "category": "core-runtime",
                    "message": reason,
                    "recoveryCommand": next_action,
                }
            ],
            "reason": reason,
            "nextAction": next_action,
        }
    release_prepared_run_request_ownership(prepared_ownership)
    data = result["data"]
    run_id = str(data["runId"])
    core = core_status(result)
    result_with_report = _result_with_public_report(project, result)
    side_effects = _public_result_field(result_with_report, "sideEffects")
    runtime_outputs = _public_result_field(result_with_report, "runtimeOutputs") or []
    post_commit = _post_commit_interpretation(result_with_report, use_case, side_effects)
    result_classification = _public_result_field(result_with_report, "resultClassification")
    gates = _planned_gates(project, alias)
    gate_coverage_results = _runtime_gate_coverage(project, result, gates)
    gate_coverage = [item.to_dict() for item in gate_coverage_results]
    contradictions = (
        [
            item.to_dict()
            for item in recommend_repairs_for_gate_coverage(gate_coverage_results, gates, source_run_id=str(run_id))
        ]
        if core not in {"failed", "error", "blocked"}
        else []
    )
    repair_recommendations = [
        item.to_dict()
        for item in _repair_recommendations_from_gate_coverage(gate_coverage_results, core, source_run_id=str(run_id))
    ]
    spec_coverage_status = coverage_status(core, gate_coverage_results)
    selected_main_skill = _selected_main_skill(use_case.mainSkill, main_skill)
    executed_skill = _executed_skill(data)
    skill_selection_status = _skill_selection_status(selected_main_skill, executed_skill)
    missing_required_gates = _missing_required_gates(gate_coverage_results)
    use_case_status = _use_case_status(core, spec_coverage_status)
    if _side_effect_violations(side_effects) or str(post_commit.sideEffectStatus or "") == "violated":
        use_case_status = "failed"
    profile_settings = profile_settings_model.to_dict()
    if not profile_settings.get("overrides"):
        profile_settings.pop("overrides", None)
    partial_coverage = gate_coverage if core in {"failed", "error", "blocked"} else []
    reason = _reason(use_case_status, core, missing_required_gates, skill_selection_status)
    next_action = _next_action(use_case_status, alias)
    failed_step = _failed_step(result)
    outcome_summary = RunOutcomeSummary(
        alias=alias,
        overallStatus=use_case_status,
        coreBrowserStatus=core,
        specCoverageStatus=spec_coverage_status,
        selectedMainSkill=selected_main_skill,
        profile=profile_name,
        runId=str(run_id),
        failedStep=failed_step,
        nextAction=next_action,
    ).to_dict()
    first_run_payload = _first_run_payload(
        project,
        alias,
        core,
        spec_coverage_status,
        missing_required_gates,
        next_action,
        _run_request_parameters(run_request).get("baseUrl", ""),
        side_effect_status=str(post_commit.sideEffectStatus or "not-applicable"),
        side_effect_violations=_side_effect_violations(side_effects),
    )
    if first_run_payload:
        outcome_summary.update(
            {
                "firstRunStatus": first_run_payload["firstRunStatus"],
                "strictPass": first_run_payload["strictPass"],
                "stageCards": first_run_payload["stageCards"],
            }
        )
    entry = RunHistoryEntry(
        runId=run_id,
        useCaseAlias=alias,
        profile=profile_name,
        status=use_case_status,
        coreStatus=core,
        coverageStatus=spec_coverage_status,
        profileSettings=profile_settings,
        selectedMainSkill=selected_main_skill,
        executedSkill=executed_skill,
        skillSelectionStatus=skill_selection_status,
        gateCoverage=gate_coverage,
        missingRequiredGates=missing_required_gates,
        partialCoverage=partial_coverage,
        runtimeContradictions=contradictions,
        repairRecommendations=repair_recommendations,
        sideEffectPolicy=canonical_side_effect_policy_snapshot(use_case.sideEffects),
        sideEffects=side_effects if isinstance(side_effects, dict) else None,
        runtimeOutputs=runtime_outputs if isinstance(runtime_outputs, list) else [],
        resolvedRuntimeInputs=[
            {
                "name": name,
                "value": value,
                "source": "generated" if _runtime_input_source(use_case, name) == "generated" else "runtime",
                "runId": str(run_id),
                "targetScope": _target_scope(use_case),
                "useCaseAlias": alias,
                "refreshed": name in set(rerun_guard.get("refreshRuntimeInputs", [])),
                "committed": bool(post_commit.postCommit or post_commit.sideEffectMayExist),
                "status": "committed" if bool(post_commit.postCommit or post_commit.sideEffectMayExist) else "discarded",
            }
            for name, value in runtime_values.items()
            if _safe_resolved_runtime_input(use_case, name)
        ],
        postCommitInterpretation=post_commit.to_dict(),
        rerunDecision=rerun_guard,
        sideEffectLifecycle=side_effect_lifecycle_summary(use_case, runtime_outputs if isinstance(runtime_outputs, list) else []),
        startedAt=now_iso(),
        completedAt=now_iso(),
        summary={
            "core": data.get("summary") or result.get("summary"),
            "status": use_case_status,
            "coverageStatus": spec_coverage_status,
            "coreBrowserStatus": core,
            "specCoverageStatus": spec_coverage_status,
            "reason": reason,
            "nextAction": next_action,
            "mainSkill": selected_main_skill,
            "runOutcomeSummary": outcome_summary,
            "postCommitInterpretation": post_commit.to_dict(),
            "resultClassification": result_classification,
            "rerunDecision": rerun_guard,
            "sideEffectLifecycle": side_effect_lifecycle_summary(use_case, runtime_outputs if isinstance(runtime_outputs, list) else []),
        },
        reportPath=data.get("reportPath"),
        evidenceDir=data.get("evidencePath") or data.get("evidenceDir"),
    )
    record_run(project, entry)
    clear_last_core_attempt(project, alias)
    completed_use_case = load_use_case(project, alias)
    completed_readiness = load_readiness_snapshot(project, alias)
    completed_preflight = build_run_preflight(
        {
            "confirmationRequirements": calculate_run_confirmation_requirements(project, completed_use_case),
            "confirmedRisks": [],
            "readinessInvalidationReasons": (
                snapshot_invalidation_reasons(project, completed_use_case, completed_readiness)
                if completed_readiness is not None
                else []
            ),
        },
        completed_use_case,
        completed_readiness,
        {},
        load_supersede_reviews(project, alias),
    )
    reconcile_active_confirmation(project, alias, completed_preflight.get("confirmation"))
    send_usage_ping("run", ping_outcome(entry.status), api_base_url=api_base_url)
    return {
        **({"credentialWarnings": environment_warnings} if environment_warnings else {}),
        "alias": alias,
        "status": entry.status,
        "coreStatus": core,
        "coverageStatus": spec_coverage_status,
        "coreBrowserStatus": core,
        "specCoverageStatus": spec_coverage_status,
        "runOutcomeSummary": outcome_summary,
        **first_run_payload,
        "selectedMainSkill": selected_main_skill,
        "executedSkill": executed_skill,
        "skillSelectionStatus": skill_selection_status,
        "profile": profile_name,
        "profileSettings": profile_settings,
        "managedRuntimeReadiness": managed_runtime.to_dict(),
        "gateCoverage": gate_coverage,
        "missingRequiredGates": missing_required_gates,
        "partialCoverage": partial_coverage,
        "runtimeContradictions": contradictions,
        "repairRecommendations": repair_recommendations,
        "postCommitInterpretation": post_commit.to_dict(),
        "rerunDecision": rerun_guard,
        "runtimeOutputs": runtime_outputs if isinstance(runtime_outputs, list) else [],
        "sideEffects": side_effects if isinstance(side_effects, dict) else None,
        "sideEffectLifecycle": side_effect_lifecycle_summary(use_case, runtime_outputs if isinstance(runtime_outputs, list) else []),
        "reason": reason,
        "nextAction": next_action,
        "reportPath": entry.reportPath,
        "evidenceDir": entry.evidenceDir,
        "core": result,
    }


def _first_run_payload(
    project: Path,
    alias: str,
    core_browser_status: str,
    spec_coverage_status: str,
    missing_required_gates: list[str],
    next_action: str,
    target: str,
    *,
    side_effect_status: str = "not-applicable",
    side_effect_violations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    state = golden_path_state(project)
    if state.get("selectedCandidate") != alias or state.get("recommendationStatus") != "accepted":
        return {}
    repaired = bool(state.get("repairFeedback"))
    first_run_status, strict_pass = classify_first_run_status(
        core_browser_status,
        spec_coverage_status,
        missing_required_gates,
        side_effect_status=side_effect_status,
        side_effect_violations=side_effect_violations,
        repaired=repaired,
    )
    stage_cards = [
        run_result_card(
            alias=alias,
            first_run_status=first_run_status,
            strict_pass=strict_pass,
            core_browser_status=core_browser_status,
            spec_coverage_status=spec_coverage_status,
            missing_required_gates=missing_required_gates,
            next_action=next_action,
        )
    ]
    run_state = GoldenPathRunState.from_run_result(
        use_case_alias=alias,
        target=str(target or ""),
        core_browser_status=core_browser_status,
        spec_coverage_status=spec_coverage_status,
        missing_required_gates=missing_required_gates,
        side_effect_status=side_effect_status,
        side_effect_violations=side_effect_violations,
        repaired=repaired,
        repair_feedback=list(state.get("repairFeedback", [])),
        stage_cards=stage_cards,
    )
    update_golden_path_run_state(project, run_state)
    return {
        "firstRunStatus": first_run_status,
        "strictPass": strict_pass,
        "stageCards": stage_cards,
    }


def evaluate_rerun_decision(record: Any, *, supersede_reviews: list[Any] | None = None) -> dict[str, Any]:
    return _evaluate_rerun_decision(record, supersede_reviews=supersede_reviews)


def _missing_local_run_artifacts(project: Path, record: Any) -> list[str]:
    missing: list[str] = []
    references = [
        record.runRequest,
        record.mainSkill,
        *record.skills,
        *record.sourceOnlySkills,
    ]
    for reference in references:
        if reference is None or not getattr(reference, "path", None):
            label = "run request" if reference is record.runRequest else "main/supporting skill"
            missing.append(label)
            continue
        try:
            path = layout.project_relative_path(project, str(reference.path))
        except ValueError:
            missing.append(str(reference.path))
            continue
        if not path.exists() or not path.is_file():
            missing.append(str(reference.path))
    return sorted(set(missing))


def _generated_binding_collision_findings(project: Path, record: Any, runtime_values: dict[str, str]) -> list[dict[str, Any]]:
    identity = record.resourceIdentity if isinstance(getattr(record, "resourceIdentity", None), dict) else {}
    if identity.get("collisionPolicy") != "avoid":
        return []
    identity_input = identity.get("identityInput")
    if identity_input and identity_input in runtime_values:
        return refresh_collision_findings(
            project,
            use_case_alias=record.alias,
            target_scope=str(identity.get("targetScope") or _target_scope(record) or ""),
            bindings={str(identity_input): runtime_values[str(identity_input)]},
        )
    generated = {
        item.name: runtime_values[item.name]
        for item in record.runtimeInputs
        if item.source == "generated" and item.name in runtime_values
    }
    return refresh_collision_findings(
        project,
        use_case_alias=record.alias,
        target_scope=str(identity.get("targetScope") or _target_scope(record) or ""),
        bindings=generated,
    )


def _named_output_runtime_values(project: Path, record: Any) -> tuple[dict[str, str], str | None]:
    values: dict[str, str] = {}
    for item in getattr(record, "runtimeInputs", []):
        if getattr(item, "source", "") != "named-output":
            continue
        output_name = item.value or item.default or (item.references[0] if item.references else item.name)
        try:
            output = resolve_named_output(project, str(output_name))
        except ValueError as exc:
            return {}, str(exc)
        values[item.name] = str(output.get("value") or "")
    return values, None


def _target_scope(record: Any) -> str | None:
    identity = record.resourceIdentity if isinstance(getattr(record, "resourceIdentity", None), dict) else {}
    if identity.get("targetScope"):
        return str(identity.get("targetScope"))
    for item in getattr(record, "runtimeInputs", []):
        if getattr(item, "name", "") == "baseUrl" and getattr(item, "value", None):
            return str(item.value)
    return None


def _core_contract(project: Path, core_command: str | None) -> dict[str, Any] | None:
    if not core_command:
        return None
    try:
        return project_core_contract(CoreAdapter(executable=core_command, cwd=project).contracts())
    except Exception:
        return None


def _planned_gates(project: Path, alias: str) -> list[Any]:
    try:
        gates, _warnings = normalize_planned_gates(load_artifact_plan(project, alias).validationGates)
        return gates
    except Exception:
        return []


def _runtime_gate_coverage(project: Path, result: dict[str, Any], gates: list[Any]) -> list[GateCoverageResult]:
    if not gates:
        return []
    evidence = extract_core_runtime_evidence(
        _result_with_public_report(project, result),
        known_gate_ids={gate.id for gate in gates},
    )
    return calculate_gate_coverage(gates, evidence)


def _post_commit_interpretation(result: dict[str, Any], record: Any, side_effects: Any) -> PostCommitInterpretation:
    interpretation = PostCommitInterpretation.from_core_result(result)
    if isinstance(side_effects, dict):
        return interpretation
    if side_effect_class(record) in {"write", "external-notification"}:
        classification = _public_result_field(result, "resultClassification")
        classification = classification if isinstance(classification, dict) else {}
        return PostCommitInterpretation(
            postCommit=False,
            sideEffectMayExist=True,
            executionStatus=classification.get("executionStatus"),
            verificationStatus="unknown",
            sideEffectStatus="unknown",
            failurePhase="post-verification",
            rerunRisk="requires-confirmation",
            message=(
                "This write-capable use case completed without a structured Core side-effect envelope; "
                "Spec conservatively treats write activity as unknown/inferred rather than proof of no side effect."
            ),
        )
    return interpretation


def _result_with_public_report(project: Path, result: dict[str, Any]) -> dict[str, Any]:
    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    if isinstance(data.get("report"), dict):
        return result
    report = _load_public_qa_report(project, data.get("reportPath"))
    if report is None:
        return result
    updated = dict(result)
    updated_data = dict(data)
    updated_data["report"] = report
    updated["data"] = updated_data
    return updated


def _public_result_field(result: dict[str, Any], field_name: str) -> Any:
    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    report = data.get("report") if isinstance(data.get("report"), dict) else {}
    if field_name in data:
        return data.get(field_name)
    return report.get(field_name)


def _side_effect_violations(side_effects: Any) -> list[dict[str, Any]]:
    if not isinstance(side_effects, dict):
        return []
    return [
        item
        for item in side_effects.get("violations", [])
        if isinstance(item, dict)
    ]


def _prepared_run_request_path(run_request: Path, output_dir: Path, run_id: str, runtime_values: dict[str, str]) -> Path:
    document, findings, changed = prepare_run_request_document(run_request, runtime_values)
    if findings:
        message = str(findings[0].get("message") or "Confirmation placeholder could not be resolved.")
        raise ValueError(message)
    if not changed or document is None:
        return run_request
    return write_prepared_run_request(output_dir, run_id, document)


def _prepared_request_ownership_blocker(
    alias: str,
    profile_name: str,
    rerun_decision: dict[str, Any],
) -> dict[str, Any]:
    reason = (
        "The prepared run request could not be created as an invocation-owned "
        "regular file inside the project runs directory."
    )
    next_action = (
        "Restore .verifysignal/runs as a project-owned directory and retry the run."
    )
    return {
        "alias": alias,
        "status": "blocked",
        "coreStatus": "not-run",
        "coverageStatus": "not-run",
        "coreBrowserStatus": "blocked",
        "specCoverageStatus": "not-run",
        "profile": profile_name,
        "rerunDecision": rerun_decision,
        "requiresConfirmation": False,
        "blockers": [
            {
                "code": "runtime.prepared-request-ownership-refused",
                "severity": "blocker",
                "category": "prepared-run-request",
                "message": reason,
                "recoveryCommand": next_action,
            }
        ],
        "reason": reason,
        "nextAction": next_action,
    }


def _runtime_input_source(record: Any, name: str) -> str:
    for item in record.runtimeInputs:
        if item.name == name:
            return item.source
    return "runtime"


def _safe_resolved_runtime_input(record: Any, name: str) -> bool:
    for item in record.runtimeInputs:
        if item.name == name:
            return item.kind != "credential" and bool(item.persistValue or item.source == "generated")
    return False


def _load_public_qa_report(project: Path, raw_path: Any) -> dict[str, Any] | None:
    report_path = _resolve_report_path(project, raw_path)
    if report_path is None or not report_path.exists():
        return None
    try:
        data = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict) or data.get("schemaVersion") != "qa-report/v1":
        return None
    return data


def _resolve_report_path(project: Path, raw_path: Any) -> Path | None:
    if not raw_path:
        return None
    path = Path(str(raw_path))
    candidate = path if path.is_absolute() else project / path
    try:
        resolved = candidate.resolve()
        workspace = (project / ".verifysignal").resolve()
    except Exception:
        return None
    if resolved == workspace or workspace in resolved.parents:
        return resolved
    return None


def _selected_main_skill(reference: ArtifactReference | None, path: Path) -> dict[str, Any]:
    data: dict[str, Any] = {"path": str(reference.path if reference else path)}
    if reference and reference.id:
        data["id"] = reference.id
    if reference and reference.version:
        data["version"] = reference.version
    return data


def _executed_skill(data: dict[str, Any]) -> dict[str, Any] | None:
    raw = data.get("executedSkill") or data.get("executedSkillId")
    if not raw:
        return None
    if isinstance(raw, dict):
        result = dict(raw)
        result.setdefault("source", "core-public-result")
        return result
    return {"id": str(raw), "source": "core-public-result"}


def _skill_selection_status(selected: dict[str, Any], executed: dict[str, Any] | None) -> str:
    if not executed:
        return "unknown"
    selected_tokens = {str(value) for value in [selected.get("id"), selected.get("path")] if value}
    selected_tokens.update(Path(token).name for token in list(selected_tokens))
    executed_tokens = {str(value) for value in [executed.get("id"), executed.get("path")] if value}
    executed_tokens.update(Path(token).name for token in list(executed_tokens))
    return "matched" if selected_tokens & executed_tokens else "mismatch"


def _missing_required_gates(gate_coverage: list[GateCoverageResult]) -> list[str]:
    incomplete = {"missing", "network-only", "screenshot-only", "unmapped", "not-evaluated", "incomplete"}
    return [item.gateId for item in gate_coverage if item.required and item.status in incomplete]


def _use_case_status(core: str, spec_coverage_status: str) -> str:
    if core in {"failed", "error", "blocked"}:
        return "failed"
    if spec_coverage_status != "complete":
        return "incomplete"
    return "passed"


def _reason(status: str, core: str, missing_required_gates: list[str], skill_selection_status: str) -> str:
    if status == "passed":
        return "Core passed and all planned required validation gates were evidenced."
    if status == "failed":
        return f"Core/browser execution reported {core}; Spec coverage is diagnostic only because runtime evidence may not have been committed."
    pieces = ["Core passed but required validation gates are missing or incomplete."]
    if missing_required_gates:
        pieces.append(f"Missing required gates: {', '.join(missing_required_gates)}.")
    if skill_selection_status == "mismatch":
        pieces.append("Core executed a different skill than the planned main validation skill.")
    return " ".join(pieces)


def _next_action(status: str, alias: str) -> str:
    if status == "passed":
        return "No repair needed."
    if status == "incomplete":
        return f"Run `verifysignal repair {alias} --json` or re-run after repairing missing gate evidence."
    return f"Inspect the Core report and run `verifysignal repair {alias} --from-report <report> --json`."


def _failed_step(result: dict[str, Any]) -> str | None:
    data = result.get("data", {}) if isinstance(result.get("data"), dict) else {}
    summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    return data.get("failedStep") or data.get("failedStepId") or summary.get("failedStepId")


def _repair_recommendations_from_gate_coverage(
    gate_coverage: list[GateCoverageResult],
    core: str,
    *,
    source_run_id: str,
) -> list[RepairRecommendation]:
    if core in {"failed", "error", "blocked"}:
        return []
    recommendations: list[RepairRecommendation] = []
    for item in gate_coverage:
        if not item.required or item.status not in {"missing", "network-only", "screenshot-only", "unmapped", "not-evaluated", "incomplete"}:
            continue
        recommendations.append(
            RepairRecommendation(
                id=f"repair-{item.gateId}",
                category="safe-artifact-repair",
                safeCategory="gateid-mapping",
                summary=f"Required gate {item.gateId} was not proven by runtime evidence.",
                action="Ask for confirmation before changing coverage mapping, then map specific rendered-result evidence or replan if confirmed.",
                affectedArtifacts=[],
                blockedReason="Coverage mapping changes can alter validation intent and require confirmation.",
                requiresUserDecision=True,
                sourceFeedback=[source_run_id, item.gateId],
            )
        )
    return recommendations


def _run_request_parameters(run_request: Path) -> dict[str, Any]:
    data = load_document(run_request, default={}) or {}
    if not isinstance(data, dict):
        return {}
    parameters = data.get("parameters")
    if isinstance(parameters, dict):
        return dict(parameters)
    runtime_inputs = data.get("runtimeInputs")
    if isinstance(runtime_inputs, list):
        return {
            str(item["name"]): value
            for item in runtime_inputs
            if isinstance(item, dict)
            and item.get("name")
            for value in [item.get("value", item.get("default"))]
            if value is not None and value != ""
        }
    return {}
