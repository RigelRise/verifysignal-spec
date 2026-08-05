from __future__ import annotations

import json
import time

from helpers import CliTestCase, FAKE_CORE
from verifysignal_spec.workspace.repository import load_document


class InitCodexIntegrationTests(CliTestCase):
    def test_fresh_init_completes_quickly_and_installs_codex(self) -> None:
        started = time.monotonic()
        code, _, err = self.cli(
            ["init", str(self.project), "--integration", "codex", "--core-cmd", str(FAKE_CORE), "--json"]
        )
        elapsed = time.monotonic() - started
        self.assertEqual(code, 0, err)
        self.assertLess(elapsed, 300)
        self.assertTrue((self.project / ".verifysignal" / "workspace.yaml").exists())
        self.assertTrue((self.project / "AGENTS.md").exists())

    def test_init_with_core_repo_directory_persists_resolved_runtime_command(self) -> None:
        core_repo = self.project / "verifysignal-core"
        core_repo.mkdir()
        (core_repo / "package.json").write_text(
            json.dumps({"scripts": {"verifysignal:dev": str(FAKE_CORE)}}),
            encoding="utf-8",
        )

        code, out, err = self.cli(
            [
                "init",
                str(self.project),
                "--integration",
                "codex",
                "--core-cmd",
                str(core_repo),
                "--json",
            ]
        )

        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        workspace = load_document(self.project / ".verifysignal" / "workspace.yaml")
        self.assertEqual(payload["runtime"]["source"], "explicit")
        self.assertEqual(workspace["coreCommand"], payload["runtime"]["runtimeCommand"])
        self.assertNotEqual(workspace["coreCommand"], str(core_repo))
        self.assertIn("verifysignal:dev", workspace["coreCommand"])

    def test_init_with_invalid_core_command_does_not_persist_unverified_command(self) -> None:
        code, out, _err = self.cli(
            [
                "init",
                str(self.project),
                "--integration",
                "codex",
                "--core-cmd",
                "missing-verifysignal-core-for-init",
                "--json",
            ]
        )

        self.assertEqual(code, 2)
        payload = json.loads(out)
        workspace = load_document(self.project / ".verifysignal" / "workspace.yaml")
        self.assertEqual(payload["status"], "blocked")
        self.assertNotEqual(payload["coreSetup"]["status"], "ready")
        self.assertEqual(payload["coreSetup"]["coreCommand"], "missing-verifysignal-core-for-init")
        self.assertNotIn("coreCommand", workspace)
