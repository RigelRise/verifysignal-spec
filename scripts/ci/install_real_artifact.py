"""Cross-repo gate leg: clean-cache install of the REAL sibling Core artifact, production-shaped.

Consumes the release metadata + detached signature the gate just built (signed with the job's
EPHEMERAL keypair — no committed test keys, no VERIFYSIGNAL_ALLOW_TEST_RELEASE_KEYS), builds a
distribution manifest from them, installs through the SAME code path a customer install uses
(load_manifest → select_manifest_entry → install_from_manifest, with sha256 + Ed25519 verification),
and executes the installed runtime. Exits non-zero on any blocker — including a skip, which would
mean the gate proved nothing.

Requires: VERIFYSIGNAL_RUNTIME_RELEASE_PUBLIC_KEYS in the environment (the ephemeral public key),
and the sibling Core checkout with dist/runtime built. Usage:
  python scripts/ci/install_real_artifact.py [core-checkout-path]

The path argument is optional: without it, Core is located by identity (see scripts/sibling_repos.py)
rather than by a hardcoded directory name, so this works whether the checkout is called `verifysignal`
or `verifysignal-core`. VERIFYSIGNAL_CORE_DIR pins it explicitly.
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

from verifysignal_spec.repos import resolve_sibling_repo


def current_platform() -> str:
    if sys.platform == "darwin":
        return "darwin-arm64" if platform_module.machine() == "arm64" else "darwin-x64"
    return "linux-x64"


def main() -> int:
    if len(sys.argv) > 1:
        core = Path(sys.argv[1]).resolve()
    else:
        resolved = resolve_sibling_repo("core")
        if resolved is None:
            print(
                "FAIL: no Core checkout found alongside this repo — pass its path or set "
                "VERIFYSIGNAL_CORE_DIR",
                file=sys.stderr,
            )
            return 1
        core = resolved
    meta_path = core / "dist/runtime/verifysignal-core-release.json"
    sig_path = core / "dist/runtime/verifysignal-core-release.json.sig"
    if not meta_path.exists() or not sig_path.exists():
        print(f"FAIL: no built release at {meta_path.parent} — run runtime:package first", file=sys.stderr)
        return 1
    if not os.environ.get("VERIFYSIGNAL_RUNTIME_RELEASE_PUBLIC_KEYS"):
        print("FAIL: VERIFYSIGNAL_RUNTIME_RELEASE_PUBLIC_KEYS is not set — the install would fail closed", file=sys.stderr)
        return 1
    if os.environ.get("VERIFYSIGNAL_ALLOW_TEST_RELEASE_KEYS"):
        print("FAIL: VERIFYSIGNAL_ALLOW_TEST_RELEASE_KEYS is set — this leg must be production-shaped", file=sys.stderr)
        return 1

    meta_bytes = meta_path.read_bytes()
    meta = json.loads(meta_bytes)
    signature = json.loads(sig_path.read_text())
    plat = current_platform()
    package = next((entry for entry in meta["packages"] if entry["platform"] == plat), None)
    if package is None:
        print(f"FAIL: no package for platform {plat} in the release metadata", file=sys.stderr)
        return 1

    workdir = Path(tempfile.mkdtemp(prefix="vs-gate-install-"))
    manifest = workdir / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "coreVersion": meta["coreVersion"],
                        "contractVersion": meta["publicContractVersion"],
                        "platform": plat,
                        "url": (core / "dist/runtime" / package["filename"]).as_uri(),
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
    entry = select_manifest_entry(manifest_entries(loaded), platform=plat)
    command, blocker = install_from_manifest(entry)
    if blocker is not None or command is None:
        code = getattr(blocker, "code", "unknown")
        message = getattr(blocker, "message", blocker)
        print(f"FAIL: install blocked: {code}: {message}", file=sys.stderr)
        return 1

    probe = subprocess.run([command, "version", "--json"], capture_output=True, text=True, timeout=120)
    payload = json.loads(probe.stdout)
    print(
        "PASS: clean-cache install consumed the production-shaped signature and ran:",
        payload["data"]["verifysignalVersion"],
        payload["data"]["contractVersion"],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
