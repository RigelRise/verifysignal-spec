from __future__ import annotations

from verifysignal_spec.integrations.claude import ClaudeIntegration
from verifysignal_spec.integrations.codex import CodexIntegration


def test_guidance_points_at_policy_set_for_policy_only_changes(tmp_path) -> None:
    # The agent must reach for `verifysignal policy set` to change ONLY the side-effect policy,
    # instead of re-authoring the whole implement payload (the ceremony policy set removes).
    claude = {item.path: item.content for item in ClaudeIntegration().render_files(tmp_path)}
    codex = {item.path: item.content for item in CodexIntegration().render_files(tmp_path)}
    assert "verifysignal policy set" in claude["CLAUDE.md"]
    assert "verifysignal policy set" in codex["AGENTS.md"]


def test_codex_renders_verifysignal_workflow_skills(tmp_path) -> None:
    files = {item.path: item.content for item in CodexIntegration().render_files(tmp_path)}
    assert ".agents/skills/verifysignal-understand/SKILL.md" in files
    assert ".agents/skills/verifysignal-run/SKILL.md" in files
    assert "verifysignal.understand" in files[".agents/skills/verifysignal-understand/SKILL.md"]
    assert ".agents/skills/verifysignal-spec-author/SKILL.md" not in files
    assert "Invoke this command as `$verifysignal-understand`" in files[".agents/skills/verifysignal-understand/SKILL.md"]
    assert any("$verifysignal-" in content for content in files.values())
    assert all("/verifysignal" not in content for content in files.values())


def test_claude_renders_argument_hints_for_workflow_skills(tmp_path) -> None:
    files = {item.path: item.content for item in ClaudeIntegration().render_files(tmp_path)}
    content = files[".claude/skills/verifysignal-specify/SKILL.md"]
    assert "argument-hint:" in content
    assert "<alias>" in content
    assert "<behavior>" in content
    assert "Invoke this command as `/verifysignal-specify`" in content

    understand = files[".claude/skills/verifysignal-understand/SKILL.md"]
    assert 'argument-hint: "[--url <url>] [scope or goal]"' in understand
    assert "live URL without source access" in understand


def test_codex_and_claude_validation_guidance_share_live_readiness_facts(tmp_path) -> None:
    codex = {item.path: item.content for item in CodexIntegration().render_files(tmp_path)}
    claude = {item.path: item.content for item in ClaudeIntegration().render_files(tmp_path)}

    codex_content = codex[".agents/skills/verifysignal-validate/SKILL.md"]
    claude_content = claude[".claude/skills/verifysignal-validate/SKILL.md"]
    for phrase in [
        "shared CLI JSON",
        "credential readiness hints",
        "structured confirmation",
        "cleanup lifecycle",
        "side-effect envelope",
    ]:
        assert phrase in codex_content
        assert phrase in claude_content


def test_context_includes_playwright_mcp_authoring_guidance(tmp_path) -> None:
    # Always-loaded context must teach the agent to use a Playwright MCP for live authoring as an
    # aid only — `discover`/`run` remain the deterministic authority; nothing MCP is persisted.
    claude = {item.path: item.content for item in ClaudeIntegration().render_files(tmp_path)}
    codex = {item.path: item.content for item in CodexIntegration().render_files(tmp_path)}
    for content in (claude["CLAUDE.md"], codex["AGENTS.md"]):
        assert "Playwright MCP" in content
        assert "discover" in content and "wins" in content
        assert "browser_snapshot" in content or "browser_navigate" in content
        assert "never" in content.lower() and "persist" in content.lower()
        assert "commit" in content.lower()
        assert "browser-first-understanding/v1" in content
        assert "headed" in content.lower()
        assert "user acknowledges the summary" in content


def test_onboarding_guide_advertises_auto_enabled_playwright_mcp(tmp_path) -> None:
    # Live authoring is registered once in Claude user scope. The project file
    # remains only as a compatibility fallback.
    claude = {item.path: item.content for item in ClaudeIntegration().render_files(tmp_path)}
    guide = claude[".claude/VERIFYSIGNAL_ONBOARDING.md"]
    assert "Playwright MCP" in guide
    assert ".mcp.json" in guide
    assert "user scope" in guide.lower()
    assert "compatibility fallback" in guide.lower()
    assert (
        "claude mcp add --scope user playwright -- verifysignal integration playwright-mcp"
        in guide
    )
    assert "private temporary" in guide
    assert "target project" in guide
    assert "private user cache" in guide
    assert "setup-playwright-mcp" in guide
    assert "does not depend on network access" in guide
    assert "authority" in guide.lower() or "wins" in guide.lower()


def test_codex_onboarding_advertises_user_scoped_playwright_and_native_invocation(tmp_path) -> None:
    codex = {item.path: item.content for item in CodexIntegration().render_files(tmp_path)}
    guide = codex[".agents/VERIFYSIGNAL_ONBOARDING.md"]

    assert ".codex/config.toml" in guide
    assert "user scope" in guide.lower()
    assert "compatibility fallback" in guide.lower()
    assert (
        "codex mcp add playwright -- verifysignal integration playwright-mcp"
        in guide
    )
    assert "trust the project" not in guide.lower()
    assert "$verifysignal" in guide
    assert "/verifysignal" not in guide
    assert ".mcp.json" not in guide
    assert "claude mcp add" not in guide
    assert "private user cache" in guide
    assert "setup-playwright-mcp" in guide
    assert "does not depend on network access" in guide
