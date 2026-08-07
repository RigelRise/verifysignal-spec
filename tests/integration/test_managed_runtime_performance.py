from __future__ import annotations

import json
import os
import time
from unittest.mock import patch

from helpers import CliTestCase, FAKE_CORE
from verifysignal_spec.workspace.repository import init_workspace


class ManagedRuntimePerformanceTests(CliTestCase):
    def tearDown(self) -> None:
        os.environ.pop("VERIFYSIGNAL_RUNTIME_CACHE_DIR", None)
        super().tearDown()

    def test_blocker_classification_completes_quickly_without_runtime(self) -> None:
        os.environ.pop("VERIFYSIGNAL_CORE_CMD", None)
        os.environ["VERIFYSIGNAL_RUNTIME_CACHE_DIR"] = str(self.project / "empty-cache")

        start = time.monotonic()
        code, out, err = self.cli(["check", "--project", str(self.project), "--json"])
        elapsed = time.monotonic() - start

        assert code == 2, err
        payload = json.loads(out)
        readiness = payload["managedRuntimeReadiness"]
        assert readiness["status"] == "blocked"
        assert readiness["source"] == "none"
        assert readiness["cache"]["status"] == "miss"
        assert [blocker["code"] for blocker in readiness["blockers"]] == [
            "entitlement.unlock-required"
        ]
        assert readiness["attempts"][-1]["source"] == "managed-download"
        assert readiness["attempts"][-1]["blockerCode"] == (
            "entitlement.unlock-required"
        )
        assert elapsed < 1

    def test_missing_workspace_does_not_scan_automatic_local_core_sources(self) -> None:
        os.environ.pop("VERIFYSIGNAL_CORE_CMD", None)
        os.environ["VERIFYSIGNAL_RUNTIME_CACHE_DIR"] = str(
            self.project / "empty-cache"
        )

        with patch(
            "verifysignal_spec.runtime.resolver._ancestor_sibling_paths",
            side_effect=AssertionError("missing-workspace check scanned local Core"),
        ):
            code, out, err = self.cli(
                ["check", "--project", str(self.project), "--json"]
            )

        assert code == 2, err
        readiness = json.loads(out)["managedRuntimeReadiness"]
        assert readiness["status"] == "blocked"
        assert readiness["source"] == "none"

    def test_missing_workspace_preserves_explicit_one_shot_core_override(self) -> None:
        with patch(
            "verifysignal_spec.runtime.resolver._ancestor_sibling_paths",
            side_effect=AssertionError("explicit check scanned local Core"),
        ):
            code, out, err = self.cli(
                [
                    "check",
                    "--project",
                    str(self.project),
                    "--core-cmd",
                    str(FAKE_CORE),
                    "--json",
                ]
            )

        assert code == 2, err
        readiness = json.loads(out)["managedRuntimeReadiness"]
        assert readiness["status"] == "ready"
        assert readiness["source"] == "explicit"

    def test_existing_workspace_keeps_its_persisted_managed_only_mode(self) -> None:
        init_workspace(self.project)
        os.environ["VERIFYSIGNAL_RUNTIME_CACHE_DIR"] = str(
            self.project / "empty-cache"
        )

        with patch(
            "verifysignal_spec.runtime.resolver._ancestor_sibling_paths",
            side_effect=AssertionError("managed-only workspace scanned local Core"),
        ):
            code, out, err = self.cli(
                ["check", "--project", str(self.project), "--json"]
            )

        assert code == 2, err
        readiness = json.loads(out)["managedRuntimeReadiness"]
        assert readiness["status"] == "blocked"
        assert readiness["source"] == "none"
