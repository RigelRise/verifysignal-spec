from __future__ import annotations

import os
import unittest

from helpers import CliTestCase, FAKE_CORE


def test_base_environment_restore_runs_after_nested_cleanups(monkeypatch) -> None:
    monkeypatch.delenv("VERIFYSIGNAL_CORE_CMD", raising=False)

    class NestedCleanupCase(CliTestCase):
        def test_nested_cleanup(self) -> None:
            captured = os.environ["VERIFYSIGNAL_CORE_CMD"]
            assert captured == str(FAKE_CORE)
            os.environ.pop("VERIFYSIGNAL_CORE_CMD")
            self.addCleanup(
                lambda: os.environ.__setitem__("VERIFYSIGNAL_CORE_CMD", captured)
            )

    result = unittest.TestResult()
    NestedCleanupCase("test_nested_cleanup").run(result)

    assert result.wasSuccessful(), result.errors + result.failures
    assert "VERIFYSIGNAL_CORE_CMD" not in os.environ
