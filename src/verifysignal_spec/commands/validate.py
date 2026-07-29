from __future__ import annotations

from pathlib import Path
from typing import Any

from verifysignal_spec.commands.run_request_preparation import (
    confirmation_placeholder_blockers,
    prepare_run_request_document,
    write_prepared_run_request,
)
from verifysignal_spec.core.adapter import CoreAdapter
from verifysignal_spec.core.contracts import core_entitlement_blocker_code
from verifysignal_spec.core.errors import CoreExecutionError, CoreIncompatibleError, CoreMissingError
from verifysignal_spec.core.executable_contract import project_core_contract
from verifysignal_spec.runtime.entitlement import api_base_url_for_runtime, valid_receipt_path
from verifysignal_spec.runtime.env_file import (
    EnvironmentFileError,
    declared_environment_keys,
    git_exposure_warnings,
    load_environment_file,
    resolve_environment_file_path,
)
from verifysignal_spec.runtime.models import RuntimeSetupBlocker
from verifysignal_spec.runtime.resolver import ensure_core_runtime
from verifysignal_spec.workflows.first_run import advance_guided_first_run_state
from verifysignal_spec.workflows.models import WORKFLOW_VALIDATION_READINESS_SCHEMA, CoreReadiness, ReadinessBlocker, ValidationReadinessSummary
from verifysignal_spec.workflows.authoring_coherence import evaluate_persisted_coherence
from verifysignal_spec.workflows.readiness import (
    executable_contract_blockers,
    legacy_executable_artifact_blockers,
    managed_runtime_contract_blockers,
    structural_validation,
    validation_readiness,
)
from verifysignal_spec.workflows.runtime_readiness import evaluate_runtime_readiness
from verifysignal_spec.workspace.repository import create_readiness_snapshot_from_validation, load_supersede_reviews, load_use_case, resolve_artifacts, update_validation
from verifysignal_spec.workspace.validation import validate_side_effect_declaration


def _selected_main_skill(record_main_skill: Any, main_skill: Path) -> dict[str, Any]:
    data: dict[str, Any] = {"path": str(record_main_skill.path if record_main_skill else main_skill)}
    if record_main_skill and record_main_skill.id:
        data["id"] = record_main_skill.id
    if record_main_skill and record_main_skill.version:
        data["version"] = record_main_skill.version
    return data


def _core_contract_for_coherence(project: Path, core_command: str | None) -> dict[str, Any] | None:
    if not core_command:
        return None
    try:
        return project_core_contract(CoreAdapter(executable=core_command, cwd=project).contracts())
    except (CoreMissingError, CoreIncompatibleError, CoreExecutionError):
        return None


