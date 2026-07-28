from __future__ import annotations

from pathlib import Path
from typing import Any

from verifysignal_spec.core.adapter import CoreAdapter
from verifysignal_spec.core.contracts import public_contract_summary
from verifysignal_spec.core.errors import CoreExecutionError, CoreIncompatibleError, CoreMissingError
from verifysignal_spec.core.executable_contract import project_core_contract
from verifysignal_spec.runtime.resolver import ensure_core_runtime
from verifysignal_spec.workspace import layout
from verifysignal_spec.workspace.models import ArtifactCapabilityPolicy
from verifysignal_spec.workspace.repository import load_document, load_use_case
from verifysignal_spec.workspace.validation import validate_use_case, validate_workspace

from .migration import migration_plans
from .models import (
    WORKFLOW_CAPABILITY_SCHEMA,
    WORKFLOW_GUARDRAILS_CAPABILITY,
    WORKFLOW_VALIDATION_READINESS_SCHEMA,
    CoreReadiness,
    ReadinessBlocker,
    StructuralWorkspaceValidation,
)
from .skill_execution_boundary import resolve_execution_boundary


REQUIRED_AUTHORING_GUARDRAILS = {
    "degenerate-text-target",
    "unstable-generated-css-target",
}


def validation_readiness(project: Path, alias: str | None = None, core_cmd: str | None = None) -> dict[str, Any]:
    structural = structural_validation(project, alias=alias)
    core = core_readiness(project, core_cmd=core_cmd)
    contract_blockers = executable_contract_blockers(project, core.coreCommand, alias=alias) if core.status == "available" else []
    blockers = [*_blockers(structural, core), *contract_blockers]
    status = "blocked" if contract_blockers else _overall_status(structural, core)
    runtime_readiness_command = f"verifysignal validate {alias or '<alias>'} --runtime-readiness --json"
    blocker_recovery = next(
        (
            blocker.recoveryCommand
            for blocker in blockers
            if blocker.recoveryCommand
        ),
        None,
    )
    if status == "blocked":
        readiness_summary = (
            "Structural readiness is blocked and must be resolved first. "
            "Protected runtime and entitlement readiness have not run."
        )
    else:
        readiness_summary = (
            "Structural readiness passed. "
            "Protected runtime and entitlement readiness have not run."
        )
    return {
        "schemaVersion": WORKFLOW_VALIDATION_READINESS_SCHEMA,
        "capabilitySchemaVersion": WORKFLOW_CAPABILITY_SCHEMA,
        "requiredCapability": WORKFLOW_GUARDRAILS_CAPABILITY,
        "supported": True,
        "stage": "validate",
        "alias": alias,
        "status": status,
        "readinessScope": "structural",
        "runtimeReadinessRequired": True,
        "runtimeReadinessStatus": "not-run",
        "runtimeReadinessCommand": runtime_readiness_command,
        "nextAction": blocker_recovery or runtime_readiness_command,
        "readinessSummary": readiness_summary,
        "structuralValidation": structural.to_dict(),
        "coreReadiness": core.to_dict(),
        "blockers": [blocker.to_dict() for blocker in blockers],
    }


def default_capability_policies() -> list[ArtifactCapabilityPolicy]:
    return [
        ArtifactCapabilityPolicy(
            capability="explicit-confirmation",
            appliesTo=["write", "external-notification"],
            severityWhenMissing="confirmation",
            safetyCritical=True,
            migrationGuidance="Re-persist or migrate the artifact so risky write runs expose structured confirmation requirements.",
        ),
        ArtifactCapabilityPolicy(
            capability="side-effect-lifecycle",
            appliesTo=["write", "external-notification"],
            severityWhenMissing="confirmation",
            safetyCritical=True,
            migrationGuidance="Declare cleanup policy, tracking intent, and manual/external cleanup instructions where needed.",
        ),
        ArtifactCapabilityPolicy(
            capability="generated-runtime-inputs",
            appliesTo=["write"],
            severityWhenMissing="warning",
            safetyCritical=True,
            migrationGuidance="Declare generated per-run identity inputs for resource-creating flows.",
        ),
        ArtifactCapabilityPolicy(
            capability="write-activity-interpretation",
            appliesTo=["write", "external-notification"],
            severityWhenMissing="confirmation",
            safetyCritical=True,
            migrationGuidance="Migrate artifacts so write activity is reported conservatively when Core side-effect envelopes are unavailable.",
        ),
    ]


