from __future__ import annotations

import base64
import hashlib
from pathlib import Path

from verifysignal_spec.runtime.distribution import (
    _force_rmtree,
    _sweep_stale_swaps,
    install_from_manifest,
    manifest_entries,
    normalize_platform,
    select_manifest_entry,
    signature_contract_available,
    verify_release_authenticity,
    verify_sha256,
)

from tests.fixtures.release_signing import sign_release_metadata, signed_manifest_entry


def _entry_with_signed_metadata(metadata: dict, *, sha256: str, platform: str = "darwin-arm64") -> dict:
    """Build an entry around genuinely-signed `metadata` so the Ed25519 signature verifies and
    only the downstream cross-checks (sha / publicContractVersion) are under test."""
    metadata_b64, signature = sign_release_metadata(metadata)
    return {
        "coreVersion": "0.5.1",
        "contractVersion": "verifysignal-public-cli-json/v1",
        "platform": platform,
        "url": "file:///tmp/verifysignal-core.tar.gz",
        "sha256": sha256,
        "releaseMetadataBytes": metadata_b64,
        "signature": signature,
    }


def test_normalize_platform_supports_documented_platforms() -> None:
    assert normalize_platform(system="Darwin", machine="arm64") == "darwin-arm64"
    assert normalize_platform(system="Darwin", machine="x86_64") == "darwin-x64"
    assert normalize_platform(system="Linux", machine="x86_64") == "linux-x64"
    assert normalize_platform(system="Windows", machine="AMD64") == "win32-x64"
    # Keep the negative case honest now that a win32 label exists: Windows on ARM is genuinely not
    # built, and "win32" could otherwise be read as covering every Windows machine.
    assert normalize_platform(system="Windows", machine="ARM64") is None


def test_manifest_selection_requires_a_real_signature_and_bytes() -> None:
    entry = signed_manifest_entry(platform="darwin-arm64", sha256="a" * 64)
    selected = select_manifest_entry(
        manifest_entries({"entries": [entry]}),
        platform="darwin-arm64",
        contract_version="verifysignal-public-cli-json/v1",
    )
    assert selected["coreVersion"] == "0.5.1"
    assert signature_contract_available(selected)

    # A self-reported stub (no detached signature / no signed bytes) is no longer selectable.
    stub = {**entry, "signature": {"algorithm": "test", "keyId": "test", "value": "valid"}}
    stub.pop("releaseMetadataBytes")
    assert not signature_contract_available(stub)


def test_verify_release_authenticity_accepts_valid_and_fails_closed() -> None:
    assert verify_release_authenticity(signed_manifest_entry(platform="darwin-arm64", sha256="a" * 64)) is None

    untrusted = signed_manifest_entry(platform="darwin-arm64", sha256="a" * 64)
    untrusted["signature"]["keyId"] = "unknown-release-key"
    blocker = verify_release_authenticity(untrusted)
    assert blocker is not None and blocker.code == "artifact.authenticity-failed"

    tampered = signed_manifest_entry(platform="darwin-arm64", sha256="a" * 64)
    tampered["releaseMetadataBytes"] = base64.b64encode(b'{"tampered":true}').decode("ascii")
    blocker = verify_release_authenticity(tampered)
    assert blocker is not None and blocker.code == "artifact.authenticity-failed"

    # Archive sha256 does not match the SIGNED sha256 (bytes still verify, cross-check fails).
    mismatch = signed_manifest_entry(platform="darwin-arm64", sha256="b" * 64, signed_sha256="a" * 64)
    blocker = verify_release_authenticity(mismatch)
    assert blocker is not None and blocker.code == "artifact.authenticity-failed"

    no_bytes = signed_manifest_entry(platform="darwin-arm64", sha256="a" * 64)
    no_bytes["releaseMetadataBytes"] = None
    blocker = verify_release_authenticity(no_bytes)
    assert blocker is not None and blocker.code == "artifact.authenticity-failed"


def test_verify_release_authenticity_requires_a_signed_public_contract_version() -> None:
    # Signed metadata that OMITS publicContractVersion must fail closed rather than silently
    # skipping the contract-version binding (L1 hardening).
    metadata = {
        "schema": "verifysignal.runtime-release/v1",
        "channel": "stable",
        "issuer": "https://verifysignal.io",
        "packages": [{"platform": "darwin-arm64", "sha256": "a" * 64}],
    }
    blocker = verify_release_authenticity(_entry_with_signed_metadata(metadata, sha256="a" * 64))
    assert blocker is not None and blocker.code == "artifact.authenticity-failed"


def test_verify_release_authenticity_binds_core_version() -> None:
    # A validly-signed release re-pointed at a coreVersion the signature does not cover must fail
    # closed. coreVersion drives the cache path and the persisted install record, so a forged
    # coreVersion on an otherwise-authentic entry cannot be trusted.
    mismatch = signed_manifest_entry(
        platform="darwin-arm64", sha256="a" * 64, core_version="9.9.9", signed_core_version="0.5.1"
    )
    blocker = verify_release_authenticity(mismatch)
    assert blocker is not None and blocker.code == "artifact.authenticity-failed"

    # Signed metadata that OMITS coreVersion must also fail closed (no silent skip), matching the
    # sha256 and publicContractVersion bindings.
    metadata = {
        "schema": "verifysignal.runtime-release/v1",
        "publicContractVersion": "verifysignal-public-cli-json/v1",
        "channel": "stable",
        "issuer": "https://verifysignal.io",
        "packages": [{"platform": "darwin-arm64", "sha256": "a" * 64}],
    }
    blocker = verify_release_authenticity(_entry_with_signed_metadata(metadata, sha256="a" * 64))
    assert blocker is not None and blocker.code == "artifact.authenticity-failed"


