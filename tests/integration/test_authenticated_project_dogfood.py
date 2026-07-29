from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from verifysignal_spec.repos import resolve_sibling_repo

SPEC_REPO = Path(__file__).resolve().parents[2]
# By identity, never by directory name: this used to join a literal "verifysignal", so on a checkout
# that called Core anything else the dogfood skipped as "sibling not present" — and the required-mode
# guard below never fired because the repo genuinely looked absent.
CORE_REPO = resolve_sibling_repo("core", SPEC_REPO)
RUNNER = SPEC_REPO / "scripts/dogfood/authenticated_project_red_green.py"


def test_public_spec_to_real_core_structural_dogfood_is_green() -> None:
    # Resolution already confirmed the manifest identity, so "resolved" IS "present".
    if CORE_REPO is None:
        if os.environ.get("VERIFYSIGNAL_REQUIRE_CROSSREPO_DOGFOOD") == "1":
            pytest.fail("The required sibling Core source repository is not present.")
        pytest.skip("The sibling Core source repository is not present.")

    child = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "--core-repo",
            str(CORE_REPO),
        ],
        cwd=SPEC_REPO,
        text=True,
        capture_output=True,
        check=False,
        timeout=120,
    )

    assert child.returncode == 0, child.stderr or child.stdout
    result = json.loads(child.stdout)
    assert result["schema"] == "verifysignal.cross-repo-dogfood/v1"
    assert result["status"] == "green"
    assert result["gates"] == {
        "discoverControl": "passed",
        "probe": "passed",
        "canonicalPersistence": "passed",
        "validate": "passed",
        "runReadiness": "passed",
        "run": "passed",
    }
    assert result["observations"]["runReadiness"]["status"] == "ready"
    assert result["observations"]["runReadiness"]["canProceed"] is True
    assert result["observations"]["runAuthorization"]["mode"] in {
        "isolated-local-invocation",
        "confirm-risk",
    }
    assert result["state"]["afterProbe"] == {
        "emailChecks": 1,
        "signIns": 1,
        "mediaLookups": 1,
        "commits": 0,
        "resourceCount": 0,
    }
    assert result["state"]["afterRunReadiness"] == result["state"]["afterProbe"]
    assert result["state"]["afterRun"] == {
        "emailChecks": 2,
        "signIns": 2,
        "mediaLookups": 2,
        "commits": 1,
        "resourceCount": 1,
    }
