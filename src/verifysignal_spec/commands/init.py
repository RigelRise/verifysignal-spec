from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from verifysignal_spec.commands.integration import install as install_integration
from verifysignal_spec.core.adapter import readiness, resolve_persistable_core_command
from verifysignal_spec.language import ConversationLanguage, detect_system_language
from verifysignal_spec.core.contracts import PUBLIC_CONTRACT_VERSION
from verifysignal_spec.runtime.entitlement import resolve_entitlement_config
from verifysignal_spec.runtime.models import ManagedRuntimeReadinessResult, RuntimeSourceAttempt
from verifysignal_spec.runtime.resolver import ensure_core_runtime
from verifysignal_spec.workflows.models import CoreCandidateAttempt, CoreSetupResult
from verifysignal_spec.workflows.core_setup import run_core_setup
from verifysignal_spec.workspace import layout
from verifysignal_spec.workspace.repository import (
    get_conversation_language,
    init_workspace,
    load_document,
    save_core_configuration,
)
from verifysignal_spec.integrations.invocation import native_invocation

CORE_SETUP_ATTEMPT_SOURCES = {"explicit", "workspace", "env", "path", "ancestor-sibling"}


def run(
    project: Path,
    integration: str,
    force: bool = False,
    core_cmd: str | None = None,
    api_base_url: str | None = None,
    language: str | None = None,
) -> dict[str, Any]:
    workspace_file_existed = (layout.workspace_root(project) / layout.WORKSPACE_FILE).exists()
    entitlement_config = resolve_entitlement_config(api_base_url=api_base_url)
    persisted_api_base_url = entitlement_config.apiBaseUrl if api_base_url or entitlement_config.source == "environment" else None
    workspace_path = layout.workspace_root(project) / layout.WORKSPACE_FILE
    workspace_preexisting = workspace_path.exists()
    if core_cmd and workspace_preexisting:
        workspace = load_document(workspace_path, default={}) or {}
    else:
        workspace = init_workspace(
            project,
            force=False,
            api_base_url=persisted_api_base_url,
        )
    email = os.environ.get("VERIFYSIGNAL_EMAIL")
    token = os.environ.get("VERIFYSIGNAL_EMAIL_UNLOCK_TOKEN")
    if not token and not email and sys.stdin.isatty():
        email = _prompt("VerifySignal email for runtime unlock: ").strip() or None
    runtime = ensure_core_runtime(
        project,
        explicit_core_cmd=core_cmd,
        api_base_url=persisted_api_base_url,
        email=email,
        token=token,
        integration=integration,
        context="init",
    )
    delivery_pending = (
        runtime.entitlement.status == "token-delivery-pending"
    )
    if (
        runtime.status != "ready"
        and delivery_pending
        and email
        and not token
        and sys.stdin.isatty()
    ):
        token = _prompt(
            "VerifySignal email unlock token "
            "(press Enter if it did not arrive): "
        ).strip() or None
        if token:
            runtime = ensure_core_runtime(
                project,
                explicit_core_cmd=core_cmd,
                api_base_url=persisted_api_base_url,
                token=token,
                integration=integration,
                context="init",
            )
    workspace_core_cmd = None
    if core_cmd and runtime.status == "ready":
        workspace_core_cmd = resolve_persistable_core_command(runtime.runtimeCommand or core_cmd, cwd=project)
        runtime.runtimeCommand = workspace_core_cmd
    if runtime.status == "ready":
        core_setup = run_core_setup(project, explicit_core_cmd=runtime.runtimeCommand, persist=False)
    else:
        core_setup = _core_setup_from_blocked_runtime(runtime)
    if core_cmd and workspace_core_cmd and runtime.status == "ready" and core_setup.status == "ready":
        workspace = save_core_configuration(
            project,
            workspace_core_cmd,
            source="explicit",
            version=core_setup.version or runtime.runtimeVersion,
            api_base_url=persisted_api_base_url,
        )
    resolved_language, persist_language = _resolve_conversation_language(
        project, language, fresh_workspace=not workspace_file_existed
    )
    installed = install_integration(
        project,
        integration,
        force=force,
        default=True,
        language=resolved_language,
        persist_language=persist_language,
    )
    mcp = installed.get("mcp")
    mcp_runtime = (
        mcp.get("runtime")
        if isinstance(mcp, dict)
        else None
    )
    mcp_registration = (
        mcp.get("userRegistration")
        if isinstance(mcp, dict)
        else None
    )
    mcp_blocked = bool(
        (
            isinstance(mcp_runtime, dict)
            and mcp_runtime.get("status") == "blocked"
        )
        or (
            isinstance(mcp_registration, dict)
            and mcp_registration.get("status") == "blocked"
        )
    )
    if runtime.status == "ready":
        core = readiness(executable=runtime.runtimeCommand, cwd=project)
    else:
        core = {
            "available": False,
            "compatible": False,
            "message": runtime.message,
            "missingOperations": runtime.missingOperations,
            "incompatibleOperations": runtime.incompatibleOperations,
        }
    return {
        "status": (
            "passed"
            if runtime.status == "ready" and not mcp_blocked
            else "blocked"
        ),
        "workspacePath": str(project / ".verifysignal"),
        "workspace": workspace,
        "integration": installed["integration"]["key"],
        "installedFiles": installed["installedFiles"],
        "conversationLanguage": resolved_language.code if resolved_language else None,
        "conversationLanguageSource": resolved_language.source if resolved_language else "none",
        "mcp": mcp,
        "coreSetup": core_setup.to_dict(),
        "runtime": runtime.to_dict(),
        "managedRuntimeReadiness": runtime.to_dict(),
        "core": core,
        "next": (
            str(
                (
                    mcp_registration
                    if (
                        isinstance(mcp_registration, dict)
                        and mcp_registration.get("status") == "blocked"
                    )
                    else mcp_runtime
                ).get("nextAction")
            )
            if mcp_blocked
            else (
                f"Run `{native_invocation('specify', integration)}` in your "
                "agent, or use `verifysignal workflow run "
                'verifysignal-use-case --goal "<behavior>"`.'
            )
        ),
    }


