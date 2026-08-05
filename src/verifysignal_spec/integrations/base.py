from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from verifysignal_spec.templates.agent_guidance import (
    MISSING_UNDERSTANDING_AUTO_PREPARE,
    REAL_TARGET_FIRST_RECOMMENDATION,
)
from verifysignal_spec.workflows.models import OnboardingGuidance

from .invocation import (
    render_agent_invocations,
    render_agent_invocations_in_value,
    skill_invocation,
)


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
    mcp_config_format: str | None = None

    def render_files(self, project: Path, core_status: dict[str, object] | None = None) -> list[RenderedFile]:
        raise NotImplementedError

    def mcp_servers(self) -> dict[str, object]:
        """MCP servers this integration configures for the selected host.

        Default: none. Host adapters register managed entries in user scope
        through the host's public CLI and retain project configuration as a
        compatibility fallback."""
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
    WorkflowCommandSpec("validate", "Validate draft artifacts through VerifySignal and its Runtime", "<alias>"),
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


def render_workflow_skill(
    spec: WorkflowCommandSpec,
    agent: str,
    include_argument_hint: bool = False,
    integration: str | None = None,
) -> str:
    integration = integration or ("codex" if agent.lower() == "codex" else "claude")
    body = render_agent_invocations(
        load_agent_command_template(spec.stage),
        integration,
    )
    hint = spec.argument_hint.replace('"', '\\"')
    argument = f'argument-hint: "{hint}"\n' if include_argument_hint and spec.argument_hint else ""
    invocation = skill_invocation(spec.skill_name, integration)
    return f"""---
name: "{spec.skill_name}"
description: "{agent} workflow command for {spec.canonical_name}: {spec.description}"
{argument}---

# {spec.skill_name}

Invoke this command as `{invocation}`.

{body}
"""


def render_workflow_skill_files(
    root: str,
    agent: str,
    include_argument_hint: bool = False,
    integration: str | None = None,
) -> list[RenderedFile]:
    integration = integration or ("codex" if agent.lower() == "codex" else "claude")
    return [
        RenderedFile(
            f"{root}/{spec.skill_name}/SKILL.md",
            render_workflow_skill(
                spec,
                agent,
                include_argument_hint=include_argument_hint,
                integration=integration,
            ),
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
    golden_path = skill_invocation("verifysignal", integration_key)
    specify = skill_invocation("verifysignal-specify", integration_key)
    plan = skill_invocation("verifysignal-plan", integration_key)
    run = skill_invocation("verifysignal-run", integration_key)
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
        f"Next: {golden_path}\n"
        "One pass: discover -> author -> validate -> run -> safe repair, stopping only when it needs you.\n"
        f"Step-by-step control: {specify}, {plan}, {run}, ...\n"
        "Safety: sensitive files and credential values require explicit approval and are never persisted."
    )
    return OnboardingGuidance(
        integrationKey=integration_key,
        terminalTitle="VerifySignal Golden Path",
        terminalSummary=(
            f"{display_name} integration installed. Run {golden_path} next: it drives the whole validation in one pass "
            "(discover, author, validate, run, safe repair) and stops only when it needs you. Use the staged "
            f"{specify} ... commands when you want step-by-step control."
        ),
        generatedGuidePath=generated_guide_path,
        stageMarkers=stage_markers,
        usesColor=True,
        plainTextFallback=fallback,
        nextCommand=golden_path,
        safetyBoundaries=safety,
        successSemantics=success,
        coreStatus=(
            render_agent_invocations_in_value(core_status, integration_key)
            if core_status
            else None
        ),
    )


_CLAUDE_LIVE_AUTHORING_ONBOARDING = """## Live Authoring

VerifySignal set up live authoring for you: it registered the managed Playwright MCP in Claude Code user scope, so a plain `claude` session can author and repair selectors against the live page. The project's `.mcp.json` entry remains as a compatibility fallback for earlier installations and other machines. During integration setup, VerifySignal installs the pinned provider into a private user cache so agent startup does not depend on network access. Node/npm is required during setup. If provider setup was blocked, run `verifysignal integration setup-playwright-mcp --json`, then rerun integration installation before starting Claude Code. To add the managed launcher manually:

```
claude mcp add --scope user playwright -- verifysignal integration playwright-mcp
```

The managed launcher runs the pinned provider in a private temporary directory
and removes its raw outputs when the MCP exits, so snapshots, screenshots,
logs, and storage state are not written into the target project.

The Playwright MCP is an authoring aid only: `verifysignal discover` and `verifysignal run` remain the deterministic authority, and if they disagree with the MCP, they win. Without it, VerifySignal authors from source and grounds with `discover` as usual."""


_CODEX_LIVE_AUTHORING_ONBOARDING = """## Live Authoring

VerifySignal set up live authoring for you: it registered the managed Playwright MCP in Codex user scope, so a plain `codex` session can map and repair against the live page without a project-trust or `-c` override. The project's `.codex/config.toml` entry remains as a compatibility fallback for earlier installations and other machines. During integration setup, VerifySignal installs the pinned provider into a private user cache so Codex startup does not depend on network access. Node/npm is required during setup. If provider setup was blocked, run `verifysignal integration setup-playwright-mcp --json`, then rerun integration installation before starting a new Codex session. To add the managed launcher manually:

```
codex mcp add playwright -- verifysignal integration playwright-mcp
```

The managed launcher runs the pinned provider in a private temporary directory
and removes its raw outputs when the MCP exits, so snapshots, screenshots,
logs, and storage state are not written into the target project.

The Playwright MCP is an authoring aid only: `verifysignal discover` and `verifysignal run` remain the deterministic authority, and if they disagree with the MCP, they win. Without it, VerifySignal authors from source and grounds with `discover` as usual."""


def _live_authoring_onboarding(integration: str) -> str:
    if integration == "codex":
        return _CODEX_LIVE_AUTHORING_ONBOARDING
    return _CLAUDE_LIVE_AUTHORING_ONBOARDING


def render_onboarding_guide(guide: OnboardingGuidance) -> str:
    data = guide.to_dict()
    integration = str(data.get("integrationKey") or "claude")
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
    content = f"""# VerifySignal Golden Path

{data.get("terminalSummary", "")}

{core_lines}## Next Step

Run `{data.get("nextCommand", skill_invocation("verifysignal-specify", integration))}`.

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

{_live_authoring_onboarding(integration)}

## Plain Text Fallback

```text
{data.get("plainTextFallback", "")}
```
"""
    return render_agent_invocations(content, integration)
