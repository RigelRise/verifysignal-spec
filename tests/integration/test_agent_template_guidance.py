from __future__ import annotations

from verifysignal_spec.integrations.claude import ClaudeIntegration
from verifysignal_spec.integrations.codex import CodexIntegration


def test_installed_codex_and_claude_templates_include_write_safety_contract_guidance(tmp_path) -> None:
    files = {item.path: item.content for item in CodexIntegration().render_files(tmp_path)}
    files.update({item.path: item.content for item in ClaudeIntegration().render_files(tmp_path)})
    combined = "\n".join(files.values())

    for phrase in [
        "sideEffectPolicy.allowed[]",
        "sideEffectPolicy.forbidden[]",
        "workflow supersede-write-outcome",
        "runtime-supported confirmation",
        "prepared/committed/discarded",
        "seed plus a run-attempt token",
        "Resolve `{{parameters.*}}` confirmation expected values before Core execution",
    ]:
        assert phrase in combined
    assert "hand-edit `.verifysignal/` `lastRun`" not in combined
    assert "verifysignal.probe/v1" in combined
    assert "verifysignal probe <run-request>" in combined
    assert "discover --storage-state" not in combined
    assert "developer-controlled `--storage-state`" not in combined
    for phrase in [
        "recommendation, not a decision",
        "confirm or replace",
        "verifysignal credentials prepare <alias>",
        ".env.verifysignal.test.local",
        "Never read\n   `.env`, `.env.local`",
        "explicit `--env-file`",
    ]:
        assert phrase in combined


def test_installed_understand_templates_guide_observable_browser_first_mapping(tmp_path) -> None:
    codex = {item.path: item.content for item in CodexIntegration().render_files(tmp_path)}
    claude = {item.path: item.content for item in ClaudeIntegration().render_files(tmp_path)}

    for content in [
        codex[".agents/skills/verifysignal-understand/SKILL.md"],
        claude[".claude/skills/verifysignal-understand/SKILL.md"],
    ]:
        flattened = " ".join(content.split())
        for phrase in [
            "workflow info verifysignal-use-case --json",
            "browser-first-understanding/v1",
            "--url <url>",
            "Playwright MCP or an equivalent",
            "headed browser",
            "explicitly confirms that login is complete",
            "about 700 ms",
            "20 meaningful pages or states",
            "depth 3",
            "three to five candidate",
            "15-minute soft budget",
            "same-origin",
            "keep the browser open",
            "raw DOM",
            "MCP snapshots",
            "verifysignal core version --json",
            "data.operations",
            "verifysignal probe",
            "must not commit",
        ]:
            assert phrase in flattened
        assert "Do not activate mutating, transactional, destructive, or unknown-safety controls during mapping" in flattened
        assert "select one journey" in flattened.lower()
