from __future__ import annotations

import json
import os
import re

from helpers import CliTestCase


class IntegrationOnboardingGuidanceIntegrationTests(CliTestCase):
    def test_codex_install_prints_guidance_and_writes_local_guide(self) -> None:
        code, out, err = self.cli(["integration", "install", "codex", "--project", str(self.project)])

        self.assertEqual(code, 0, err)
        self.assertIn("VerifySignal Golden Path", out)
        self.assertIn("VerifySignal Core: [READY]", out)
        self.assertIn("Source: env", out)
        self.assertIn("[RECOMMENDED]", out)
        self.assertIn("$verifysignal", out)
        self.assertIsNone(
            re.search(r"(?<![\w./-])/verifysignal(?:-[a-z0-9*-]+)?", out)
        )
        self.assertIn(".codex/config.toml", out)

        guide_path = self.project / ".agents" / "VERIFYSIGNAL_ONBOARDING.md"
        self.assertTrue(guide_path.exists())
        content = guide_path.read_text(encoding="utf-8")
        self.assertIn("Core Runtime", content)
        self.assertIn("VerifySignal Core is ready", content)
        self.assertIn("Safety Boundaries", content)
        self.assertIn("Repaired strict pass", content)
        self.assertIn("$verifysignal", content)
        self.assertIsNone(
            re.search(r"(?<![\w./-])/verifysignal(?:-[a-z0-9*-]+)?", content)
        )

    def test_claude_install_prints_guidance_and_writes_local_guide(self) -> None:
        code, out, err = self.cli(["integration", "install", "claude", "--project", str(self.project)])

        self.assertEqual(code, 0, err)
        self.assertIn("VerifySignal Golden Path", out)
        self.assertIn("VerifySignal Core: [READY]", out)
        self.assertIn("[PASS]", out)

        guide_path = self.project / ".claude" / "VERIFYSIGNAL_ONBOARDING.md"
        self.assertTrue(guide_path.exists())
        self.assertIn("/verifysignal-specify", guide_path.read_text(encoding="utf-8"))

    def test_upgrade_includes_guidance_for_each_result(self) -> None:
        code, out, err = self.cli(["integration", "upgrade", "--project", str(self.project), "--json"])

        self.assertEqual(code, 0, err)
        data = json.loads(out)
        self.assertTrue(data["upgraded"])
        self.assertTrue(all("onboardingGuide" in item for item in data["upgraded"]))
        self.assertTrue(all("coreSetup" in item for item in data["upgraded"]))
        self.assertTrue(all(item["onboardingGuide"]["coreStatus"]["statusMarker"] == "[READY]" for item in data["upgraded"]))

    def test_install_missing_core_prints_blocked_status_and_guide_recovery(self) -> None:
        os.environ["VERIFYSIGNAL_CORE_CMD"] = "missing-verifysignal-core-for-guide-test"

        code, out, err = self.cli(["integration", "install", "claude", "--project", str(self.project)])

        self.assertEqual(code, 0, err)
        self.assertIn("VerifySignal Core: [BLOCKED]", out)
        self.assertIn("full validation and browser execution require Core", out)
        self.assertIn("Next: verifysignal core setup --json", out)

        guide_path = self.project / ".claude" / "VERIFYSIGNAL_ONBOARDING.md"
        content = guide_path.read_text(encoding="utf-8")
        self.assertIn("Core Runtime", content)
        self.assertIn("Specification, understanding, planning, task generation, and artifact authoring can continue without Core.", content)
        self.assertIn("verifysignal core setup --json", content)

    def test_install_incompatible_core_prints_incompatible_status(self) -> None:
        os.environ["FAKE_VERIFYSIGNAL_MODE"] = "incompatible-run-schema"

        code, out, err = self.cli(["integration", "install", "codex", "--project", str(self.project)])

        self.assertEqual(code, 0, err)
        self.assertIn("VerifySignal Core: [INCOMPATIBLE]", out)
        self.assertIn("does not satisfy required operations", out)
