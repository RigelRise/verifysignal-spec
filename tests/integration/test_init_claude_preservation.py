from __future__ import annotations

from helpers import FAKE_CORE, CliTestCase


class InitClaudePreservationTests(CliTestCase):
    def test_modified_claude_file_is_preserved_on_rerun(self) -> None:
        init_args = [
            "init",
            str(self.project),
            "--integration",
            "claude",
            "--core-cmd",
            str(FAKE_CORE),
            "--json",
        ]
        self.assertEqual(self.cli(init_args)[0], 0)
        skill = self.project / ".claude" / "skills" / "verifysignal-implement" / "SKILL.md"
        skill.write_text("user modified\n", encoding="utf-8")
        self.assertEqual(self.cli(init_args)[0], 0)
        self.assertEqual(skill.read_text(encoding="utf-8"), "user modified\n")