def structural_validation(project: Path, alias: str | None = None) -> StructuralWorkspaceValidation:
    findings = validate_workspace(project)
    checked = [f"{layout.WORKSPACE_DIR}/{layout.REGISTRY_FILE}"]
    if alias:
        checked.append(f"{layout.WORKSPACE_DIR}/{layout.USE_CASES_DIR}/{alias}.yaml")
        try:
            from verifysignal_spec.workspace.repository import load_use_case

            record = load_use_case(project, alias)
            findings.extend(validate_use_case(project, record))
            if record.runRequest:
                checked.append(record.runRequest.path)
            checked.extend(skill.path for skill in [*record.skills, *record.sourceOnlySkills])
        except Exception as exc:
            findings.append(
                {
                    "severity": "blocking",
                    "code": "missing-or-invalid-use-case-record",
                    "path": f"{layout.WORKSPACE_DIR}/{layout.USE_CASES_DIR}/{alias}.yaml",
                    "message": str(exc),
                }
            )
    plans = migration_plans(project, alias=alias)
    if plans:
        findings.append(
            {
                "severity": "blocking",
                "code": "migration-required",
                "path": f"{layout.WORKSPACE_DIR}/{layout.REGISTRY_FILE}",
                "message": "Recoverable malformed workspace artifacts require approved migration before validation.",
            }
        )
    if any(item.get("severity") == "blocking" for item in findings):
        status = "blocked"
    elif findings:
        status = "warning"
    else:
        status = "pass"
    return StructuralWorkspaceValidation(status=status, findings=findings, checkedArtifacts=checked, migrationPlans=plans)


def core_readiness(project: Path, core_cmd: str | None = None) -> CoreReadiness:
    contract = public_contract_summary()
    runtime = ensure_core_runtime(project, explicit_core_cmd=core_cmd, context="validate")
    if runtime.status == "ready":
        return CoreReadiness(
            status="available",
            coreCommand=runtime.runtimeCommand,
            version=runtime.runtimeVersion,
            contractVersion=runtime.contractVersion or contract["contractVersion"],
            requiredOperations=contract["requiredOperations"],
            missingOperations=[],
            message="VerifySignal Core is available for complete validation and browser execution.",
        )

    blocker = runtime.blockers[0] if runtime.blockers else None
    blocker_code = blocker.code if blocker else ""
    message = runtime.message or (blocker.message if blocker else "VerifySignal Core failed readiness check.")
    command = runtime.runtimeCommand or _last_attempt_command(runtime.attempts) or core_cmd
    if blocker_code == "core.missing":
        return CoreReadiness(
            status="missing",
            coreCommand=command,
            contractVersion=contract["contractVersion"],
            requiredOperations=contract["requiredOperations"],
            message=(
                f"{message} Structural workspace validation can still run, but VerifySignal Core is required "
                "for the complete VerifySignal validation and browser execution experience."
            ),
        )
    if blocker_code == "core.incompatible" or runtime.status == "incompatible":
        compatibility = _compatibility_for_selected_command(project, command)
        if compatibility:
            return compatibility
        return CoreReadiness(
            status="incompatible",
            coreCommand=command,
            version=runtime.runtimeVersion,
            contractVersion=runtime.contractVersion or contract["contractVersion"],
            requiredOperations=contract["requiredOperations"],
            missingOperations=runtime.missingOperations,
            incompatibleOperations=runtime.incompatibleOperations,
            message=message,
        )
    return CoreReadiness(status="error", coreCommand=command, requiredOperations=contract["requiredOperations"], message=message)