def run(
    project: Path,
    alias: str,
    runtime_readiness: bool = False,
    core_cmd: str | None = None,
    api_base_url: str | None = None,
    env_file: Path | None = None,
) -> dict[str, Any]:
    structural = structural_validation(project, alias=alias)
    if structural.status == "blocked":
        structural_dict = structural.to_dict()
        detailed_blockers = _structural_guided_blockers(structural_dict.get("findings", []), alias)
        return {
            "schemaVersion": WORKFLOW_VALIDATION_READINESS_SCHEMA,
            "alias": alias,
            "status": "blocked",
            "structuralValidation": structural_dict,
            "coreReadiness": CoreReadiness(status="error", message="Core readiness was not checked because structural workspace validation is blocked.").to_dict(),
            "blockers": [
                ReadinessBlocker(
                    code="workspace.structural-blocked",
                    message="Workspace structure is blocked. Review structuralValidation.findings and apply approved migrations when offered.",
                    recoveryCommand=f"verifysignal workflow check validate --alias {alias} --json",
                ).to_dict()
            ]
            + detailed_blockers,
        }
    environment_values: dict[str, str] = {}
    environment_warnings: list[dict[str, str]] = []
    if env_file:
        try:
            credential_record = load_use_case(project, alias)
            env_file_path = resolve_environment_file_path(project, env_file)
            environment_values = load_environment_file(
                env_file_path,
                declared_keys=declared_environment_keys(credential_record),
            )
            environment_warnings = git_exposure_warnings(project, env_file_path)
        except EnvironmentFileError as exc:
            return {
                "schemaVersion": WORKFLOW_VALIDATION_READINESS_SCHEMA,
                "alias": alias,
                "status": "blocked",
                "blockers": [exc.blocker()],
                "valuesIncluded": False,
            }
    managed_runtime = ensure_core_runtime(project, explicit_core_cmd=core_cmd, api_base_url=api_base_url, context="validate")
    if managed_runtime.status != "ready":
        contract_blockers = managed_runtime_contract_blockers(managed_runtime)
        result = {
            "schemaVersion": WORKFLOW_VALIDATION_READINESS_SCHEMA,
            "capabilitySchemaVersion": "verifysignal-spec-workflow-capability/v1",
            "requiredCapability": "workflow.guardrails/v1",
            "supported": True,
            "stage": "validate",
            "alias": alias,
            "status": "blocked",
            "structuralValidation": structural.to_dict(),
            "coreReadiness": CoreReadiness(
                status="incompatible" if managed_runtime.status == "incompatible" else "missing",
                coreCommand=managed_runtime.runtimeCommand,
                version=managed_runtime.runtimeVersion,
                contractVersion=managed_runtime.contractVersion or "",
                missingOperations=managed_runtime.missingOperations,
                incompatibleOperations=managed_runtime.incompatibleOperations,
                message=managed_runtime.message,
            ).to_dict(),
            "managedRuntimeReadiness": managed_runtime.to_dict(),
            "blockers": [blocker.to_dict() for blocker in contract_blockers]
            or [
                ReadinessBlocker.from_dict(blocker.to_dict()).to_dict()
                for blocker in managed_runtime.blockers
            ],
        }
        update_validation(project, alias, result)
        _persist_readiness_snapshot(project, alias, result)
        return result
    core_contract = _core_contract_for_coherence(project, managed_runtime.runtimeCommand)
    record, run_request, main_skill, skills = resolve_artifacts(project, alias, core_contract=core_contract)
    contract_blockers = [
        *legacy_executable_artifact_blockers(run_request, main_skill, skills),
        *executable_contract_blockers(project, managed_runtime.runtimeCommand, alias=alias, core_contract=core_contract),
    ]
    if contract_blockers:
        result = {
            "schemaVersion": WORKFLOW_VALIDATION_READINESS_SCHEMA,
            "alias": alias,
            "status": "blocked",
            "selectedMainSkill": _selected_main_skill(record.mainSkill, main_skill),
            "managedRuntimeReadiness": managed_runtime.to_dict(),
            "blockers": [blocker.to_dict() for blocker in contract_blockers],
        }
        update_validation(project, alias, result)
        _persist_readiness_snapshot(project, alias, result)
        return result
    coherence = evaluate_persisted_coherence(
        project,
        alias,
        core_contract=core_contract,
    )
    if coherence.status == "blocked":
        result = {
            "schemaVersion": WORKFLOW_VALIDATION_READINESS_SCHEMA,
            "alias": alias,
            "status": "blocked",
            "selectedMainSkill": _selected_main_skill(record.mainSkill, main_skill),
            "authoringCoherence": coherence.to_dict(),
            "blockers": [
                ReadinessBlocker(
                    code="authoring.coherence-blocked",
                    message=message,
                    recoveryCommand=f"verifysignal workflow persist implement --alias {alias} --payload <payload.json> --json",
                ).to_dict()
                for message in coherence.blockers
            ],
        }
        update_validation(project, alias, result)
        _persist_readiness_snapshot(project, alias, result)
        return result
    side_effect_findings = validate_side_effect_declaration(
        record.sideEffects,
        record.rerunPolicy,
        record.runtimeOutputs,
        [item.to_dict() for item in record.runtimeInputs],
        core_contract=core_contract,
        runtime_outcomes=[record.lastRun] if isinstance(record.lastRun, dict) else [],
    )
    side_effect_blockers = [item for item in side_effect_findings if item.get("severity") == "blocking"]
    if side_effect_blockers:
        result = {
            "schemaVersion": WORKFLOW_VALIDATION_READINESS_SCHEMA,
            "alias": alias,
            "status": "blocked",
            "selectedMainSkill": _selected_main_skill(record.mainSkill, main_skill),
            "authoringCoherence": coherence.to_dict(),
            "managedRuntimeReadiness": managed_runtime.to_dict(),
            "sideEffectPolicy": {"findings": side_effect_findings},
            "runtimeReadiness": {
                "status": "blocked",
                "findingIds": [f"runtime.{item.get('code')}" for item in side_effect_blockers],
                "message": str(side_effect_blockers[0].get("message") or "Side-effect policy is not runtime-ready."),
                "fullBrowserFlowExecuted": False,
            },
            "blockers": [
                ReadinessBlocker(
                    code=f"runtime.{item.get('code')}",
                    message=str(item.get("message") or "Side-effect policy is not runtime-ready."),
                    recoveryCommand=f"verifysignal workflow check validate --alias {alias} --json",
                ).to_dict()
                for item in side_effect_blockers
            ],
        }
        update_validation(project, alias, result)
        _persist_readiness_snapshot(project, alias, result)
        return result
    validation_runtime_values = _validation_runtime_values(record, run_request, alias)
    prepared_document, confirmation_findings, prepared_changed = prepare_run_request_document(
        run_request,
        validation_runtime_values,
    )
    if confirmation_findings:
        blockers = [
            ReadinessBlocker(
                code=str(item["code"]),
                message=str(item.get("message") or "Confirmation placeholder could not be resolved before Core validation."),
                recoveryCommand=str(item.get("recoveryCommand") or f"verifysignal workflow check validate --alias {alias} --json"),
            ).to_dict()
            for item in confirmation_placeholder_blockers(confirmation_findings)
        ]
        result = {
            "schemaVersion": WORKFLOW_VALIDATION_READINESS_SCHEMA,
            "alias": alias,
            "status": "blocked",
            "selectedMainSkill": _selected_main_skill(record.mainSkill, main_skill),
            "authoringCoherence": coherence.to_dict(),
            "managedRuntimeReadiness": managed_runtime.to_dict(),
            "sideEffectPolicy": {"findings": confirmation_findings},
            "runtimeReadiness": {
                "status": "blocked",
                "findingIds": [str(item["code"]) for item in blockers],
                "message": str(blockers[0].get("message") or "Runtime readiness is blocked."),
                "fullBrowserFlowExecuted": False,
            },
            "blockers": blockers,
        }
        update_validation(project, alias, result)
        _persist_readiness_snapshot(project, alias, result)
        return result
    authoring_run_request = (
        write_prepared_run_request(project / ".verifysignal" / "readiness" / alias, f"{alias}-validation", prepared_document)
        if prepared_changed and prepared_document is not None
        else run_request
    )
    result = CoreAdapter(executable=managed_runtime.runtimeCommand, cwd=project).authoring_check(
        authoring_run_request,
        main_skill,
        skills,
        runtime_readiness=runtime_readiness,
        env=environment_values,
        entitlement_receipt=valid_receipt_path(
            api_base_url_for_runtime(managed_runtime, api_base_url),
        ),
    )
    runtime_check = (
        evaluate_runtime_readiness(
            project,
            alias,
            authoring_result=result,
            core_contract=core_contract,
            environment_values=environment_values,
        )
        if runtime_readiness
        else None
    )
    wrapped = {
        "alias": alias,
        "status": result.get("status", "error"),
        "selectedMainSkill": _selected_main_skill(record.mainSkill, main_skill),
        "skillSelectionStatus": "matched",
        "authoringCoherence": coherence.to_dict(),
        "managedRuntimeReadiness": managed_runtime.to_dict(),
        "core": result,
    }
    if environment_warnings:
        wrapped["credentialWarnings"] = environment_warnings
    side_effect = record.sideEffects if isinstance(record.sideEffects, dict) else {}
    if side_effect.get("class") in {"write", "external-notification"}:
        from verifysignal_spec.workflows.write_safety import evaluate_rerun_decision

        wrapped["rerunDecision"] = evaluate_rerun_decision(record, supersede_reviews=load_supersede_reviews(project, alias))
    named_outputs = _named_output_summary(record)
    if named_outputs:
        wrapped["namedOutputs"] = named_outputs
    entitlement_blocker_code = core_entitlement_blocker_code(result)
    if entitlement_blocker_code:
        blocker = RuntimeSetupBlocker(
            code=entitlement_blocker_code,
            message="VerifySignal Core rejected the entitlement receipt for this protected operation.",
            recoveryCommand="Run `verifysignal init --here --integration codex` to unlock or refresh runtime entitlement.",
        )
        wrapped["status"] = "blocked"
        wrapped["blockers"] = [ReadinessBlocker.from_dict(blocker.to_dict()).to_dict()]
    authored_evidence_status = _authored_evidence_coverage_status(coherence.to_dict().get("gateCoverage", []))
    runtime_status = "not-run"
    if runtime_check:
        wrapped["runtimeReadiness"] = runtime_check.to_dict()
        runtime_status = runtime_check.status
        if runtime_check.status != "passed":
            wrapped["status"] = "blocked"
            wrapped["blockers"] = [
                ReadinessBlocker(
                    code=finding,
                    message=runtime_check.message or "Runtime readiness is blocked.",
                    recoveryCommand=f"verifysignal workflow check validate --alias {alias} --json",
                ).to_dict()
                for finding in runtime_check.findingIds
            ]
    summary = ValidationReadinessSummary(
        alias=alias,
        status="blocked" if wrapped.get("status") == "blocked" else ("passed" if wrapped.get("status") == "passed" else "failed"),
        skillSelectionStatus="matched",
        authoringCoherenceStatus=coherence.status,
        authoredEvidenceCoverageStatus=authored_evidence_status,
        runtimeReadinessStatus=runtime_status,
        fullBrowserFlowExecuted=False,
        nextAction=f"verifysignal run {alias} --json" if wrapped.get("status") == "passed" else f"verifysignal workflow check validate --alias {alias} --json",
    )
    wrapped.update(summary.to_dict())
    wrapped["readinessSummary"] = _readiness_summary_text(summary)
    update_validation(project, alias, wrapped)
    guided_stage = None
    if summary.status == "passed":
        guided_stage = advance_guided_first_run_state(
            project,
            alias,
            stage="running",
            first_run_status="running",
            resume_command=f"verifysignal run {alias} --json",
            summary=f"{alias} validation readiness passed; the first browser run is ready.",
        )
    elif summary.status == "blocked":
        guided_stage = advance_guided_first_run_state(
            project,
            alias,
            stage="blocked",
            first_run_status="blocked",
            resume_command=summary.nextAction,
            summary=f"{alias} validation readiness is blocked.",
            status_marker="[BLOCKED]",
            blocker={"category": "validation-readiness", "requiredAction": summary.nextAction, "resumeCommand": summary.nextAction},
        )
    if guided_stage:
        wrapped["guidedFirstRunState"] = guided_stage
    _persist_readiness_snapshot(project, alias, wrapped)
    return wrapped


