from __future__ import annotations

import json
import os
import time

from helpers import CliTestCase


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
