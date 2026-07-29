"""Install a real Core-built runtime package through the managed installer.

Cross-repo guard: each repo's own tests exercise its own fixture layout, so a
divergence between Core's packaged archive layout and this installer would ship
silently. This test consumes an actual artifact from ``dist/runtime`` in the
sibling Core repo when one exists and skips cleanly otherwise. Core is located by
identity (see ``verifysignal_spec.repos``), never by directory name.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from verifysignal_spec.core.adapter import CoreAdapter
from verifysignal_spec.core.contracts import PUBLIC_CONTRACT_VERSION
from verifysignal_spec.runtime.distribution import install_from_manifest, normalize_platform

from tests.fixtures.release_signing import signed_manifest_entry
from tests.helpers import resolve_sibling_repo


def _discover_real_artifact() -> Path | None:
    override = os.environ.get("VERIFYSIGNAL_REAL_CORE_ARTIFACT")
    if override:
        path = Path(override).expanduser()
        return path if path.is_file() else None
    platform = normalize_platform()
    if platform is None:
        return None
    # By identity, never by directory name: this used to join a literal "verifysignal", so the whole
    # test skipped on any checkout that called Core something else — a clean skip that looked like
    # "nothing to check" rather than "the guard is off".
    core_repo = resolve_sibling_repo("core", Path(__file__).resolve().parents[2])
    if core_repo is None:
        return None
    dist_dir = core_repo / "dist" / "runtime"
    if not dist_dir.is_dir():
        return None
    candidates: list[tuple[tuple[int, int, int], Path]] = []
    for artifact in dist_dir.glob(f"verifysignal-core-*-{platform}.tar.gz"):
        match = re.match(r"verifysignal-core-(\d+)\.(\d+)\.(\d+)-", artifact.name)
        if match:
            candidates.append((tuple(int(part) for part in match.groups()), artifact))
    if not candidates:
        return None
    return max(candidates)[1]


REAL_ARTIFACT = _discover_real_artifact()


def _artifact_version(artifact: Path) -> str:
    match = re.match(r"verifysignal-core-(\d+\.\d+\.\d+)-", artifact.name)
    assert match is not None
    return match.group(1)


@pytest.mark.skipif(REAL_ARTIFACT is None, reason="no real Core runtime artifact available")
@pytest.mark.skipif(shutil.which("node") is None, reason="node is required to run the packaged runtime")
def test_real_core_artifact_installs_and_serves_the_public_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert REAL_ARTIFACT is not None
    monkeypatch.setenv("VERIFYSIGNAL_RUNTIME_CACHE_DIR", str(tmp_path / "cache"))
    platform = normalize_platform()
    assert platform is not None
    core_version = _artifact_version(REAL_ARTIFACT)
    # Sign the real artifact's release metadata with the TEST release key so the managed
    # installer verifies a genuine detached Ed25519 signature over the real archive sha256.
    entry = signed_manifest_entry(
        platform=platform,
        sha256=hashlib.sha256(REAL_ARTIFACT.read_bytes()).hexdigest(),
        contract=PUBLIC_CONTRACT_VERSION,
        coreVersion=core_version,
        artifactName=REAL_ARTIFACT.name,
        url=REAL_ARTIFACT.as_uri(),
    )

    command, blocker = install_from_manifest(entry)

    assert blocker is None
    assert command is not None
    assert command.endswith("verifysignal-core/bin/verifysignal-core")
    assert os.access(command, os.X_OK)

    compat = CoreAdapter(executable=command, cwd=tmp_path).check_compatibility()
    assert compat.compatible
    assert compat.contractVersion == PUBLIC_CONTRACT_VERSION
    assert compat.verifysignalVersion == core_version

    raw = subprocess.run(
        [command, "version", "--json"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=120,
        check=True,
    )
    envelope = json.loads(raw.stdout)
    assert envelope["schema"] == "verifysignal.version/v1"