def _persist_readiness_snapshot(project: Path, alias: str, result: dict[str, Any]) -> None:
    try:
        create_readiness_snapshot_from_validation(project, alias, result)
    except Exception:
        # Readiness snapshots are advisory local metadata; validation output remains authoritative.
        pass


def _structural_guided_blockers(findings: list[dict[str, Any]], alias: str) -> list[dict[str, Any]]:
    guided: list[dict[str, Any]] = []
    for item in findings:
        if item.get("severity") != "blocking":
            continue
        if item.get("category") not in {"side-effect-confirmation", "generated-binding"}:
            continue
        code = str(item.get("code") or "workspace.structural-finding")
        guided.append(
            ReadinessBlocker(
                code=f"runtime.{code}",
                message=str(item.get("message") or "Workspace structure is blocked."),
                recoveryCommand=str(item.get("recoveryCommand") or f"verifysignal workflow check validate --alias {alias} --json"),
            ).to_dict()
        )
    return guided


def _named_output_summary(record: Any) -> list[dict[str, Any]]:
    outputs: list[dict[str, Any]] = []
    for item in getattr(record, "runtimeOutputs", []) or []:
        if not isinstance(item, dict) or not item.get("publishAsNamedOutput"):
            continue
        data = {"name": str(item.get("name") or ""), "source": str(item.get("source") or "")}
        if item.get("resourceType"):
            data["resourceType"] = str(item.get("resourceType"))
        outputs.append({key: value for key, value in data.items() if value})
    return outputs


