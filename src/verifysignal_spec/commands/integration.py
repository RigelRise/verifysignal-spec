from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from verifysignal_spec.integrations.claude import ClaudeIntegration
from verifysignal_spec.integrations.codex import CodexIntegration
from verifysignal_spec.integrations.base import build_onboarding_guidance
from verifysignal_spec.integrations.manifests import install_rendered_files, load_all_states, remove_integration, set_default
from verifysignal_spec.integrations.invocation import native_invocation
from verifysignal_spec.integrations.mcp import (
    AGENT_MCP_AUTO_REGISTER_ENV,
    configure_mcp_servers,
    ensure_playwright_mcp_runtime,
    register_agent_user_mcp,
    run_playwright_mcp,
)
from verifysignal_spec.runtime.resolver import ensure_core_runtime
from verifysignal_spec.workspace.repository import get_core_configuration
from verifysignal_spec.workflows.core_setup import onboarding_core_status, run_core_setup

INTEGRATIONS = {
    "codex": CodexIntegration,
    "claude": ClaudeIntegration,
}


def playwright_mcp() -> int:
    return run_playwright_mcp()


def setup_playwright_mcp() -> dict[str, Any]:
    return ensure_playwright_mcp_runtime()


def get_integration(key: str):
    if key not in INTEGRATIONS:
        raise ValueError(f"Unsupported integration: {key}")
    return INTEGRATIONS[key]()


def install(project: Path, key: str, force: bool = False, default: bool = True) -> dict[str, Any]:
    integration = get_integration(key)
    runtime = ensure_core_runtime(project, context="integration")
    core_setup_result = run_core_setup(project, persist=False)
    core_setup = core_setup_result.to_dict()
    core_status = _runtime_onboarding_status(runtime.to_dict(), integration.key) if runtime.source in {"managed-cache", "managed-download"} else onboarding_core_status(core_setup_result)
    state = install_rendered_files(
        project,
        integration.key,
        integration.display_name,
        integration.invoke_style,
        integration.render_files(project, core_status=core_status),
        force=force,
        default=default,
    )
    mcp = _configure_integration_mcp(project, integration)
    guide_path = ".agents/VERIFYSIGNAL_ONBOARDING.md" if integration.key == "codex" else ".claude/VERIFYSIGNAL_ONBOARDING.md"
    guide = build_onboarding_guidance(
        integration_key=integration.key,
        display_name=integration.display_name,
        generated_guide_path=guide_path,
        core_status=core_status,
    ).to_dict()
    return {
        "status": (
            "blocked"
            if isinstance(mcp, dict) and mcp.get("status") == "blocked"
            else "ready"
        ),
        "integration": state.to_dict(),
        "installedFiles": [item.path for item in state.managedFiles],
        "coreSetup": core_setup,
        "runtime": runtime.to_dict(),
        "managedRuntimeReadiness": runtime.to_dict(),
        "onboardingGuide": guide,
        "mcp": mcp,
    }


def _configure_integration_mcp(project: Path, integration) -> dict[str, Any] | None:
    # Keep the project entry as a compatibility fallback, then register the
    # same managed launcher in user scope through the host's public MCP CLI.
    # A user-owned project or user entry is never overwritten.
    servers = integration.mcp_servers()
    if not servers:
        return None
    try:
        mcp = configure_mcp_servers(
            project,
            integration.key,
            str(integration.mcp_config_format),
            servers,
        )
    except OSError as exc:
        path = (
            ".codex/config.toml"
            if integration.mcp_config_format == "codex-toml"
            else ".mcp.json"
        )
        mcp = {
            "path": path,
            "integrationKey": integration.key,
            "format": integration.mcp_config_format,
            "skipped": True,
            "reason": f"could not write {path}: {exc}",
            "nodeAvailable": False,
        }
    if isinstance(mcp, dict) and "playwright" in servers:
        if (
            os.environ.get(
                "VERIFYSIGNAL_PLAYWRIGHT_MCP_AUTO_INSTALL",
                "1",
            )
            == "0"
        ):
            provider_runtime = {
                "status": "skipped",
                "source": "auto-install-disabled",
                "offlineReady": False,
                "nextAction": (
                    "verifysignal integration "
                    "setup-playwright-mcp --json"
                ),
            }
        else:
            provider_runtime = ensure_playwright_mcp_runtime()
        mcp["runtime"] = provider_runtime
        if provider_runtime.get("status") == "blocked":
            mcp.setdefault("warnings", []).append(
                str(
                    provider_runtime.get("message")
                    or "Playwright MCP provider setup failed."
                )
            )
        if (
            os.environ.get(AGENT_MCP_AUTO_REGISTER_ENV, "1")
            == "0"
        ):
            user_registration = {
                "status": "skipped",
                "scope": "user",
                "integrationKey": integration.key,
                "serverName": "playwright",
                "source": "auto-registration-disabled",
                "added": [],
                "preserved": [],
                "managedServers": [],
                "unchanged": False,
                "nextAction": None,
            }
        else:
            user_registration = register_agent_user_mcp(
                integration.key
            )
        mcp["userRegistration"] = user_registration
        if user_registration.get("status") == "blocked":
            mcp.setdefault("warnings", []).append(
                str(
                    user_registration.get("message")
                    or "Agent user-scope MCP registration failed."
                )
            )
        mcp["status"] = (
            "blocked"
            if (
                provider_runtime.get("status") == "blocked"
                or user_registration.get("status") == "blocked"
            )
            else "ready"
        )
    return mcp


