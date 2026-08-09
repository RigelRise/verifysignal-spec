from __future__ import annotations

import json
from unittest.mock import patch

from helpers import CliTestCase, FAKE_CORE

from verifysignal_spec.integrations.manifests import load_all_states


class ConversationLanguagePersistenceTests(CliTestCase):
    def _init(self, *extra: str, integration: str = "codex") -> tuple[int, str, str]:
        return self.cli(
            ["init", str(self.project), "--integration", integration, "--core-cmd", str(FAKE_CORE), *extra]
        )

    def test_upgrade_keeps_persisted_language_without_redetecting(self) -> None:
        code, _out, err = self._init("--language", "et", "--json")
        self.assertEqual(code, 0, err)

        with patch("verifysignal_spec.language.detect_system_language", return_value="ru"):
            code, _out, err = self.cli(["integration", "upgrade", "codex", "--project", str(self.project), "--json"])
        self.assertEqual(code, 0, err)
        agents = (self.project / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("Default conversation language: et.", agents)
        self.assertNotIn("(detected at init)", agents)

    def test_install_other_integration_reuses_persisted_language(self) -> None:
        code, _out, err = self._init("--language", "et", "--json")
        self.assertEqual(code, 0, err)

        code, _out, err = self.cli(["integration", "install", "claude", "--project", str(self.project), "--json"])
        self.assertEqual(code, 0, err)
        claude = (self.project / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertIn("Default conversation language: et.", claude)

    def test_install_language_flag_persists_project_wide(self) -> None:
        code, _out, err = self._init("--language", "et", "--json")
        self.assertEqual(code, 0, err)

        code, _out, err = self.cli(
            ["integration", "install", "claude", "--project", str(self.project), "--language", "ru", "--json"]
        )
        self.assertEqual(code, 0, err)
        self.assertIn("Default conversation language: ru.", (self.project / "CLAUDE.md").read_text(encoding="utf-8"))

        code, _out, err = self.cli(["integration", "upgrade", "--project", str(self.project), "--json"])
        self.assertEqual(code, 0, err)
        self.assertIn("Default conversation language: ru.", (self.project / "AGENTS.md").read_text(encoding="utf-8"))
        self.assertIn("Default conversation language: ru.", (self.project / "CLAUDE.md").read_text(encoding="utf-8"))

    def test_reinstall_with_same_language_is_hash_idempotent(self) -> None:
        code, _out, err = self._init("--language", "pt", "--json")
        self.assertEqual(code, 0, err)
        first = load_all_states(self.project)

        code, _out, err = self._init("--language", "pt", "--json")
        self.assertEqual(code, 0, err)
        second = load_all_states(self.project)
        self.assertEqual(first["integrations"], second["integrations"])

    def test_plain_reinit_does_not_revert_explicit_language(self) -> None:
        code, _out, err = self._init("--language", "pt", "--json")
        self.assertEqual(code, 0, err)

        with patch("verifysignal_spec.commands.init.detect_system_language", return_value="en"):
            code, out, err = self._init("--json")
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertEqual(payload["conversationLanguage"], "pt")
        self.assertEqual(payload["conversationLanguageSource"], "flag")
        self.assertIn("Default conversation language: pt.", (self.project / "AGENTS.md").read_text(encoding="utf-8"))

    def test_human_output_announces_language_choice(self) -> None:
        code, out, err = self._init("--language", "pt")
        self.assertEqual(code, 0, err)
        self.assertIn("Conversation language: pt (set via --language)", out)

        with patch("verifysignal_spec.commands.init.detect_system_language", return_value="ru"):
            code, out, err = self.cli(
                ["init", str(self.project), "--integration", "claude", "--core-cmd", str(FAKE_CORE), "--force"]
            )
        self.assertEqual(code, 0, err)
        # The earlier explicit choice persists; a re-init must not report a detection.
        self.assertIn("Conversation language: pt (set via --language)", out)
