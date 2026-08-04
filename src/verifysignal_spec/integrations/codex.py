from __future__ import annotations

from pathlib import Path

from verifysignal_spec.templates.agent_guidance import (
    FIRST_RUN_STAGE_CARD_GUIDANCE,
    MISSING_UNDERSTANDING_AUTO_PREPARE,
    PLAYWRIGHT_MCP_GUIDANCE,
    REAL_TARGET_FIRST_RECOMMENDATION,
)

from .base import AgentIntegration, RenderedFile, build_onboarding_guidance, render_onboarding_guide, render_workflow_skill_files
from .invocation import render_agent_invocations
from .mcp import managed_playwright_mcp_server


class CodexIntegration(AgentIntegration):
    key = "codex"
    display_name = "Codex"
    invoke_style = "Codex skills under .agents/skills/verifysignal-*; invoke as $verifysignal-*"
    mcp_config_format = "codex-toml"

    def render_files(self, project: Path, core_status: dict[str, object] | None = None) -> list[RenderedFile]:
        files = [
            RenderedFile(
                "AGENTS.md",
                render_agent_invocations(_context("AGENTS.md"), self.key),
                "codex/context",
                "context",
            ),
        ]
        guide = build_onboarding_guidance(
            integration_key=self.key,
            display_name=self.display_name,
            generated_guide_path=".agents/VERIFYSIGNAL_ONBOARDING.md",
            core_status=core_status,
        )
        files.append(RenderedFile(".agents/VERIFYSIGNAL_ONBOARDING.md", render_onboarding_guide(guide), "codex/onboarding-guide", "onboarding-guide"))
        files.extend(
            render_workflow_skill_files(
                ".agents/skills",
                "Codex",
                integration=self.key,
            )
        )
        return files

    def mcp_servers(self) -> dict[str, object]:
        return {
            "playwright": managed_playwright_mcp_server(required=True)
        }


def _context(filename: str) -> str:
    return f"""# VerifySignal Agent Guidance

Use `$verifysignal-*` workflow skills for staged VerifySignal use case authoring.
Use `verifysignal` commands from the target repository root for deterministic
non-AI operations. Keep generated project artifacts and guidance in English.
Use pt-BR only for conversation with the project owner when appropriate. Store
VerifySignal state in `.verifysignal/`. Do not import private VerifySignal
Core packages.

Avoid sensitive files by default and ask before reading local environment files
or secret-bearing configuration. Never persist credential values.

Each use case maps to exactly one run request. Skills are decoupled reusable
artifacts that may support multiple run requests. Store staged workflow
documents under `.verifysignal/workflows/` and use structured workflow state for
status, gates, and resume.

To change ONLY a use case's side-effect policy (class/mode/allowed/forbidden),
use `verifysignal policy set <alias> --class <class> [--mode <mode>] [--payload
<policy.json>]`. It mutates only the policy, re-syncs the run request, and
preserves runtime inputs and skills — do NOT re-author the full `implement`
payload to declare or change a policy. Re-persist `implement` only for
skill/target/step/resourceIdentity/rerun-policy changes.

Golden Path first runs are agent-chat first. {REAL_TARGET_FIRST_RECOMMENDATION}.
{FIRST_RUN_STAGE_CARD_GUIDANCE}.
{MISSING_UNDERSTANDING_AUTO_PREPARE}.

{PLAYWRIGHT_MCP_GUIDANCE}.
"""
