from __future__ import annotations

from pathlib import Path
from typing import Any

from verifysignal_spec.integrations.claude import ClaudeIntegration
from verifysignal_spec.integrations.codex import CodexIntegration
from verifysignal_spec.integrations.base import build_onboarding_guidance
from verifysignal_spec.integrations.manifests import install_rendered_files, load_all_states, remove_integration, set_default
from verifysignal_spec.integrations.mcp import merge_mcp_servers
from verifysignal_spec.runtime.resolver import ensure_core_runtime
from verifysignal_spec.workspace.repository import get_core_configuration
from verifysignal_spec.workflows.core_setup import onboarding_core_status, run_core_setup

INTEGRATIONS = {
    "codex": CodexIntegration,
    "claude": ClaudeIntegration,
}


def get_integration(key: str):
    if key not in INTEGRATIONS:
        raise ValueError(f"Unsupported integration: {key}")
    return INTEGRATIONS[key]()


def install(project: Path, key: str, force: bool = False, default: bool = True) -> dict[str, Any]:
    integration = get_integration(key)
    runtime = ensure_core_runtime(project, context="integration")
    core_setup_result = run_core_setup(project, persist=False)
    core_setup = core_setup_result.to_dict()
    core_status = _runtime_onboarding_status(runtime.to_dict()) if runtime.source in {"managed-cache", "managed-download"} else onboarding_core_status(core_setup_result)
    state = install_rendered_files(
        project,
        integration.key,
        integration.display_name,
        integration.invoke_style,
        integration.render_files(project, core_status=core_status),
        force=force,
        default=default,
    )
    # Live authoring: merge the integration's declared MCP servers into the agent's project config
    # (e.g. Claude Code's .mcp.json). Merge-safe and never fatal to install.
    mcp = None
    servers = integration.mcp_servers()
    if servers:
        try:
            mcp = merge_mcp_servers(project, servers)
        except OSError as exc:
            mcp = {"path": ".mcp.json", "skipped": True, "reason": f"could not write .mcp.json: {exc}", "nodeAvailable": False}
    guide_path = ".agents/VERIFYSIGNAL_ONBOARDING.md" if integration.key == "codex" else ".claude/VERIFYSIGNAL_ONBOARDING.md"
    guide = build_onboarding_guidance(
        integration_key=integration.key,
        display_name=integration.display_name,
        generated_guide_path=guide_path,
        core_status=core_status,
    ).to_dict()
    return {
        "integration": state.to_dict(),
        "installedFiles": [item.path for item in state.managedFiles],
        "coreSetup": core_setup,
        "runtime": runtime.to_dict(),
        "managedRuntimeReadiness": runtime.to_dict(),
        "onboardingGuide": guide,
        "mcp": mcp,
    }


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
    results = []
    for item in keys:
        results.append(_upgrade_without_core_resolution(project, item, force=force))
    return {"upgraded": results}


def _upgrade_without_core_resolution(project: Path, key: str, *, force: bool) -> dict[str, Any]:
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
        default=False,
    )
    mcp = None
    servers = integration.mcp_servers()
    if servers:
        try:
            mcp = merge_mcp_servers(project, servers)
        except OSError as exc:
            mcp = {
                "path": ".mcp.json",
                "skipped": True,
                "reason": f"could not write .mcp.json: {exc}",
                "nodeAvailable": False,
            }
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


def _runtime_onboarding_status(runtime: dict[str, Any]) -> dict[str, Any]:
    if runtime.get("status") == "ready":
        return {
            "statusMarker": "[READY]",
            "summary": "VerifySignal runtime is ready.",
            "source": runtime.get("source"),
            "coreCommand": runtime.get("runtimeCommand"),
            "selectedCandidate": None,
            "nextAction": "Continue with /verifysignal-specify.",
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
