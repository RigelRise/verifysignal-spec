from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from verifysignal_spec.templates.agent_guidance import (
    MISSING_UNDERSTANDING_AUTO_PREPARE,
    REAL_TARGET_FIRST_RECOMMENDATION,
)
from verifysignal_spec.workflows.models import OnboardingGuidance


@dataclass(slots=True)
class RenderedFile:
    path: str
    content: str
    source: str
    kind: str = "agent-skill"


class AgentIntegration:
    key: str
    display_name: str
    invoke_style: str

    def render_files(self, project: Path, core_status: dict[str, object] | None = None) -> list[RenderedFile]:
        raise NotImplementedError

    def mcp_servers(self) -> dict[str, object]:
        """MCP servers this integration configures in the host agent's project MCP config.

        Default: none. Claude overrides with the Playwright MCP so live authoring is enabled on
        install. VerifySignal merges these into the agent's project config (e.g. ``.mcp.json``)."""
        return {}


@dataclass(frozen=True, slots=True)
class WorkflowCommandSpec:
    stage: str
    description: str
    argument_hint: str = ""
    skill_name_override: str | None = None

    @property
    def canonical_name(self) -> str:
        return f"verifysignal.{self.stage}"

    @property
    def skill_name(self) -> str:
        return self.skill_name_override or f"verifysignal-{self.stage}"


WORKFLOW_COMMANDS = [
    WorkflowCommandSpec(
        "understand",
        "Capture product context from a repository or live URL without source access",
        "[--url <url>] [scope or goal]",
    ),
    WorkflowCommandSpec("specify", "Define one browser validation use case", '<alias> "<behavior>"'),
    WorkflowCommandSpec("clarify", "Resolve high-impact unknowns", "<alias>"),
    WorkflowCommandSpec("plan", "Plan one run request and reusable skills", "<alias>"),
    WorkflowCommandSpec("tasks", "Generate ordered authoring tasks", "<alias>"),
    WorkflowCommandSpec("implement", "Create or update planned artifacts", "<alias>"),
    WorkflowCommandSpec("validate", "Validate draft artifacts through VerifySignal Spec/Core", "<alias>"),
    WorkflowCommandSpec("list", "List registered use cases and workflow state", ""),
    WorkflowCommandSpec("run", "Run a selected validated use case", "<alias>"),
    WorkflowCommandSpec("repair", "Repair invalid or failed use cases", "<alias> [report path]"),
    WorkflowCommandSpec(
        "auto",
        "Drive discover, author, validate, run, and safe repair in one pass (the default happy path)",
        "<goal or alias>",
        skill_name_override="verifysignal",
    ),
]


def load_agent_command_template(stage: str) -> str:
    path = Path(__file__).resolve().parents[1] / "templates" / "agent-commands" / f"verifysignal.{stage}.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    else:
        return f"# verifysignal.{stage}\n\nFollow the VerifySignal workflow stage rules.\n"


def render_workflow_skill(spec: WorkflowCommandSpec, agent: str, include_argument_hint: bool = False) -> str:
    body = load_agent_command_template(spec.stage)
    hint = spec.argument_hint.replace('"', '\\"')
    argument = f'argument-hint: "{hint}"\n' if include_argument_hint and spec.argument_hint else ""
    return f"""---
name: "{spec.skill_name}"
description: "{agent} workflow command for {spec.canonical_name}: {spec.description}"
{argument}---

# {spec.skill_name}

Invoke this command as `/{spec.skill_name}`.

{body}
"""


def render_workflow_skill_files(root: str, agent: str, include_argument_hint: bool = False) -> list[RenderedFile]:
    return [
        RenderedFile(
            f"{root}/{spec.skill_name}/SKILL.md",
            render_workflow_skill(spec, agent, include_argument_hint=include_argument_hint),
            f"{agent.lower()}/{spec.skill_name}",
        )
        for spec in WORKFLOW_COMMANDS
    ]


