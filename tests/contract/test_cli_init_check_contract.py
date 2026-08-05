from __future__ import annotations

import json
from unittest.mock import patch

from helpers import CliTestCase, FAKE_CORE
from verifysignal_spec.workspace.repository import init_workspace, load_document, save_core_configuration


class InitCheckContractTests(CliTestCase):
    def test_init_json_contract_and_check(self) -> None:
        code, out, err = self.cli(["init", str(self.project), "--integration", "codex", "--json"])
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertEqual(payload["integration"], "codex")
        self.assertTrue((self.project / ".verifysignal").exists())
        self.assertTrue((self.project / ".agents" / "skills" / "verifysignal-specify" / "SKILL.md").exists())
        self.assertFalse((self.project / ".agents" / "skills" / "verifysignal-spec-author" / "SKILL.md").exists())
        self.assertTrue(payload["core"]["compatible"])

        code, out, err = self.cli(["check", "--project", str(self.project), "--json"])
        self.assertEqual(code, 0, err)
        check = json.loads(out)
        self.assertEqual(check["schemaVersion"], "verifysignal-spec-check/v1")
        self.assertEqual(check["status"], "passed")

    def test_check_core_cmd_override_does_not_persist_to_workspace(self) -> None:
        code, _out, err = self.cli(["init", str(self.project), "--integration", "codex", "--core-cmd", str(FAKE_CORE), "--json"])
        self.assertEqual(code, 0, err)

        code, out, _err = self.cli(["check", "--project", str(self.project), "--core-cmd", "missing-verifysignal-core-for-check", "--json"])

        self.assertEqual(code, 2)
        payload = json.loads(out)
        workspace = load_document(self.project / ".verifysignal" / "workspace.yaml")
        self.assertEqual(payload["status"], "blocked")
        self.assertEqual(payload["managedRuntimeReadiness"]["runtimeCommand"], "missing-verifysignal-core-for-check")
        self.assertEqual(workspace["coreCommand"], str(FAKE_CORE))

    def test_explicit_init_persists_development_override_mode(self) -> None:
        code, _out, err = self.cli(
            ["init", str(self.project), "--integration", "codex", "--core-cmd", str(FAKE_CORE), "--json"]
        )

        self.assertEqual(code, 0, err)
        workspace = load_document(self.project / ".verifysignal" / "workspace.yaml")
        self.assertEqual(workspace["coreCommand"], str(FAKE_CORE))
        self.assertEqual(workspace["coreResolutionMode"], "development-override")

    def test_explicit_core_setup_persists_development_override_mode(self) -> None:
        code, out, err = self.cli(
            ["core", "setup", "--project", str(self.project), "--core-cmd", str(FAKE_CORE), "--json"]
        )

        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["status"], "ready")
        workspace = load_document(self.project / ".verifysignal" / "workspace.yaml")
        self.assertEqual(workspace["coreCommand"], str(FAKE_CORE))
        self.assertEqual(workspace["coreResolutionMode"], "development-override")

    def test_failed_explicit_init_keeps_fresh_workspace_managed_only(self) -> None:
        code, out, _err = self.cli(
            [
                "init",
                str(self.project),
                "--integration",
                "codex",
                "--core-cmd",
                "missing-explicit-core-for-init",
                "--json",
            ]
        )

        self.assertEqual(code, 2)
        self.assertEqual(json.loads(out)["status"], "blocked")
        workspace = load_document(self.project / ".verifysignal" / "workspace.yaml")
        self.assertNotIn("coreCommand", workspace)
        self.assertEqual(workspace["coreResolutionMode"], "managed-only")

    def test_failed_explicit_core_setup_preserves_existing_workspace(self) -> None:
        init_workspace(self.project)
        save_core_configuration(self.project, str(FAKE_CORE), source="explicit", version="0.1.0")
        workspace_path = self.project / ".verifysignal" / "workspace.yaml"
        before = workspace_path.read_bytes()

        with patch("verifysignal_spec.workspace.repository.now_iso", return_value="2099-01-01T00:00:00Z"):
            code, out, err = self.cli(
                [
                    "core",
                    "setup",
                    "--project",
                    str(self.project),
                    "--core-cmd",
                    "missing-explicit-core-for-setup",
                    "--json",
                ]
            )

        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["status"], "missing")
        self.assertEqual(workspace_path.read_bytes(), before)
