from __future__ import annotations

from verifysignal_spec.integrations.base import build_onboarding_guidance, render_onboarding_guide
from tests.fixtures.workflows.golden_path_onboarding import assert_no_secret_findings


def test_onboarding_guidance_plain_text_fallback_and_no_secret_values() -> None:
    guide = build_onboarding_guidance(
        integration_key="codex",
        display_name="Codex",
        generated_guide_path=".agents/VERIFYSIGNAL_ONBOARDING.md",
    )
    data = guide.to_dict()

    assert data["plainTextFallback"]
    assert "$verifysignal-specify" in data["plainTextFallback"]
    assert "/verifysignal" not in data["plainTextFallback"]
    assert_no_secret_findings(data)


def test_rendered_onboarding_guide_contains_equivalent_status_semantics() -> None:
    guide = build_onboarding_guidance(
        integration_key="claude",
        display_name="Claude Code",
        generated_guide_path=".claude/VERIFYSIGNAL_ONBOARDING.md",
    )
    content = render_onboarding_guide(guide)

    assert "VerifySignal Golden Path" in content
    assert "[RECOMMENDED]" in content
    assert "Repaired strict pass" in content
    assert "Sensitive files" in content
