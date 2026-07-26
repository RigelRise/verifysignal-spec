from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _template(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_agent_command_guidance_uses_canonical_side_effect_policy_and_supersede_flow() -> None:
    combined = "\n".join(
        _template(f"src/verifysignal_spec/templates/agent-commands/verifysignal.{stage}.md")
        for stage in ["specify", "clarify", "plan", "implement", "validate", "run", "repair"]
    )

    assert "sideEffectPolicy.allowed[]" in combined
    assert "sideEffectPolicy.forbidden[]" in combined
    assert "sideEffectPolicy.rules[].effect/match" in combined
    assert "Do not author" in combined
    assert "workflow supersede-write-outcome" in combined
    assert "runtime-supported confirmation" in combined
    assert "prepared/committed/discarded" in combined
    assert "seed plus a run-attempt token" in combined
    assert "Resolve `{{parameters.*}}` confirmation expected values before Core execution" in combined


def test_workflow_template_documents_canonical_policy_without_legacy_examples() -> None:
    content = _template("src/verifysignal_spec/templates/workflows/verifysignal-use-case.yaml")

    assert "sideEffectPolicy.allowed[]" in content
    assert "sideEffectPolicy.forbidden[]" in content
    assert "sideEffectPolicy.rules[].effect/match" in content
    assert "Do not author" in content
    assert "seed plus a run-attempt token" in content
    assert "Resolve `{{parameters.*}}` confirmation expected values before Core execution" in content


def test_browser_first_understanding_guidance_uses_the_shared_public_boundary() -> None:
    content = _template(
        "src/verifysignal_spec/templates/agent-commands/verifysignal.understand.md"
    )
    flattened = " ".join(content.split())

    assert "browser-first-understanding/v1" in flattened
    assert "Playwright MCP or an equivalent host browser/Playwright interface" in flattened
    assert "documented public Core `discover`, `probe`, and `run` operations" in flattened
    assert "verifysignal.probe/v1" in flattened
    assert ".agents/" not in content
    assert ".claude/" not in content
