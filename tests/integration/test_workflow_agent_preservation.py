from __future__ import annotations

from helpers import FAKE_CORE, CliTestCase


class WorkflowAgentPreservationTests(CliTestCase):
    def test_existing_user_modified_workflow_skill_is_preserved(self) -> None:
        skill = self.project / ".agents" / "skills" / "verifysignal-understand" / "SKILL.md"
        skill.parent.mkdir(parents=True, exist_ok=True)
        skill.write_text("user edited\n", encoding="utf-8")
        code, _, err = self.cli(
            [
                "init",
                str(self.project),
                "--integration",
                "codex",
                "--core-cmd",
                str(FAKE_CORE),
                "--json",
            ]
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(skill.read_text(encoding="utf-8"), "user edited\n")