def executable_contract_blockers(
    project: Path,
    core_command: str | None,
    *,
    alias: str | None = None,
    core_contract: dict[str, Any] | None = None,
) -> list[ReadinessBlocker]:
    if not core_command and core_contract is None:
        return [
            ReadinessBlocker(
                code="core-contract.bootstrap-incompatible",
                message="VerifySignal Core command is unavailable, so the public executable contract cannot be discovered.",
                repairable=False,
                documentationRef="coreExecutableContract",
            )
        ]
    projection = core_contract
    if projection is None:
        adapter = CoreAdapter(executable=str(core_command), cwd=project)
        try:
            raw = adapter.contracts()
        except CoreIncompatibleError as exc:
            return [
                ReadinessBlocker(
                    code="core-contract.bootstrap-incompatible",
                    message=str(exc),
                    repairable=False,
                    documentationRef="coreExecutableContract",
                )
            ]
        except (CoreMissingError, CoreExecutionError) as exc:
            return [
                ReadinessBlocker(
                    code="core-contract.discovery-failed",
                    message=str(exc),
                    repairable=False,
                    documentationRef="coreExecutableContract",
                )
            ]
        projection = project_core_contract(raw)
    blockers: list[ReadinessBlocker] = []
    for finding in projection.get("findings", []):
        if finding.get("severity") != "blocking":
            continue
        blockers.append(
            ReadinessBlocker(
                code=str(finding.get("code") or "core-contract.incompatible"),
                message=str(finding.get("message") or "Core executable contract is incompatible."),
                repairable=False,
                documentationRef="coreExecutableContract",
            )
        )
    browser = projection.get("sections", {}).get("browserWorkflow", {})
    warnings = browser.get("authoringWarnings", []) if isinstance(browser, dict) else []
    blocking_warning_codes = {
        str(item.get("code"))
        for item in warnings
        if isinstance(item, dict) and item.get("runtimeReadinessSeverity") == "blocking"
    }
    missing_guardrails = sorted(REQUIRED_AUTHORING_GUARDRAILS - blocking_warning_codes)
    if missing_guardrails:
        blockers.append(
            ReadinessBlocker(
                code="core.authoring-guardrails-outdated",
                category="core-contract",
                message=(
                    "VerifySignal Core does not announce the required browser authoring guardrails: "
                    f"{', '.join(missing_guardrails)}."
                ),
                recoveryCommand="verifysignal core setup --json",
                repairable=False,
                documentationRef="coreExecutableContract.sections.browserWorkflow.authoringWarnings",
            )
        )
    if alias:
        blockers.extend(execution_boundary_blockers(project, alias, core_contract=projection))
    return blockers


def execution_boundary_blockers(project: Path, alias: str, *, core_contract: dict[str, Any] | None = None) -> list[ReadinessBlocker]:
    try:
        record = load_use_case(project, alias)
    except Exception:
        return []
    run_request = None
    if record.runRequest:
        run_request = load_document(project / record.runRequest.path, default={}) or {}
    decision = resolve_execution_boundary(record, core_contract=core_contract, run_request=run_request)
    blockers: list[ReadinessBlocker] = []
    for finding in decision.findings:
        if finding.get("severity") != "blocking":
            continue
        blockers.append(
            ReadinessBlocker(
                code=str(finding.get("code") or "skill-execution.boundary-blocked"),
                category="skill-execution-boundary",
                message=str(finding.get("message") or "Skill execution boundary is blocked."),
                recoveryCommand=f"verifysignal workflow persist implement --alias {alias} --payload <payload.json> --json",
                repairable=bool(finding.get("repairable", True)),
                documentationRef="coreExecutableContract.sections.skillExecution",
            )
        )
    return blockers


def legacy_executable_artifact_blockers(run_request: Path, main_skill: Path, skills: list[Path]) -> list[ReadinessBlocker]:
    blockers: list[ReadinessBlocker] = []
    expected = {
        run_request: "qa-run-request/v1",
        main_skill: "qa-skill/v1",
        **{skill: "qa-skill/v1" for skill in skills},
    }
    for path, expected_schema in expected.items():
        schema = _artifact_schema_version(path)
        if schema and schema != expected_schema:
            blockers.append(
                ReadinessBlocker(
                    code="core-contract.legacy-artifact",
                    message=f"Executable artifact {path} uses schemaVersion {schema!r}; expected {expected_schema!r} from the Core public contract.",
                    repairable=False,
                    documentationRef="coreExecutableContract.sections.runRequest/skill",
                )
            )
    return blockers


