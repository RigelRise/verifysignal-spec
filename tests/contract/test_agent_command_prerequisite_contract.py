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
        assert "/verifysignal-understand" in content
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
