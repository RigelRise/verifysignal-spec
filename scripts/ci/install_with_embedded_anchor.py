"""Release acceptance leg: clean-machine install through the EMBEDDED production anchor.

This is the inverse of scripts/ci/install_real_artifact.py. That leg REQUIRES
VERIFYSIGNAL_RUNTIME_RELEASE_PUBLIC_KEYS (the gate's ephemeral public key); this leg FORBIDS
all release-trust environment, so the only key that can verify the release is the production
anchor embedded in the installed verifysignal_spec package. It exists to prove, on every real
release, that the private key in Core's Actions secrets corresponds to the public key customers
actually ship with — a divergence would otherwise stay green in CI and fail every clean
customer install with artifact.authenticity-failed.

The happy path needs an artifact signed by the real production private key, which exists only
in Core's release workflow — its embedded-anchor-acceptance job is the authoritative end-to-end
proof. The guards, manifest synthesis, and test-key rejection are unit-tested hermetically in
tests/unit/test_install_with_embedded_anchor.py.

Usage:
  python scripts/ci/install_with_embedded_anchor.py <artifact-dir>

<artifact-dir> is a downloaded release-artifact directory (verifysignal-core-release.json,
its .sig, and the platform tarballs) — not a repository checkout, so it is always passed
explicitly rather than resolved by sibling identity.
"""

from __future__ import annotations

import base64
import json
import os
import platform as platform_module
import subprocess
import sys
import tempfile
from pathlib import Path

from verifysignal_spec.runtime.release_signature import verify_release_signature

PRODUCTION_KEY_ID = "verifysignal-core-release-2026"
FORBIDDEN_TRUST_ENV = (
    "VERIFYSIGNAL_RUNTIME_RELEASE_PUBLIC_KEYS",
    "VERIFYSIGNAL_ALLOW_TEST_RELEASE_KEYS",
)


def current_platform() -> str:
    if sys.platform == "darwin":
        return "darwin-arm64" if platform_module.machine() == "arm64" else "darwin-x64"
    return "linux-x64"


def guard_environment(environ: dict[str, str] | os._Environ[str] = os.environ) -> str | None:
    """Return a failure message when any release-trust environment is present.

    This leg proves the EMBEDDED anchor alone; environment-provided trust (extra keys or the
    committed test key) would let a secret/anchor divergence pass unnoticed.
    """
    for name in FORBIDDEN_TRUST_ENV:
        if environ.get(name):
            return f"{name} is set — this leg must trust only the embedded production anchor"
    return None


def synthesize_manifest(artifact_dir: Path, workdir: Path, platform: str | None = None) -> Path:
    """Build the one-entry distribution manifest install_real_artifact.py builds, from a
    downloaded artifact directory instead of a Core checkout."""
    plat = platform or current_platform()
    meta_path = artifact_dir / "verifysignal-core-release.json"
    meta_bytes = meta_path.read_bytes()
    meta = json.loads(meta_bytes)
    signature = json.loads((artifact_dir / "verifysignal-core-release.json.sig").read_text())
    package = next((entry for entry in meta["packages"] if entry["platform"] == plat), None)
    if package is None:
        raise ValueError(f"no package for platform {plat} in the release metadata")
    manifest = workdir / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "coreVersion": meta["coreVersion"],
                        "contractVersion": meta["publicContractVersion"],
                        "platform": plat,
                        "url": (artifact_dir / package["filename"]).resolve().as_uri(),
                        "filename": package["filename"],
                        "byteSize": package["byteSize"],
                        "sha256": package["sha256"],
                        "releaseMetadataBytes": base64.b64encode(meta_bytes).decode(),
                        "signature": signature,
                    }
                ]
            }
        )
    )
    return manifest


def main() -> int:
    guard = guard_environment()
    if guard is not None:
        print(f"FAIL: {guard}", file=sys.stderr)
        return 1
    if len(sys.argv) < 2:
        print(
            "FAIL: usage: install_with_embedded_anchor.py <artifact-dir>",
            file=sys.stderr,
        )
        return 1
    artifact_dir = Path(sys.argv[1]).resolve()
    meta_path = artifact_dir / "verifysignal-core-release.json"
    sig_path = artifact_dir / "verifysignal-core-release.json.sig"
    if not meta_path.exists() or not sig_path.exists():
        print(f"FAIL: no built release at {artifact_dir}", file=sys.stderr)
        return 1

    meta_bytes = meta_path.read_bytes()
    signature = json.loads(sig_path.read_text())
    # With both trust env vars absent, the default trust set is exactly the embedded anchor —
    # a successful verification here IS the correspondence proof.
    ok, key_id = verify_release_signature(meta_bytes, signature)
    if not ok or key_id != PRODUCTION_KEY_ID:
        print(
            "FAIL: release signature does not verify under the embedded production anchor "
            f"(signature keyId={signature.get('keyId')!r}, expected {PRODUCTION_KEY_ID!r})",
            file=sys.stderr,
        )
        return 1

    workdir = Path(tempfile.mkdtemp(prefix="vs-anchor-accept-"))
    try:
        manifest = synthesize_manifest(artifact_dir, workdir)
    except ValueError as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1

    os.environ["VERIFYSIGNAL_RUNTIME_MANIFEST_PATH"] = str(manifest)
    os.environ["VERIFYSIGNAL_RUNTIME_CACHE_DIR"] = str(workdir / "cache")

    from verifysignal_spec.runtime.distribution import (
        install_from_manifest,
        load_manifest,
        manifest_entries,
        select_manifest_entry,
    )

    loaded, blocker = load_manifest()
    if blocker is not None or loaded is None:
        print(f"FAIL: manifest load blocked: {blocker}", file=sys.stderr)
        return 1
    entry = select_manifest_entry(manifest_entries(loaded), platform=current_platform())
    command, blocker = install_from_manifest(entry)
    if blocker is not None or command is None:
        code = getattr(blocker, "code", "unknown")
        message = getattr(blocker, "message", blocker)
        print(f"FAIL: install blocked: {code}: {message}", file=sys.stderr)
        return 1

    probe = subprocess.run([command, "version", "--json"], capture_output=True, text=True, timeout=120)
    payload = json.loads(probe.stdout)
    import verifysignal_spec

    print(
        f"PASS: clean-machine install verified through embedded anchor keyId={PRODUCTION_KEY_ID}:",
        payload["data"]["verifysignalVersion"],
        payload["data"]["contractVersion"],
        f"(verifysignal_spec from {verifysignal_spec.__file__})",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
