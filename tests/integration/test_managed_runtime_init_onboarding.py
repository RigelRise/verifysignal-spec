from __future__ import annotations

import json
import os
from pathlib import Path

from helpers import CliTestCase
from verifysignal_spec.runtime.distribution import normalize_platform
from verifysignal_spec.workspace.repository import get_core_command
from verifysignal_spec.workflows.stage_persistence import (
    _core_contract_for_browser_authoring,
)
from tests.fixtures.managed_runtime import build_managed_runtime_distribution, serve_fake_entitlement_backend


class ManagedRuntimeInitOnboardingTests(CliTestCase):
    def setUp(self) -> None:
        super().setUp()
        os.environ.pop("VERIFYSIGNAL_CORE_CMD", None)
        os.environ["VERIFYSIGNAL_RUNTIME_CACHE_DIR"] = str(self.project / "user-cache")
        os.environ["VERIFYSIGNAL_EMAIL_UNLOCK_TOKEN"] = "vs_valid"
        os.environ["VERIFYSIGNAL_CORE_VERSION"] = "0.5.1"

    def tearDown(self) -> None:
        os.environ.pop("VERIFYSIGNAL_RUNTIME_CACHE_DIR", None)
        os.environ.pop("VERIFYSIGNAL_EMAIL_UNLOCK_TOKEN", None)
        os.environ.pop("VERIFYSIGNAL_API_BASE_URL", None)
        os.environ.pop("VERIFYSIGNAL_CORE_VERSION", None)
        super().tearDown()

    def test_init_manages_runtime_without_manual_core_setup(self) -> None:
        payload = self._install_managed_runtime()

        assert payload["runtime"]["status"] == "ready"
        assert payload["runtime"]["source"] == "managed-download"
        assert payload["core"]["compatible"] is True
        workspace_text = (self.project / ".verifysignal" / "workspace.yaml").read_text(encoding="utf-8")
        guide_text = (self.project / ".agents" / "VERIFYSIGNAL_ONBOARDING.md").read_text(encoding="utf-8")
        assert "vs_valid" not in workspace_text + guide_text
        assert "core setup" not in guide_text.lower()

    def test_workflow_info_reuses_managed_runtime_without_core_override(self) -> None:
        init_payload = self._install_managed_runtime()
        os.environ.pop("VERIFYSIGNAL_EMAIL_UNLOCK_TOKEN", None)
        os.environ.pop("VERIFYSIGNAL_CORE_VERSION", None)
        os.environ.pop("VERIFYSIGNAL_API_BASE_URL", None)

        code, out, err = self.cli(
            [
                "workflow",
                "info",
                "verifysignal-use-case",
                "--project",
                str(self.project),
                "--json",
            ]
        )

        assert code == 0, err
        payload = json.loads(out)
        contract = payload["coreExecutableContract"]
        assert contract["coreVersion"] == init_payload["runtime"]["runtimeVersion"]
        assert contract["findings"] == []
        assert "navigate" in payload["browserAuthoringContract"]["validActions"]

    def test_core_version_reuses_managed_runtime_without_core_override(self) -> None:
        init_payload = self._install_managed_runtime()
        os.environ.pop("VERIFYSIGNAL_EMAIL_UNLOCK_TOKEN", None)
        os.environ.pop("VERIFYSIGNAL_CORE_VERSION", None)
        os.environ.pop("VERIFYSIGNAL_API_BASE_URL", None)

        code, out, err = self.cli(
            [
                "core",
                "version",
                "--project",
                str(self.project),
                "--json",
            ]
        )

        assert code == 0, err
        payload = json.loads(out)
        assert payload["schema"] == "verifysignal.version/v1"
        assert payload["status"] == "passed"
        # `runtimeVersion` reports the verified distribution's version while the Core
        # binary still reports its own, so the two are no longer interchangeable.
        # Reuse is proven by resolving and executing the managed runtime at all:
        # this workspace persists no Core command to fall back on.
        assert init_payload["runtime"]["source"] in {"managed-cache", "managed-download"}
        assert get_core_command(self.project) is None
        assert payload["data"]["verifysignalVersion"]

    def test_browser_authoring_reuses_managed_runtime_without_core_override(self) -> None:
        self._install_managed_runtime()
        os.environ.pop("VERIFYSIGNAL_EMAIL_UNLOCK_TOKEN", None)
        os.environ.pop("VERIFYSIGNAL_CORE_VERSION", None)
        os.environ.pop("VERIFYSIGNAL_API_BASE_URL", None)

        contract = _core_contract_for_browser_authoring(self.project)

        assert contract is not None
        assert contract["findings"] == []
        assert "navigate" in contract["sections"]["browserWorkflow"]["validActions"]

    def _install_managed_runtime(self) -> dict:
        platform = normalize_platform() or "darwin-arm64"
        distribution = build_managed_runtime_distribution(self.project / "distribution", platform=platform)
        with serve_fake_entitlement_backend(distribution) as (api_base_url, _state):
            os.environ["VERIFYSIGNAL_API_BASE_URL"] = api_base_url
            code, out, err = self.cli(["init", str(self.project), "--integration", "codex", "--json"])

        assert code == 0, err
        payload = json.loads(out)
        assert "vs_valid" not in out
        return payload