def _validation_runtime_values(record: Any, run_request: Path, alias: str) -> dict[str, Any]:
    from verifysignal_spec.commands.runtime_inputs import resolve_runtime_inputs
    from verifysignal_spec.core.errors import RuntimeInputError

    values = _run_request_parameters(run_request)
    try:
        resolved = resolve_runtime_inputs(
            record.runtimeInputs,
            interactive=False,
            provided=values,
            run_id=f"{alias}-validation",
            refresh_names=[item.name for item in record.runtimeInputs if item.source == "generated" and item.refreshOnRerunAfterCommit],
        )
        return {**values, **resolved}
    except RuntimeInputError:
        pass

    for item in getattr(record, "runtimeInputs", []):
        if getattr(item, "kind", "") == "credential" or getattr(item, "name", "") in values:
            continue
        if getattr(item, "source", "") == "generated":
            try:
                values.update(
                    resolve_runtime_inputs(
                        [item],
                        interactive=False,
                        run_id=f"{alias}-validation",
                        refresh_names=[item.name],
                    )
                )
            except RuntimeInputError:
                continue
        elif getattr(item, "value", None) not in {None, ""}:
            values[item.name] = item.value
        elif getattr(item, "default", None) not in {None, ""}:
            values[item.name] = item.default
    return values


def _run_request_parameters(run_request: Path) -> dict[str, Any]:
    from verifysignal_spec.workspace.repository import load_document

    data = load_document(run_request, default={}) or {}
    if not isinstance(data, dict):
        return {}
    parameters = data.get("parameters")
    return dict(parameters) if isinstance(parameters, dict) else {}


def _authored_evidence_coverage_status(gate_coverage: list[dict[str, Any]]) -> str:
    if not gate_coverage:
        return "not-applicable"
    incomplete = {"missing", "network-only", "screenshot-only", "unmapped", "not-evaluated", "incomplete"}
    if any(item.get("required", True) and item.get("status") in incomplete for item in gate_coverage):
        return "incomplete"
    return "complete"


def _readiness_summary_text(summary: ValidationReadinessSummary) -> str:
    if summary.status == "passed":
        return (
            "Validation readiness passed: required gates have mapped authored evidence, "
            f"runtime readiness is {summary.runtimeReadinessStatus}, and the full browser flow has not executed yet. "
            f"Next action: {summary.nextAction}."
        )
    return (
        "Validation readiness did not pass. Review structural validation, authoring coherence, "
        "runtime readiness, and mapped authored evidence before running the browser flow."
    )