def list_integrations(project: Path) -> dict[str, Any]:
    state = load_all_states(project)
    installed = state.get("integrations", {})
    return {
        "available": [{"key": key, "displayName": cls.display_name} for key, cls in INTEGRATIONS.items()],
        "installed": installed,
    }


def use(project: Path, key: str) -> dict[str, Any]:
    set_default(project, key)
    return {"default": key}


def upgrade(project: Path, key: str | None = None, force: bool = False) -> dict[str, Any]:
    keys = [key] if key else list(INTEGRATIONS)
    installed = load_all_states(project).get("integrations", {})
    results = []
    for item in keys:
        previous = installed.get(item)
        was_default = bool(
            isinstance(previous, dict) and previous.get("default")
        )
        results.append(
            _upgrade_without_core_resolution(
                project,
                item,
                force=force,
                default=was_default,
            )
        )
    return {
        "status": (
            "blocked"
            if any(result.get("status") == "blocked" for result in results)
            else "ready"
        ),
        "upgraded": results,
    }


def _upgrade_without_core_resolution(
    project: Path,
    key: str,
    *,
    force: bool,
    default: bool = False,
) -> dict[str, Any]:
    integration = get_integration(key)
    stored = get_core_configuration(project)
    source = stored.get("coreCommandSource")
    core_status = {
        "statusMarker": "[NOT CHECKED]",
        "summary": "Core readiness was not checked during integration upgrade.",
        "source": source,
        "coreCommand": None,
        "selectedCandidate": None,
        "nextAction": "Run `verifysignal core version --json` when runtime readiness is needed.",
        "guideText": "Integration files were regenerated without resolving or changing the active Core runtime.",
    }
    state = install_rendered_files(
        project,
        integration.key,
        integration.display_name,
        integration.invoke_style,
        integration.render_files(project, core_status=core_status),
        force=force,
        default=default,
    )
    mcp = _configure_integration_mcp(project, integration)
    not_checked = {
        "status": "not-checked",
        "source": source,
        "message": "Integration upgrade does not resolve or set up Core.",
    }
    guide_path = (
        ".agents/VERIFYSIGNAL_ONBOARDING.md"
        if integration.key == "codex"
        else ".claude/VERIFYSIGNAL_ONBOARDING.md"
    )
    guide = build_onboarding_guidance(
        integration_key=integration.key,
        display_name=integration.display_name,
        generated_guide_path=guide_path,
        core_status=core_status,
    ).to_dict()
    return {
        "status": (
            "blocked"
            if isinstance(mcp, dict) and mcp.get("status") == "blocked"
            else "ready"
        ),
        "integration": state.to_dict(),
        "installedFiles": [item.path for item in state.managedFiles],
        "coreSetup": dict(not_checked),
        "runtime": dict(not_checked),
        "managedRuntimeReadiness": dict(not_checked),
        "onboardingGuide": guide,
        "mcp": mcp,
    }


def remove(project: Path, key: str, force: bool = False) -> dict[str, Any]:
    preserved = remove_integration(project, key, force=force)
    return {"removed": key, "preserved": preserved}


def _runtime_onboarding_status(
    runtime: dict[str, Any],
    integration_key: str,
) -> dict[str, Any]:
    if runtime.get("status") == "ready":
        return {
            "statusMarker": "[READY]",
            "summary": "VerifySignal runtime is ready.",
            "source": runtime.get("source"),
            "coreCommand": runtime.get("runtimeCommand"),
            "selectedCandidate": None,
            "nextAction": (
                f"Continue with {native_invocation('specify', integration_key)}."
            ),
            "guideText": "VerifySignal runtime is ready. Validation and browser execution can use the verified runtime automatically.",
        }
    return {
        "statusMarker": "[BLOCKED]",
        "summary": runtime.get("message", "VerifySignal runtime is not ready."),
        "source": runtime.get("source"),
        "coreCommand": None,
        "selectedCandidate": None,
        "nextAction": runtime.get("nextAction", "Provide an email unlock token or configure an override."),
        "guideText": "Workspace and integration setup can continue. Full validation and browser execution require a verified VerifySignal runtime.",
    }
