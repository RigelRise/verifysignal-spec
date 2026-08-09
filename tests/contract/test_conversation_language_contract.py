from __future__ import annotations

from verifysignal_spec.integrations.claude import ClaudeIntegration
from verifysignal_spec.integrations.codex import CodexIntegration
from verifysignal_spec.language import ConversationLanguage

BOUNDARY_PHRASE = "keep aliases and identifiers ASCII"


def _contexts(tmp_path, language: ConversationLanguage | None) -> tuple[str, str]:
    claude = {item.path: item.content for item in ClaudeIntegration().render_files(tmp_path, language=language)}
    codex = {item.path: item.content for item in CodexIntegration().render_files(tmp_path, language=language)}
    return claude["CLAUDE.md"], codex["AGENTS.md"]


def test_detected_language_declares_default_with_detection_note(tmp_path) -> None:
    for content in _contexts(tmp_path, ConversationLanguage("ru", "detected")):
        assert "Default conversation language: ru (detected at init)." in content
        assert "mirror the user when they write in another language" in content
        assert BOUNDARY_PHRASE in content
        assert "Keep generated project artifacts in English." in content


def test_flag_language_declares_default_without_detection_note(tmp_path) -> None:
    for content in _contexts(tmp_path, ConversationLanguage("pt", "flag")):
        assert "Default conversation language: pt." in content
        assert "(detected at init)" not in content


def test_no_language_falls_back_to_mirroring_the_user(tmp_path) -> None:
    for content in _contexts(tmp_path, None):
        assert "Converse and guide in the language the user writes in; default to English." in content
        assert "Default conversation language:" not in content
        assert BOUNDARY_PHRASE in content


def test_personal_pt_br_dogfood_line_is_gone(tmp_path) -> None:
    for language in (None, ConversationLanguage("et", "flag")):
        claude = {item.path: item.content for item in ClaudeIntegration().render_files(tmp_path, language=language)}
        codex = {item.path: item.content for item in CodexIntegration().render_files(tmp_path, language=language)}
        for content in list(claude.values()) + list(codex.values()):
            assert "pt-BR only" not in content


def test_codex_invocation_invariant_holds_with_language_set(tmp_path) -> None:
    files = {
        item.path: item.content
        for item in CodexIntegration().render_files(tmp_path, language=ConversationLanguage("pt-BR", "flag"))
    }
    assert all("/verifysignal" not in content for content in files.values())