def managed_runtime_contract_blockers(runtime: Any) -> list[ReadinessBlocker]:
    missing_operations = set(getattr(runtime, "missingOperations", []) or [])
    runtime_command = getattr(runtime, "runtimeCommand", None)
    if "contracts" not in missing_operations and runtime_command:
        try:
            compatibility = CoreAdapter(executable=runtime_command).check_compatibility()
            missing_operations.update(compatibility.missingOperations or [])
        except Exception:
            pass
    if "contracts" not in missing_operations:
        return []
    return [
        ReadinessBlocker(
            code="core-contract.bootstrap-incompatible",
            message="VerifySignal Core does not advertise the required public `contracts` operation.",
            repairable=False,
            documentationRef="coreExecutableContract",
        )
    ]


def _artifact_schema_version(path: Path) -> str | None:
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return None
    try:
        import yaml  # type: ignore

        parsed = yaml.safe_load(text) or {}
    except Exception:
        try:
            import json

            parsed = json.loads(text)
        except Exception:
            return None
    if isinstance(parsed, dict) and parsed.get("schemaVersion"):
        return str(parsed["schemaVersion"])
    return None


def _compatibility_for_selected_command(project: Path, command: str | None) -> CoreReadiness | None:
    if not command:
        return None
    contract = public_contract_summary()
    try:
        adapter = CoreAdapter(executable=command, cwd=project)
        compatible = adapter.check_compatibility()
        if not compatible.compatible:
            return CoreReadiness(
                status="incompatible",
                coreCommand=adapter.executable,
                version=compatible.verifysignalVersion,
                contractVersion=compatible.contractVersion or contract["contractVersion"],
                requiredOperations=contract["requiredOperations"],
                missingOperations=compatible.missingOperations or [],
                incompatibleOperations=compatible.incompatibleOperations or [],
                recoveryAction=compatible.recoveryAction,
                message=compatible.message,
            )
        return None
    except CoreIncompatibleError as exc:
        return CoreReadiness(status="incompatible", coreCommand=command, requiredOperations=contract["requiredOperations"], message=str(exc))
    except (CoreMissingError, CoreExecutionError):
        return None
    except Exception:
        return None


def _last_attempt_command(attempts: list[Any]) -> str | None:
    for attempt in reversed(attempts):
        command = getattr(attempt, "command", None)
        if command:
            return str(command)
    return None


def _blockers(structural: StructuralWorkspaceValidation, core: CoreReadiness) -> list[ReadinessBlocker]:
    blockers: list[ReadinessBlocker] = []
    if structural.status == "blocked":
        blockers.append(
            ReadinessBlocker(
                code="workspace.structural-blocked",
                message="Workspace structure is blocked. Review structuralValidation.findings and apply approved migrations when offered.",
                recoveryCommand="verifysignal workflow check validate --json",
            )
        )
    if core.status == "missing":
        blockers.append(
            ReadinessBlocker(
                code="core.missing",
                category="environment",
                message="VerifySignal Core is not configured or could not be found. Core setup is required for complete validation and browser execution.",
                recoveryCommand="verifysignal core setup --json",
                repairable=False,
            )
        )
    elif core.status == "incompatible":
        blockers.append(
            ReadinessBlocker(
                code="core.incompatible",
                message=core.message or "VerifySignal Core is incompatible with the required public contract.",
                recoveryCommand="verifysignal core version --json",
            )
        )
    elif core.status == "error":
        blockers.append(ReadinessBlocker(code="core.error", message=core.message or "VerifySignal Core failed readiness check."))
    return blockers


def _overall_status(structural: StructuralWorkspaceValidation, core: CoreReadiness) -> str:
    if structural.status == "blocked":
        return "blocked"
    if core.status == "available":
        return "ready" if structural.status == "pass" else "warning"
    if structural.status == "pass":
        return "blocked"
    return "blocked"