def build_onboarding_guidance(
    *,
    integration_key: str,
    display_name: str,
    generated_guide_path: str,
    core_status: dict[str, object] | None = None,
) -> OnboardingGuidance:
    stage_markers = ["[RECOMMENDED]", "[ACCEPTED]", "[RUNNING]", "[REPAIR]", "[PASS]", "[SKIPPED]", "[BLOCKED]", "[FAIL]"]
    safety = [
        "Sensitive files, local env files, cookies, browser storage, and credential values are not inspected or persisted by default.",
        "Safe understanding inspects public project structure and non-sensitive source context or a user-approved live URL before recommending the first run.",
    ]
    success = [
        "Direct strict pass counts as first-run success.",
        "Repaired strict pass also counts as first-run success when the repair was safe, revalidated, rerun, and strict.",
        "Skip means the user declined the Golden Path; it is not pass, fail, or inconclusive.",
        "Blocked means required runtime data, host permission, safety boundary, or Core compatibility stopped automatic continuation.",
        "Failed means the first run did not reach strict pass and needs clear feedback or repair.",
    ]
    fallback = (
        "VerifySignal Golden Path\n"
        "Next: /verifysignal\n"
        "One pass: discover -> author -> validate -> run -> safe repair, stopping only when it needs you.\n"
        "Step-by-step control: /verifysignal-specify, /verifysignal-plan, /verifysignal-run, ...\n"
        "Safety: sensitive files and credential values require explicit approval and are never persisted."
    )
    return OnboardingGuidance(
        integrationKey=integration_key,
        terminalTitle="VerifySignal Golden Path",
        terminalSummary=(
            f"{display_name} integration installed. Run /verifysignal next: it drives the whole validation in one pass "
            "(discover, author, validate, run, safe repair) and stops only when it needs you. Use the staged "
            "/verifysignal-specify ... commands when you want step-by-step control."
        ),
        generatedGuidePath=generated_guide_path,
        stageMarkers=stage_markers,
        usesColor=True,
        plainTextFallback=fallback,
        nextCommand="/verifysignal",
        safetyBoundaries=safety,
        successSemantics=success,
        coreStatus=core_status,
    )


_LIVE_AUTHORING_ONBOARDING = """## Live Authoring

VerifySignal set up live authoring for you: it added a Playwright MCP server to this project's `.mcp.json`, so the agent can author and repair selectors against the live page. Claude Code will ask you to approve the server on first session (this needs Node/npx installed). To do it manually, or for another agent:

```
claude mcp add playwright -- npx -y @playwright/mcp@latest
```

The Playwright MCP is an authoring aid only: `verifysignal discover` and `verifysignal run` remain the deterministic authority, and if they disagree with the MCP, they win. Without it, VerifySignal authors from source and grounds with `discover` as usual. MCP snapshots, screenshots, and storage state are never persisted into `.verifysignal/`."""


def render_onboarding_guide(guide: OnboardingGuidance) -> str:
    data = guide.to_dict()
    stages = "\n".join(f"- {item}" for item in data.get("stageMarkers", []))
    safety = "\n".join(f"- {item}" for item in data.get("safetyBoundaries", []))
    success = "\n".join(f"- {item}" for item in data.get("successSemantics", []))
    core = data.get("coreStatus") or {}
    core_lines = ""
    if core:
        source = f"\n- Source: {core.get('source')}" if core.get("source") else ""
        command = f"\n- Command: `{core.get('coreCommand')}`" if core.get("coreCommand") else ""
        core_lines = f"""## Core Runtime

{core.get("guideText", core.get("summary", ""))}

- Status: {core.get("statusMarker")} {core.get("summary", "")}{source}{command}
- Next: {core.get("nextAction")}

"""
    return f"""# VerifySignal Golden Path

{data.get("terminalSummary", "")}

{core_lines}## Next Step

Run `{data.get("nextCommand", "/verifysignal-specify")}`.

## Stage Markers

{stages}

## Safety Boundaries

{safety}

## Success Semantics

{success}

## First-Run Policy

- {REAL_TARGET_FIRST_RECOMMENDATION}.
- {MISSING_UNDERSTANDING_AUTO_PREPARE}.
- Repaired strict pass is a success only after safe repair, revalidation, rerun, and strict pass.

{_LIVE_AUTHORING_ONBOARDING}

## Plain Text Fallback

```text
{data.get("plainTextFallback", "")}
```
"""
