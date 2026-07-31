"""RATCHET (customer-journey orchestrator guards). The product-truth gate's journey leg drives
``scripts/ci/customer_journey.py``: BE issues a real receipt over HTTP, Spec installs the
packaged Core from the BE, and every protected leg executes the INSTALLED runtime. The whole
point is that nothing can fake the journey, so the script's fail-closed door is pinned:

- any env var that would let the journey pass WITHOUT touching the BE or the packaged runtime
  must abort before anything else runs: ``VERIFYSIGNAL_ALLOW_TEST_RELEASE_KEYS`` (release trust
  must be the explicit env map the script builds itself), ``VERIFYSIGNAL_RUNTIME_MANIFEST_PATH``
  / ``_JSON`` (the file:// manifest short-circuits the HTTP download), and
  ``VERIFYSIGNAL_ENTITLEMENT_PUBLIC_KEYS_JSON`` / ``_RECEIPT`` / ``_RECEIPT_PATH`` /
  ``VERIFYSIGNAL_CORE_CMD`` (a pre-provisioned trust store, receipt, or source Core would make
  the BE-issued receipt and the managed download decorative).
- the guards run BEFORE sibling resolution, so these tests need no sibling checkouts and stay
  green inside the gate's own Spec-suite step.
- the script text may never invoke ``--core-cmd`` (protected legs must execute the installed
  runtime) and may never import the managed-runtime test fixture (importing it silently enables
  the committed test release key for the whole process).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/ci/customer_journey.py"

POISONED = [
    ("VERIFYSIGNAL_ALLOW_TEST_RELEASE_KEYS", "1"),
    ("VERIFYSIGNAL_RUNTIME_MANIFEST_PATH", "/tmp/manifest.json"),
    ("VERIFYSIGNAL_RUNTIME_MANIFEST_JSON", "{}"),
    ("VERIFYSIGNAL_ENTITLEMENT_PUBLIC_KEYS_JSON", "{}"),
    ("VERIFYSIGNAL_ENTITLEMENT_RECEIPT", "/tmp/receipt.json"),
    ("VERIFYSIGNAL_ENTITLEMENT_RECEIPT_PATH", "/tmp/receipt.json"),
    ("VERIFYSIGNAL_CORE_CMD", "/tmp/core"),
]


def _run_script(extra_env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("VERIFYSIGNAL_")
    }
    env.update(extra_env)
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
        cwd=ROOT,
    )


def test_script_exists() -> None:
    assert SCRIPT.exists()


@pytest.mark.parametrize(("name", "value"), POISONED)
def test_poisoned_env_fails_closed_before_anything_else(name: str, value: str) -> None:
    result = _run_script({name: value})
    assert result.returncode == 1
    assert "FAIL:" in result.stderr
    assert name in result.stderr


def test_script_never_reaches_for_the_shortcuts() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "--core-cmd" not in text
    assert "managed_runtime" not in text
    assert 'VERIFYSIGNAL_ALLOW_TEST_RELEASE_KEYS"] = ' not in text
    assert '"VERIFYSIGNAL_ALLOW_TEST_RELEASE_KEYS": ' not in text
