"""The clean-machine acceptance leg must install through the EMBEDDED production anchor alone.

Core's release workflow signs with a private key that lives only in its Actions secrets; a
customer's clean install verifies with the production key embedded in this package. Nothing
proves the two halves correspond until an artifact signed with the real secret verifies under
the embedded anchor with NO release-trust environment in play. These tests pin the acceptance
script that closes that gap: it must refuse any environment-provided trust (env keys or the
test-key flag would mask a divergence), fail closed on a missing or test-key-signed release,
and synthesize the same manifest shape as scripts/ci/install_real_artifact.py.

The happy path needs an artifact signed by the production private key, which no test
environment has — the authoritative end-to-end proof is the embedded-anchor-acceptance job in
Core's release workflow. Everything that can drift is covered hermetically here.

Every subprocess run builds its environment explicitly: importing tests.fixtures.release_signing
(or managed_runtime) sets VERIFYSIGNAL_ALLOW_TEST_RELEASE_KEYS=1 process-wide at import time, so
the child env must strip both trust variables deterministically rather than inherit.
"""

from __future__ import annotations

import base64
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

from tests.fixtures.release_signing import TEST_RELEASE_KEY_ID, sign_release_metadata

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ci" / "install_with_embedded_anchor.py"
TRUST_ENV_VARS = (
    "VERIFYSIGNAL_RUNTIME_RELEASE_PUBLIC_KEYS",
    "VERIFYSIGNAL_ALLOW_TEST_RELEASE_KEYS",
)


def _clean_env(**extra: str) -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if key not in TRUST_ENV_VARS}
    env.update(extra)
    return env


def _run(artifact_dir: Path, **env_extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(artifact_dir)],
        env=_clean_env(**env_extra),
        capture_output=True,
        text=True,
        timeout=120,
    )


def _write_test_key_signed_release(artifact_dir: Path, platform: str) -> None:
    """Write a genuinely signed (TEST key) metadata + signature pair into ``artifact_dir``."""
    metadata = {
        "schema": "verifysignal.runtime-release/v1",
        "coreVersion": "0.5.1",
        "publicContractVersion": "verifysignal-public-cli-json/v1",
        "channel": "stable",
        "issuer": "https://verifysignal.io",
        "packages": [
            {
                "platform": platform,
                "filename": f"verifysignal-core-0.5.1-{platform}.tar.gz",
                "byteSize": 4,
                "sha256": "ab" * 32,
            }
        ],
    }
    metadata_b64, signature_block = sign_release_metadata(metadata)
    (artifact_dir / "verifysignal-core-release.json").write_bytes(base64.b64decode(metadata_b64))
    (artifact_dir / "verifysignal-core-release.json.sig").write_text(json.dumps(signature_block))
    (artifact_dir / f"verifysignal-core-0.5.1-{platform}.tar.gz").write_bytes(b"tarb")


def test_rejects_an_env_trust_map(tmp_path: Path) -> None:
    result = _run(tmp_path, VERIFYSIGNAL_RUNTIME_RELEASE_PUBLIC_KEYS="{}")
    assert result.returncode != 0
    assert "VERIFYSIGNAL_RUNTIME_RELEASE_PUBLIC_KEYS" in result.stderr


def test_rejects_the_test_key_flag(tmp_path: Path) -> None:
    result = _run(tmp_path, VERIFYSIGNAL_ALLOW_TEST_RELEASE_KEYS="1")
    assert result.returncode != 0
    assert "VERIFYSIGNAL_ALLOW_TEST_RELEASE_KEYS" in result.stderr


def test_fails_without_metadata_or_signature(tmp_path: Path) -> None:
    result = _run(tmp_path)
    assert result.returncode != 0
    assert "no built release" in result.stderr


def test_rejects_a_test_key_signed_artifact(tmp_path: Path) -> None:
    """Anti-vacuity: a REAL signature by the wrong (test) key must fail the embedded anchor."""
    _write_test_key_signed_release(tmp_path, platform="linux-x64")
    result = _run(tmp_path)
    assert result.returncode != 0
    assert "embedded production anchor" in result.stderr
    assert TEST_RELEASE_KEY_ID in result.stderr


def test_manifest_synthesis_matches_the_real_artifact_leg(tmp_path: Path) -> None:
    """The synthesized manifest must carry the exact shape install_real_artifact.py produces."""
    spec = importlib.util.spec_from_file_location("install_with_embedded_anchor", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    artifact_dir = tmp_path / "artifact"
    artifact_dir.mkdir()
    _write_test_key_signed_release(artifact_dir, platform="linux-x64")
    meta_bytes = (artifact_dir / "verifysignal-core-release.json").read_bytes()
    signature = json.loads((artifact_dir / "verifysignal-core-release.json.sig").read_text())

    workdir = tmp_path / "work"
    workdir.mkdir()
    manifest_path = module.synthesize_manifest(artifact_dir, workdir, platform="linux-x64")

    manifest = json.loads(Path(manifest_path).read_text())
    assert len(manifest["entries"]) == 1
    entry = manifest["entries"][0]
    assert entry["coreVersion"] == "0.5.1"
    assert entry["contractVersion"] == "verifysignal-public-cli-json/v1"
    assert entry["platform"] == "linux-x64"
    assert entry["url"].startswith("file://")
    assert entry["url"].endswith("verifysignal-core-0.5.1-linux-x64.tar.gz")
    assert entry["filename"] == "verifysignal-core-0.5.1-linux-x64.tar.gz"
    assert entry["byteSize"] == 4
    assert entry["sha256"] == "ab" * 32
    assert base64.b64decode(entry["releaseMetadataBytes"]) == meta_bytes
    assert entry["signature"] == signature
