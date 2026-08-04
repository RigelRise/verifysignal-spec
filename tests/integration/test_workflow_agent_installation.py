from __future__ import annotations

from helpers import CliTestCase, assert_guardrail_template
from verifysignal_spec.integrations.manifests import load_manifest, save_manifest, sha256_bytes, sha256_text
from verifysignal_spec.workspace.models import AgentIntegrationState, ManagedFileRecord


class WorkflowAgentInstallationTests(CliTestCase):
    def test_claude_workflow_commands_install(self) -> None:
        code, _, err = self.cli(["init", str(self.project), "--integration", "claude", "--json"])
        self.assertEqual(code, 0, err)
        understand = self.project / ".claude" / "skills" / "verifysignal-understand" / "SKILL.md"
        plan = self.project / ".claude" / "skills" / "verifysignal-plan" / "SKILL.md"
        assert understand.exists()
        assert plan.exists()
        assert_guardrail_template(understand.read_text(encoding="utf-8"), "understand")
        assert_guardrail_template(plan.read_text(encoding="utf-8"), "plan")
        assert (self.project / "CLAUDE.md").read_text(encoding="utf-8").find("/verifysignal-*") >= 0

    def test_managed_files_are_written_with_the_bytes_their_hash_describes(self) -> None:
        # install_rendered_files hashes the rendered STRING and later re-reads the file's BYTES to
        # decide whether the user edited it. Python's text mode translates "\n" to os.linesep, so on
        # Windows those two never matched: every managed file was classified as user-modified
        # forever -- never refreshed, never removed on uninstall. `init` was silently non-idempotent.
        code, _, err = self.cli(["init", str(self.project), "--integration", "claude", "--json"])
        self.assertEqual(code, 0, err)

        manifest = load_manifest(self.project, "claude")
        assert manifest is not None
        self.assertTrue(manifest.managedFiles)

        for record in manifest.managedFiles:
            raw = (self.project / record.path).read_bytes()
            self.assertNotIn(b"\r\n", raw, f"{record.path} was written with CRLF")
            self.assertEqual(sha256_bytes(raw), record.sha256, f"{record.path} does not match its recorded hash")

    def test_reinstalling_does_not_report_untouched_files_as_user_modified(self) -> None:
        # The observable consequence of the above: a second `init` over an untouched workspace must
        # rewrite every managed file rather than preserving it as if the user had edited it.
        code, _, err = self.cli(["init", str(self.project), "--integration", "claude", "--json"])
        self.assertEqual(code, 0, err)
        first = load_manifest(self.project, "claude")
        assert first is not None

        code, _, err = self.cli(["init", str(self.project), "--integration", "claude", "--json"])
        self.assertEqual(code, 0, err)
        second = load_manifest(self.project, "claude")
        assert second is not None

        self.assertEqual(
            {item.path: item.sha256 for item in first.managedFiles},
            {item.path: item.sha256 for item in second.managedFiles},
        )

    def test_claude_upgrade_removes_previous_managed_legacy_skills(self) -> None:
        legacy_path = ".claude/skills/verifysignal-spec-author/SKILL.md"
        legacy = self.project / legacy_path
        legacy.parent.mkdir(parents=True, exist_ok=True)
        legacy_content = "old generated legacy skill\n"
        legacy.write_text(legacy_content, encoding="utf-8")
        save_manifest(
            self.project,
            AgentIntegrationState(
                key="claude",
                displayName="Claude Code",
                installedAt="2026-06-02T00:00:00Z",
                managedFiles=[ManagedFileRecord(path=legacy_path, sha256=sha256_text(legacy_content), source="claude/verifysignal-spec-author", kind="agent-skill")],
            ),
        )

        code, _, err = self.cli(["init", str(self.project), "--integration", "claude", "--json"])

        self.assertEqual(code, 0, err)
        self.assertFalse(legacy.exists())
