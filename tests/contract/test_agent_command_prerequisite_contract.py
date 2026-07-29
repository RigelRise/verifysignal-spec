from __future__ import annotations

from verifysignal_spec.integrations.claude import ClaudeIntegration
from verifysignal_spec.integrations.codex import CodexIntegration


def _rendered_workflow_files(tmp_path) -> dict[str, str]:
    files = {item.path: item.content for item in CodexIntegration().render_files(tmp_path)}
    files.update({item.path: item.content for item in ClaudeIntegration().render_files(tmp_path)})
    return files


def test_specify_template_requires_prerequisite_check_and_understanding_guidance(tmp_path) -> None:
    files = _rendered_workflow_files(tmp_path)
    for path in [
        ".agents/skills/verifysignal-specify/SKILL.md",
        ".claude/skills/verifysignal-specify/SKILL.md",
    ]:
        content = files[path]
        assert "verifysignal workflow check specify --json" in content
        assert "Do not use `npx` or package-runner wrappers" in content
        assert "If `workflow check` is unavailable" in content
        assert "Do not fall back to `verifysignal check`, directory listing, repository inspection, or use-case questions" in content
        assert "product understanding is required" in content
        assert "approximate time" in content
        expected = (
            "$verifysignal-understand"
            if path.startswith(".agents/")
            else "/verifysignal-understand"
        )
        assert expected in content
        assert "project overview" in content
        assert "candidate validation use cases" in content
        assert "Do not ask for alias, target behavior, expected outcome, run request details, or skill details" in content


def test_later_stage_templates_use_workflow_check_before_stage_work(tmp_path) -> None:
    files = _rendered_workflow_files(tmp_path)
    expected = {
        "clarify": "verifysignal workflow check clarify --alias <alias> --json",
        "plan": "verifysignal workflow check plan --alias <alias> --json",
        "tasks": "verifysignal workflow check tasks --alias <alias> --json",
        "implement": "verifysignal workflow check implement --alias <alias> --json",
        "validate": "verifysignal workflow check validate --alias <alias> --json",
        "run": "verifysignal workflow check run --alias <alias> --json",
        "repair": "verifysignal workflow check repair --alias <alias> --json",
    }
    for stage, command in expected.items():
        for root in [".agents/skills", ".claude/skills"]:
            content = files[f"{root}/verifysignal-{stage}/SKILL.md"]
            assert command in content
            assert "Do not use `npx` or package-runner wrappers" in content
            assert "If `workflow check` is unavailable" in content
            assert "Do not perform stage-specific work until the check allows it" in content


def test_understand_and_list_templates_document_no_prerequisite_behavior(tmp_path) -> None:
    files = _rendered_workflow_files(tmp_path)
    assert "No prior product understanding is required" in files[".agents/skills/verifysignal-understand/SKILL.md"]
    assert "verifysignal workflow check understand --json" in files[".agents/skills/verifysignal-understand/SKILL.md"]
    assert "Do not inspect the repository or browse the product with an unknown CLI contract" in files[".agents/skills/verifysignal-understand/SKILL.md"]
    assert "No product understanding prerequisite is required" in files[".claude/skills/verifysignal-list/SKILL.md"]


def test_understand_host_browser_failure_is_setup_not_product_state(
    tmp_path,
) -> None:
    files = _rendered_workflow_files(tmp_path)
    for path in [
        ".agents/skills/verifysignal-understand/SKILL.md",
        ".claude/skills/verifysignal-understand/SKILL.md",
    ]:
        content = files[path]
        assert "verify that the headed browser capability is actually available" in content
        assert "host integration setup failure" in content
        assert "do not call `workflow persist understand`" in content
        assert "do not create or update product understanding artifacts" in content
        assert "at least one real product signal" in content
        assert "Never pass raw JSON text to `--payload`" in content
        assert "pipe it through `--stdin`" in content

    codex = files[".agents/skills/verifysignal-understand/SKILL.md"]
    assert "setup-playwright-mcp" in codex
    assert "user-scoped" in codex
    assert "trust the project" not in codex
    assert "start a new Codex session" in codex


def test_understand_uses_loaded_playwright_mcp_when_codex_browser_plugin_is_empty(
    tmp_path,
) -> None:
    content = _rendered_workflow_files(tmp_path)[
        ".agents/skills/verifysignal-understand/SKILL.md"
    ]

    mcp_check = "First inspect the current agent session for the project Playwright MCP tools"
    host_check = "Only when those MCP tools are absent"
    unavailable = "only after both browser inventories were checked"

    assert mcp_check in content
    assert host_check in content
    assert unavailable in content
    assert content.index(mcp_check) < content.index(host_check)
    assert content.index(host_check) < content.index(unavailable)
    assert (
        "`agent.browsers.list()` only reports Browser Plugin/in-app browser backends"
        in content
    )
    assert "an empty list does not report Playwright MCP availability" in content
    assert (
        "Do not run setup or recommend a session restart when the Playwright MCP "
        "tools are already available"
        in content
    )