def _resolve_conversation_language(
    project: Path, flag_code: str | None, *, fresh_workspace: bool
) -> tuple[ConversationLanguage | None, bool]:
    """Resolve flag > persisted > detected > none; return (language, persist?).

    Detection runs only for a brand-new workspace: a re-init must never mutate an
    existing workspace.yaml with this machine's locale (failed re-inits are
    contractually byte-preserving), and an existing project keeps rendering the
    same files on every machine.
    """
    if flag_code:
        return ConversationLanguage(flag_code, "flag"), True
    stored = get_conversation_language(project)
    if stored:
        return ConversationLanguage(stored["code"], stored["source"]), False
    if fresh_workspace:
        detected = detect_system_language()
        if detected:
            return ConversationLanguage(detected, "detected"), True
    return None, False


def _prompt(message: str) -> str:
    sys.stderr.write(message)
    sys.stderr.flush()
    return input()


def _core_setup_from_blocked_runtime(runtime: ManagedRuntimeReadinessResult) -> CoreSetupResult:
    blocker_codes = {blocker.code for blocker in runtime.blockers}
    if "core.missing" in blocker_codes:
        status = "missing"
    elif "core.incompatible" in blocker_codes or runtime.status == "incompatible":
        status = "incompatible"
    else:
        status = "error"
    blocker = runtime.blockers[0] if runtime.blockers else None
    return CoreSetupResult(
        status=status,  # type: ignore[arg-type]
        coreCommand=runtime.runtimeCommand,
        contractVersion=runtime.contractVersion or PUBLIC_CONTRACT_VERSION,
        attempts=[_core_setup_attempt_from_runtime_attempt(attempt) for attempt in runtime.attempts if attempt.source in CORE_SETUP_ATTEMPT_SOURCES],
        message=runtime.message,
        nextAction=runtime.nextAction,
        recoveryCommand=(blocker.recoveryCommand if blocker else runtime.nextAction) or "verifysignal core setup --json",
    )


def _core_setup_attempt_from_runtime_attempt(attempt: RuntimeSourceAttempt) -> CoreCandidateAttempt:
    status = attempt.status if attempt.status in {"missing", "available", "compatible", "incompatible", "error", "skipped"} else "error"
    return CoreCandidateAttempt(
        source=attempt.source,  # type: ignore[arg-type]
        command=attempt.command or "",
        status=status,  # type: ignore[arg-type]
        terminal=attempt.terminal,
        version=attempt.runtimeVersion,
        message=attempt.message,
    )
