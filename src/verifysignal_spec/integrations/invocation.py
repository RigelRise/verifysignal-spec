"""Integration-native VerifySignal agent command rendering.

Agent commands are presentation-layer hints, not deterministic CLI commands.
Codex invokes installed skills with ``$`` while Claude Code uses slash commands.
This module keeps that distinction out of shared workflow and template logic.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

SUPPORTED_INTEGRATIONS = {"codex", "claude"}
_VERIFY_AGENT_COMMAND = re.compile(
    r"(?<![\w./-])[/\\$](?P<command>verifysignal(?:-[a-z0-9*][a-z0-9*-]*)?)",
    flags=re.IGNORECASE,
)


def invocation_prefix(integration: str) -> str:
    """Return the native installed-skill prefix for a supported integration."""

    if integration not in SUPPORTED_INTEGRATIONS:
        raise ValueError(f"Unsupported integration: {integration}")
    return "$" if integration == "codex" else "/"


def skill_invocation(skill_name: str, integration: str) -> str:
    """Render one installed skill name using the host integration's syntax."""

    return f"{invocation_prefix(integration)}{skill_name}"


def native_invocation(stage: str, integration: str, style: str = "skill") -> str:
    """Render a staged VerifySignal command for one host integration."""

    separator = "-" if style == "skill" else "."
    return skill_invocation(f"verifysignal{separator}{stage}", integration)


def render_agent_invocations(text: str, integration: str) -> str:
    """Normalize VerifySignal agent commands in user-facing text.

    The boundary-aware pattern intentionally ignores filesystem paths and URLs
    such as ``/path/to/verifysignal`` and ``https://verifysignal.io``.
    """

    prefix = invocation_prefix(integration)
    return _VERIFY_AGENT_COMMAND.sub(
        lambda match: f"{prefix}{match.group('command')}",
        text,
    )


def render_agent_invocations_in_value(value: Any, integration: str) -> Any:
    """Recursively normalize command hints in a public response value."""

    if isinstance(value, str):
        return render_agent_invocations(value, integration)
    if isinstance(value, dict):
        return {
            key: render_agent_invocations_in_value(item, integration)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [
            render_agent_invocations_in_value(item, integration)
            for item in value
        ]
    if isinstance(value, tuple):
        return tuple(
            render_agent_invocations_in_value(item, integration)
            for item in value
        )
    return value


def project_integration(project: Path, requested: str | None = None) -> str:
    """Resolve the selected project integration without introducing globals."""

    if requested:
        if requested not in SUPPORTED_INTEGRATIONS:
            raise ValueError(f"Unsupported integration: {requested}")
        return requested

    # Lazy import avoids a base -> invocation -> manifests -> base cycle.
    from .manifests import load_all_states

    states = load_all_states(project).get("integrations", {})
    for key, value in states.items():
        if (
            key in SUPPORTED_INTEGRATIONS
            and isinstance(value, dict)
            and value.get("default")
        ):
            return key
    return "codex"
