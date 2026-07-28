from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path

from helpers import CliTestCase, FAKE_CORE
from tests.fixtures.workflows.golden_path_onboarding import assert_guidance_shape


class IntegrationOnboardingGuidanceContractTests(CliTestCase):
    def test_integration_install_returns_onboarding_guide_contract(self) -> None:
        code, out, err = self.cli(["integration", "install", "codex", "--project", str(self.project), "--json"])

        self.assertEqual(code, 0, err)
        data = json.loads(out)
        guide = data["onboardingGuide"]
        assert_guidance_shape(guide)
        self.assertEqual(guide["schemaVersion"], "verifysignal-spec-onboarding-guidance/v1")
        self.assertEqual(guide["integrationKey"], "codex")
        self.assertEqual(guide["nextCommand"], "$verifysignal")
        self.assertIn("[RECOMMENDED]", guide["stageMarkers"])
        self.assertIn("repaired", " ".join(guide["successSemantics"]).lower())
        self.assertIn("sensitive", " ".join(guide["safetyBoundaries"]).lower())
        self.assertEqual(data["mcp"]["path"], ".codex/config.toml")
        self.assertEqual(data["mcp"]["userRegistration"]["scope"], "user")
        self.assertEqual(
            data["mcp"]["userRegistration"]["status"],
            "skipped",
        )

    def test_integration_install_json_includes_ready_core_setup_contract(self) -> None:
        code, out, err = self.cli(["integration", "install", "codex", "--project", str(self.project), "--json"])

        self.assertEqual(code, 0, err)
        data = json.loads(out)
        core = data["coreSetup"]
        self.assertEqual(core["schemaVersion"], "verifysignal-spec-core-setup/v1")
        self.assertEqual(core["status"], "ready")
        self.assertEqual(core["source"], "env")
        self.assertEqual(core["coreCommand"], str(FAKE_CORE))
        self.assertEqual(core["selectedCandidate"]["status"], "compatible")
        self.assertIn("report.inspect", core["requiredOperationsByName"])
        self.assertEqual(data["onboardingGuide"]["coreStatus"]["statusMarker"], "[READY]")
        self.assertEqual(data["onboardingGuide"]["coreStatus"]["source"], "env")

    def test_integration_install_json_includes_missing_core_status_contract(self) -> None:
        os.environ["VERIFYSIGNAL_CORE_CMD"] = "missing-verifysignal-core-for-install-contract"

        code, out, err = self.cli(["integration", "install", "claude", "--project", str(self.project), "--json"])

        self.assertEqual(code, 0, err)
        data = json.loads(out)
        self.assertEqual(data["coreSetup"]["status"], "missing")
        self.assertEqual(data["onboardingGuide"]["coreStatus"]["statusMarker"], "[BLOCKED]")
        self.assertEqual(data["onboardingGuide"]["coreStatus"]["nextAction"], "verifysignal core setup --json")

    def test_integration_install_json_includes_incompatible_core_status_contract(self) -> None:
        os.environ["FAKE_VERIFYSIGNAL_MODE"] = "incompatible-run-schema"

        code, out, err = self.cli(["integration", "install", "claude", "--project", str(self.project), "--json"])

        self.assertEqual(code, 0, err)
        data = json.loads(out)
        self.assertEqual(data["coreSetup"]["status"], "incompatible")
        self.assertEqual(data["onboardingGuide"]["coreStatus"]["statusMarker"], "[INCOMPATIBLE]")
        self.assertEqual(data["coreSetup"]["incompatibleOperations"][0]["operationName"], "run")

    def test_integration_upgrade_json_includes_error_core_status_contract(self) -> None:
        failing = self.project / "bad-core"
        _write_executable(
            failing,
            "\n".join(
                [
                    f"#!{sys.executable}",
                    "import sys",
                    "sys.exit(9)",
                    "",
                ]
            ),
        )
        os.environ["VERIFYSIGNAL_CORE_CMD"] = str(failing)

        code, out, err = self.cli(["integration", "upgrade", "codex", "--project", str(self.project), "--json"])

        self.assertEqual(code, 0, err)
        data = json.loads(out)
        self.assertEqual(data["upgraded"][0]["coreSetup"]["status"], "error")
        self.assertEqual(data["upgraded"][0]["onboardingGuide"]["coreStatus"]["statusMarker"], "[ERROR]")


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