def test_verify_release_authenticity_rejects_degenerate_sha_on_both_sides() -> None:
    # A signed package whose sha256 is empty / whitespace / non-hex must not authenticate an
    # entry with the same degenerate value via a bare equality ("" == "", "   " == "   ",
    # None -> "none" == "none"). Only a real 64-hex match may pass (L2 hardening).
    for degenerate in ("", "   ", None, "not-a-hash"):
        metadata = {
            "schema": "verifysignal.runtime-release/v1",
            "publicContractVersion": "verifysignal-public-cli-json/v1",
            "channel": "stable",
            "issuer": "https://verifysignal.io",
            "packages": [{"platform": "darwin-arm64", "sha256": degenerate}],
        }
        entry = _entry_with_signed_metadata(metadata, sha256="")
        entry["sha256"] = degenerate  # type: ignore[assignment]
        blocker = verify_release_authenticity(entry)
        assert blocker is not None and blocker.code == "artifact.authenticity-failed", degenerate


def test_verify_sha256_detects_mismatch(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact.tar.gz"
    artifact.write_text("runtime", encoding="utf-8")
    assert verify_sha256(artifact, hashlib.sha256(b"runtime").hexdigest())
    assert not verify_sha256(artifact, "0" * 64)


def test_install_fails_closed_when_the_served_object_drifts_from_the_signed_sha(tmp_path: Path) -> None:
    # Characterizes the DURABLE guarantee behind runtime-storage.ts's corrected comment. The BE upload
    # read-back is only a POINT-IN-TIME check: a later `upsert` overwrite, or an import that writes the
    # runtime_releases row without reading the object back, can leave the advertised — and SIGNED —
    # sha256 describing bytes the bucket no longer holds. install_from_manifest pins the DOWNLOADED
    # bytes to that signed sha and fails closed at integrity, BEFORE extraction, rather than serving
    # bad bytes. The write-primitive regression in test_signed_field_binding.py passes through this
    # path but asserts a different dimension, so nothing pinned `artifact.integrity-failed` on a
    # genuinely-signed-but-drifted object until now.
    good_bytes = b"the-genuine-runtime-archive"
    signed_sha = hashlib.sha256(good_bytes).hexdigest()

    served = tmp_path / "served.tar.gz"
    served.write_bytes(b"an-overwritten-object")  # the bucket now holds bytes the signed sha never described
    assert hashlib.sha256(served.read_bytes()).hexdigest() != signed_sha

    entry = signed_manifest_entry(platform="darwin-arm64", sha256=signed_sha, url=served.as_uri())
    # The release IS genuinely signed against the good sha — authenticity would pass if it were reached.
    assert verify_release_authenticity(entry) is None

    runtime, blocker = install_from_manifest(entry)

    assert runtime is None
    assert blocker is not None and blocker.code == "artifact.integrity-failed"


def test_force_rmtree_clears_the_read_only_files_windows_leaves_behind(tmp_path: Path) -> None:
    # shutil.rmtree fails on a read-only FILE on Windows, because os.remove refuses it -- unlike
    # POSIX, where the containing DIRECTORY's write bit decides. An install that cannot clean up its
    # own staging directory leaves the cache growing silently.
    cache = tmp_path / "cache"
    tree = cache / ".runtime.old-abc"
    (tree / "bin").mkdir(parents=True)
    (tree / "bin" / "verifysignal-core").write_text("#!/bin/sh\n", encoding="utf-8")
    try:
        (tree / "bin" / "verifysignal-core").chmod(0o444)
        (tree / "bin").chmod(0o555)
        tree.chmod(0o555)

        _force_rmtree(tree)

        assert not tree.exists()
        # Never raises: this only ever cleans up, so a stubborn leftover must not fail the install.
        _force_rmtree(cache / "does-not-exist")
    finally:
        # Restore anything that survived, so a failure here cannot leave an undeletable tmpdir.
        for node in sorted(cache.rglob("*"), reverse=True) + [cache]:
            if node.exists():
                node.chmod(0o755)


def test_stale_swap_directories_are_swept_but_real_caches_are_not(tmp_path: Path) -> None:
    # An install interrupted between rename and promote leaves a staging or retired directory. They
    # are swept on the next install; anything else in the cache is untouched.
    cache = tmp_path / "0.6.1"
    for name in (".darwin-arm64.new-abc", ".darwin-arm64.old-def"):
        (cache / name).mkdir(parents=True)
    real = cache / "darwin-arm64"
    real.mkdir(parents=True)
    (real / "manifest.json").write_text("{}", encoding="utf-8")
    unrelated = cache / ".config"
    unrelated.mkdir()

    _sweep_stale_swaps(cache)

    assert sorted(entry.name for entry in cache.iterdir()) == [".config", "darwin-arm64"]
    assert (real / "manifest.json").is_file()
