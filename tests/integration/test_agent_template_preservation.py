from __future__ import annotations

from verifysignal_spec.integrations.claude import ClaudeIntegration
from verifysignal_spec.integrations.codex import CodexIntegration


def test_codex_and_claude_generated_guidance_preserves_browser_guardrails(tmp_path) -> None:
    files = {item.path: item.content for item in CodexIntegration().render_files(tmp_path)}
    files.update({item.path: item.content for item in ClaudeIntegration().render_files(tmp_path)})

    for root in [".agents/skills", ".claude/skills"]:
        implement = files[f"{root}/verifysignal-implement/SKILL.md"]
        validate = files[f"{root}/verifysignal-validate/SKILL.md"]
        repair = files[f"{root}/verifysignal-repair/SKILL.md"]
        assert "Browser validation use cases require a resolved target application environment" in files[f"{root}/verifysignal-specify/SKILL.md"]
        assert "runtime readiness verifies target resolution, target reachability, required runtime prerequisites, and Core authoring readiness" in validate
        # This asserted "Safe mechanical selector" — the opening of a sentence promising that
        # selector, wait-strategy, target-specificity, equivalent-flow, and run-profile repairs "may
        # auto-apply", when step-ordering is the only category with a mutator. The test PRESERVED the
        # overclaim as a guardrail, and it reaches the user's agent as instruction. Pin the honest
        # guarantee instead: what VerifySignal applies, and that the rest are proposed.
        assert "Step-ordering repairs are the only ones VerifySignal applies itself" in repair
        assert "propose-only" in repair
        assert "Data assumptions, credentials, required gates" in repair
        assert "Never persist credential values" in implement
        clarify = files[f"{root}/verifysignal-clarify/SKILL.md"]
        assert "recommendation, not a decision" in clarify
        assert "direct-user" in clarify
        assert "verifysignal credentials prepare" in clarify


def test_specify_and_understand_templates_describe_auto_prepare_without_manual_restart() -> None:
    from helpers import agent_template

    specify = agent_template("specify")
    understand = agent_template("understand")

    assert "auto-prepare" in specify.lower()
    assert "resume" in specify.lower()
    assert "verifysignal workflow recommend-first-run --json" in specify
    assert "Do not present candidateUseCases or recommendedCandidate from workflow check as the product-owned first-run recommendation" in specify
    assert "without requiring the user to manually restart" in specify
    assert "trivial public/read-only" in understand.lower()
    assert "before branch-heavy" in understand.lower()
    assert "partial inventory" in understand.lower()
