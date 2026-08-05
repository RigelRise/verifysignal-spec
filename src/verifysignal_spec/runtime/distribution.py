from __future__ import annotations

import hashlib
import json
import os
import re
import platform as host_platform
import shutil
import socket
import stat
import sys
import tarfile
import tempfile
import urllib.parse
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from verifysignal_spec.core.contracts import PUBLIC_CONTRACT_VERSION

import base64

from .cache import cache_root, platform_cache_dir, save_cache_entry
from .models import EntitlementClientConfig, RuntimeEntitlementReceipt, RuntimeEntitlementStatus, RuntimeSetupBlocker, RuntimeVerificationKeyStatus
from .release_signature import verify_release_signature
from verifysignal_spec.security.file_protection import harden_owner_only


@dataclass(slots=True)
class RuntimeAuthorizationResponse:
    data: dict[str, Any]
    blocker: RuntimeSetupBlocker | None = None


def normalize_platform(system: str | None = None, machine: str | None = None) -> str | None:
    system = (system or host_platform.system()).lower()
    machine = (machine or host_platform.machine()).lower()
    if system == "darwin" and machine in {"arm64", "aarch64"}:
        return "darwin-arm64"
    if system == "darwin" and machine in {"x86_64", "amd64"}:
        return "darwin-x64"
    if system == "linux" and machine in {"x86_64", "amd64"}:
        return "linux-x64"
    if system == "windows" and machine in {"amd64", "x86_64"}:
        return "win32-x64"
    return None


def load_manifest() -> tuple[dict[str, Any] | None, RuntimeSetupBlocker | None]:
    raw = os.environ.get("VERIFYSIGNAL_RUNTIME_MANIFEST_JSON")
    if raw:
        try:
            return json.loads(raw), None
        except json.JSONDecodeError:
            return None, RuntimeSetupBlocker(code="manifest.invalid", message="Managed runtime manifest JSON is invalid.")
    path = os.environ.get("VERIFYSIGNAL_RUNTIME_MANIFEST_PATH")
    if path:
        try:
            return json.loads(Path(path).expanduser().read_text(encoding="utf-8")), None
        except FileNotFoundError:
            return None, RuntimeSetupBlocker(code="manifest.unavailable", message="Managed runtime manifest path was not found.")
        except json.JSONDecodeError:
            return None, RuntimeSetupBlocker(code="manifest.invalid", message="Managed runtime manifest file is invalid.")
    return None, RuntimeSetupBlocker(
        code="distribution.unavailable",
        message="Official managed runtime distribution is not configured for this Spec build. Use an override or configure the distribution manifest.",
        recoveryCommand="verifysignal core setup --core-cmd <path>",
    )


def manifest_entries(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(manifest.get("entries"), list):
        return [item for item in manifest["entries"] if isinstance(item, dict)]
    if all(key in manifest for key in ["coreVersion", "contractVersion", "platform", "url", "sha256"]):
        return [manifest]
    return []


def select_manifest_entry(entries: list[dict[str, Any]], *, platform: str, contract_version: str = PUBLIC_CONTRACT_VERSION) -> dict[str, Any]:
    for entry in entries:
        if entry.get("platform") == platform and entry.get("contractVersion") == contract_version and _entry_has_required_fields(entry):
            return entry
    raise ValueError("No compatible managed runtime manifest entry was found.")


def _entry_has_required_fields(entry: dict[str, Any]) -> bool:
    return all(entry.get(key) for key in ["coreVersion", "contractVersion", "platform", "url", "sha256"]) and signature_contract_available(entry)


def signature_contract_available(entry: dict[str, Any]) -> bool:
    # A verifiable entry carries the detached Ed25519 signature record AND the exact signed
    # metadata bytes the signature covers. (The old contract only required self-reported
    # `value`/`algorithm` strings, which proved nothing.)
    signature = entry.get("signature")
    return (
        isinstance(signature, dict)
        and signature.get("algorithm") == "ed25519"
        and bool(signature.get("keyId"))
        and bool(signature.get("signature"))
        and bool(entry.get("releaseMetadataBytes"))
    )


def verify_sha256(path: Path, expected: str) -> bool:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return digest.lower() == expected.lower()


def verify_release_authenticity(entry: dict[str, Any]) -> RuntimeSetupBlocker | None:
    """Cryptographically verify a runtime release: the detached Ed25519 signature over the
    exact signed metadata bytes, then that the signed metadata binds this platform's archive
    sha256 and public-contract version. Returns a blocker on any failure (fails closed), or
    None when the release is authentic.
    """
    metadata_b64 = entry.get("releaseMetadataBytes")
    signature = entry.get("signature")
    if not isinstance(metadata_b64, str) or not metadata_b64 or not isinstance(signature, dict):
        return RuntimeSetupBlocker(code="artifact.authenticity-failed", message="Managed runtime release is missing signed metadata bytes.")
    try:
        metadata_bytes = base64.b64decode(metadata_b64, validate=True)
    except (ValueError, TypeError):
        return RuntimeSetupBlocker(code="artifact.authenticity-failed", message="Managed runtime signed metadata bytes were malformed.")

    ok, _key_id = verify_release_signature(metadata_bytes, signature)
    if not ok:
        return RuntimeSetupBlocker(code="artifact.authenticity-failed", message="Managed runtime release signature could not be verified against a trusted release key.")

    try:
        metadata = json.loads(metadata_bytes.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return RuntimeSetupBlocker(code="artifact.authenticity-failed", message="Signed runtime release metadata was malformed.")

    # The signed payload MUST declare that it IS a release. A signature proves WHO signed, never WHAT
    # KIND of document was signed, so without this any other document a trusted key ever signed could
    # be replayed here as a release. The `schema` check in release_signature.py is NOT this check: it
    # inspects the detached signature RECORD, which sits outside the signed bytes and is freely
    # attacker-mutable. Absent schema fails closed, like every other binding below.
    if metadata.get("schema") != "verifysignal.runtime-release/v1":
        return RuntimeSetupBlocker(
            code="artifact.authenticity-failed",
            message="Signed runtime release metadata is not a verifysignal.runtime-release/v1 document.",
        )

    packages = metadata.get("packages") if isinstance(metadata.get("packages"), list) else []
    signed_entry = next(
        (item for item in packages if isinstance(item, dict) and item.get("platform") == entry.get("platform")),
        None,
    )
    # Both hashes must be well-formed sha256 hex AND equal. Requiring the 64-hex shape rejects
    # the degenerate matches that a bare equality would accept — "" == "", "   " == "   ", or
    # None/None stringifying to "none" == "none" — none of which prove a real archive binding.
    signed_sha = str(signed_entry.get("sha256", "")).strip().lower() if signed_entry else ""
    entry_sha = str(entry.get("sha256", "")).strip().lower()
    if (
        signed_entry is None
        or not re.fullmatch(r"[0-9a-f]{64}", signed_sha)
        or not re.fullmatch(r"[0-9a-f]{64}", entry_sha)
        or signed_sha != entry_sha
    ):
        return RuntimeSetupBlocker(code="artifact.authenticity-failed", message="Runtime archive sha256 does not match the signed release metadata.")

    # The signed metadata MUST bind the public-contract version. A release whose signed metadata
    # omits it cannot be accepted (fail closed) — matching the stated "fail closed on any
    # mismatch" contract rather than silently skipping the binding when the field is absent.
    signed_contract = metadata.get("publicContractVersion")
    if not signed_contract or signed_contract != entry.get("contractVersion"):
        return RuntimeSetupBlocker(code="artifact.authenticity-failed", message="Signed runtime release metadata public-contract version did not match.")

    # The signed metadata MUST also bind coreVersion — it drives the cache path and the persisted
    # install record, so a validly-signed blob cannot be re-pointed at a different coreVersion.
    # Absent signed coreVersion fails closed, matching the sha256 and contract-version bindings.
    signed_core_version = metadata.get("coreVersion")
    if not signed_core_version or signed_core_version != entry.get("coreVersion"):
        return RuntimeSetupBlocker(code="artifact.authenticity-failed", message="Signed runtime release metadata coreVersion did not match.")

    # Bind the artifact filename too. Core really does sign packages[].filename (see the cross-repo
    # golden) and the BE already cross-checks it at registration — the Spec was the only consumer
    # taking it on trust from the server. Only checked when the entry claims one: the field is inert
    # now (a fixed scratch name is used), so an entry that omits it has nothing to lie about.
    entry_filename = entry.get("artifactName")
    if entry_filename and str(entry_filename) != str(signed_entry.get("filename") or ""):
        return RuntimeSetupBlocker(
            code="artifact.authenticity-failed",
            message="Runtime archive filename does not match the signed release metadata.",
        )
    return None


def _force_rmtree(path: Path) -> None:
    """Remove ``path``, clearing the read-only attribute Windows sets on some extracted files.

    ``shutil.rmtree`` fails on a read-only file on Windows because ``os.remove`` refuses it, unlike
    POSIX where the DIRECTORY's write bit decides. Never raises: this only ever cleans up.
    """

    def _retry(func: Any, target: str, _exc: Any) -> None:
        try:
            # Both the entry AND its parent. On POSIX, removing a file needs write on the
            # containing DIRECTORY, not on the file; on Windows it is the file's read-only attribute
            # that blocks it. Clearing both covers each host without branching.
            #
            # OR the bits in rather than REPLACING the mode: stat.S_IWRITE is 0o200, so assigning it
            # would strip read and execute and make a directory untraversable -- turning a
            # recoverable failure into a permanent one.
            for node in (Path(target).parent, Path(target)):
                if node.exists():
                    os.chmod(node, os.stat(node).st_mode | stat.S_IRWXU)
            func(target)
        except OSError:
            pass

    if not path.exists():
        return
    # `onexc` is 3.12+; `onerror` is the 3.11 spelling and takes the same three arguments. The
    # package supports >=3.11, so passing `onexc` there would raise TypeError from a cleanup helper.
    hook = "onexc" if sys.version_info >= (3, 12) else "onerror"
    shutil.rmtree(path, **{hook: _retry})


def _sweep_stale_swaps(cache_dir: Path) -> None:
    """Drop staging and retired directories a previous interrupted swap left behind."""

    try:
        entries = list(cache_dir.iterdir())
    except OSError:
        return
    for entry in entries:
        if entry.is_dir() and (".new-" in entry.name or ".old-" in entry.name) and entry.name.startswith("."):
            _force_rmtree(entry)


def _resolve_packaged_executable(package_root: Path) -> Path | None:
    """Resolve the runtime executable inside an extracted package.

    Real Core packages are a ``verifysignal-core/`` directory whose
    ``manifest.json`` declares ``executable`` (``bin/verifysignal-core`` per the
    Core runtime-package contract); legacy flat archives shipped the executable
    as a top-level ``verifysignal-core`` file.
    """
    if package_root.is_file():
        return package_root
    if not package_root.is_dir():
        return None
    executable_rel = "bin/verifysignal-core"
    manifest_path = package_root / "manifest.json"
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            manifest = {}
        declared = manifest.get("executable")
        if isinstance(declared, str) and declared:
            executable_rel = declared
    candidate = (package_root / executable_rel).resolve()
    if package_root.resolve() not in candidate.parents:
        return None
    if candidate.is_file():
        return candidate
    # A Spec newer than the installed package: the manifest may declare a launcher this package
    # predates. Both launchers ship in every Core package, so the sibling with the right suffix for
    # this host is the correct entry point.
    for suffix in ((".cmd", ".exe") if os.name == "nt" else ("",)):
        sibling = candidate.with_name(candidate.stem + suffix)
        if sibling.is_file() and package_root.resolve() in sibling.parents:
            return sibling
    return None


def install_from_manifest(
    entry: dict[str, Any],
    *,
    entitlement_receipt_id: str | None = None,
    api_base_url: str | None = None,
) -> tuple[str | None, RuntimeSetupBlocker | None]:
    temp_dir = Path(tempfile.mkdtemp(prefix="verifysignal-runtime-"))
    # A FIXED scratch name. `entry["artifactName"]` comes from the distribution server's JSON — the
    # party this whole signature architecture exists because it does not trust — and it used to be
    # joined here directly. `Path("/tmp/x") / "/Users/me/.zshrc"` yields `/Users/me/.zshrc`: an
    # absolute name silently REPLACES the scratch dir, and `..` escapes it. Worse, the download below
    # writes BEFORE sha256 and signature verification, so rejecting the release does not un-write the
    # attacker's bytes, and the `finally` rmtree cannot reach a file that escaped temp_dir.
    # The field only ever named a throwaway file (extraction reads the archive, not its name), so the
    # fix is to stop using it: untrusted input never reaches a path join. It is ALSO bound to the
    # signed metadata in verify_release_authenticity — two independent defenses on purpose.
    artifact_path = temp_dir / "verifysignal-core.tar.gz"
    destination: Path | None = None
    try:
        _download_artifact(str(entry["url"]), artifact_path)
        if not verify_sha256(artifact_path, str(entry["sha256"])):
            return None, RuntimeSetupBlocker(code="artifact.integrity-failed", message="Managed runtime artifact checksum did not match.")
        authenticity_blocker = verify_release_authenticity(entry)
        if authenticity_blocker is not None:
            return None, authenticity_blocker
        core_version = str(entry["coreVersion"])
        platform = str(entry["platform"])
        destination = platform_cache_dir(
            core_version,
            platform,
            api_base_url,
        )
        # Stage, validate, THEN swap. Deleting the destination first meant a failed extraction left
        # no runtime at all where a working one had been. On Windows it is worse than untidy: a
        # directory holding a file some process has open cannot be deleted, so `core update` while a
        # Core was alive failed outright -- but the destination can usually still be RENAMED away.
        _sweep_stale_swaps(destination.parent)
        staging = destination.parent / f".{destination.name}.new-{uuid4().hex}"
        _force_rmtree(staging)
        staging.mkdir(parents=True, exist_ok=True)
        with tarfile.open(artifact_path, "r:gz") as archive:
            archive.extractall(staging, filter="data")
        runtime = _resolve_packaged_executable(staging / "verifysignal-core")
        if runtime is None:
            _force_rmtree(staging)
            return None, RuntimeSetupBlocker(code="manifest.invalid", message="Managed runtime artifact does not contain a verifysignal-core executable.")
        # The x bit is meaningless on Windows, where executability comes from the extension.
        if os.name != "nt":
            runtime.chmod(runtime.stat().st_mode | 0o100)
        retired = destination.parent / f".{destination.name}.old-{uuid4().hex}"
        if destination.exists():
            destination.replace(retired)
        destination.parent.mkdir(parents=True, exist_ok=True)
        staging.replace(destination)
        _force_rmtree(retired)
        runtime = destination / runtime.relative_to(staging)
        save_cache_entry(
            core_version=core_version,
            platform=platform,
            runtime_command=str(runtime),
            contract_version=str(entry.get("contractVersion", PUBLIC_CONTRACT_VERSION)),
            sha256=str(entry.get("sha256", "")),
            entitlement_receipt_id=entitlement_receipt_id,
            api_base_url=api_base_url,
        )
        return str(runtime), None
    except PermissionError:
        if destination:
            shutil.rmtree(destination, ignore_errors=True)
        return None, RuntimeSetupBlocker(code="cache.permission-denied", message="Managed runtime cache is not writable.")
    except Exception as exc:
        if destination:
            shutil.rmtree(destination, ignore_errors=True)
        return None, RuntimeSetupBlocker(code="manifest.unavailable", message=str(exc))
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def install_from_authorization(
    grant: dict[str, Any],
    *,
    entitlement_receipt_id: str | None = None,
    api_base_url: str | None = None,
) -> tuple[str | None, RuntimeSetupBlocker | None]:
    package = grant.get("package") if isinstance(grant.get("package"), dict) else {}
    signature = grant.get("releaseSignature") if isinstance(grant.get("releaseSignature"), dict) else {}
    entry = {
        "coreVersion": grant.get("coreVersion"),
        "contractVersion": grant.get("contractVersion", PUBLIC_CONTRACT_VERSION),
        "platform": grant.get("platform"),
        "artifactName": package.get("filename"),
        "url": package.get("downloadUrl"),
        "sha256": package.get("sha256"),
        # The real detached signature + the exact signed metadata bytes the backend served,
        # so authenticity is verified cryptographically rather than synthesized.
        "signature": signature,
        "releaseMetadataBytes": grant.get("releaseMetadataBytes"),
    }
    if _is_expired(package.get("expiresAt")):
        return None, RuntimeSetupBlocker(code="distribution.url-expired", message="Authorized runtime download URL expired before use.")
    if not _entry_has_required_fields(entry):
        return None, RuntimeSetupBlocker(code="manifest.invalid", message="Runtime download authorization response is incomplete.")
    return install_from_manifest(
        entry,
        entitlement_receipt_id=entitlement_receipt_id,
        api_base_url=api_base_url,
    )


class RuntimeDistributionClient:
    def __init__(self, config: EntitlementClientConfig) -> None:
        self.config = config

    def authorize_runtime_download(self, core_version: str, platform: str, receipt: RuntimeEntitlementReceipt) -> RuntimeAuthorizationResponse:
        if not receipt.receiptPayload:
            return RuntimeAuthorizationResponse(data={}, blocker=RuntimeSetupBlocker(code="entitlement.malformed", message="Entitlement receipt payload is unavailable."))
        path = f"/runtimes/{urllib.parse.quote(core_version)}?platform={urllib.parse.quote(platform)}"
        status, data, transport_blocker = self._json_request(
            path,
            headers={"Authorization": f"Bearer {receipt.receiptPayload}"},
        )
        if transport_blocker:
            return RuntimeAuthorizationResponse(data={}, blocker=transport_blocker)
        if status != 200:
            return RuntimeAuthorizationResponse(data={}, blocker=_download_http_blocker(status, data))
        blocker = validate_runtime_authorization_response(data, expected_platform=platform)
        return RuntimeAuthorizationResponse(data=data, blocker=blocker)

    def resolve_latest_core_version(self, platform: str, receipt: RuntimeEntitlementReceipt) -> tuple[str | None, RuntimeSetupBlocker | None]:
        """Ask the backend which Core version is current for this platform.

        Every other lookup here is exact-match on a version the client must already know, and the only
        thing that ever wrote that version locally read it off an installed Core — so a first-time
        user was in a closed loop: the managed download needs the version, and the version came from
        the runtime the download exists to fetch.

        Returns ``(coreVersion, None)`` or ``(None, blocker)``. Fails closed: an unreachable or
        unparseable answer yields a blocker rather than a guess, because guessing a version produces
        an opaque 404 from the exact-match download API.
        """
        if not receipt.receiptPayload:
            return None, RuntimeSetupBlocker(code="entitlement.malformed", message="Entitlement receipt payload is unavailable.")
        path = f"/runtimes/latest?platform={urllib.parse.quote(platform)}"
        status, data, transport_blocker = self._json_request(
            path,
            headers={"Authorization": f"Bearer {receipt.receiptPayload}"},
        )
        if transport_blocker:
            return None, transport_blocker
        if status != 200:
            return None, _download_http_blocker(status, data)
        if data.get("schema") != "verifysignal.runtime-latest/v1" or data.get("schemaVersion") != 1:
            return None, RuntimeSetupBlocker(code="manifest.invalid", message="Runtime latest-version response did not match the public contract.")
        core_version = data.get("coreVersion")
        if not isinstance(core_version, str) or not core_version.strip():
            return None, RuntimeSetupBlocker(code="manifest.invalid", message="Runtime latest-version response did not carry a coreVersion.")
        return core_version.strip(), None

    def fetch_verification_keys(self, *, issuer: str | None = None) -> RuntimeAuthorizationResponse:
        status, data, transport_blocker = self._json_request("/entitlements/keys")
        if transport_blocker:
            return RuntimeAuthorizationResponse(data={}, blocker=_verification_key_blocker("entitlement.keys-unavailable"))
        if status != 200:
            return RuntimeAuthorizationResponse(data={}, blocker=_verification_key_blocker("entitlement.keys-unavailable"))
        if data.get("schema") != "verifysignal.entitlement-keys/v1" or data.get("schemaVersion") != 1 or not isinstance(data.get("keys"), list):
            return RuntimeAuthorizationResponse(data={}, blocker=_verification_key_blocker("entitlement.keys-incompatible"))
        save_verification_keys(
            data,
            source_api_base_url=self.config.apiBaseUrl,
            issuer=issuer,
        )
        return RuntimeAuthorizationResponse(
            data=load_verification_keys(
                api_base_url=self.config.apiBaseUrl,
            )
            or data
        )

    def _json_request(self, path: str, *, headers: dict[str, str] | None = None) -> tuple[int, dict[str, Any], RuntimeSetupBlocker | None]:
        request = urllib.request.Request(
            f"{self.config.apiBaseUrl}{path}",
            method="GET",
            headers={"Accept": "application/json", "Cache-Control": "no-store", **(headers or {})},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.config.timeoutSeconds) as response:  # nosec B310 - official/explicit API URL
                return response.status, _parse_json_response(response.read()), None
        except urllib.error.HTTPError as exc:
            return exc.code, _parse_json_response(exc.read()), None
        except (urllib.error.URLError, TimeoutError, socket.timeout, OSError):
            return 0, {}, RuntimeSetupBlocker(code="api.unavailable", message="VerifySignal runtime distribution API is unavailable.")


def validate_runtime_authorization_response(data: dict[str, Any], *, expected_platform: str | None = None) -> RuntimeSetupBlocker | None:
    package = data.get("package") if isinstance(data.get("package"), dict) else {}
    if data.get("schema") != "verifysignal.runtime-download/v1" or data.get("schemaVersion") != 1:
        return RuntimeSetupBlocker(code="manifest.invalid", message="Runtime download authorization response did not match the public contract.")
    if expected_platform and data.get("platform") != expected_platform:
        return RuntimeSetupBlocker(code="platform.unsupported", message="Runtime download authorization returned the wrong platform.")
    required_package = ["filename", "byteSize", "sha256", "downloadUrl", "expiresAt"]
    if not all(package.get(key) for key in required_package):
        return RuntimeSetupBlocker(code="manifest.invalid", message="Runtime download authorization package metadata is incomplete.")
    if _is_expired(package.get("expiresAt")):
        return RuntimeSetupBlocker(code="distribution.url-expired", message="Authorized runtime download URL has expired.")
    return None


def verification_keys_path(api_base_url: str | None = None) -> Path:
    return cache_root(api_base_url) / "entitlement" / "keys.json"


def save_verification_keys(data: dict[str, Any], *, source_api_base_url: str | None = None, issuer: str | None = None) -> Path:
    path = verification_keys_path(source_api_base_url)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(data)
    if source_api_base_url:
        payload["sourceApiBaseUrl"] = source_api_base_url.rstrip("/")
    if payload.get("issuer") is None and issuer:
        payload["issuer"] = issuer
    payload.setdefault("retrievedAt", datetime.now(UTC).isoformat().replace("+00:00", "Z"))
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    try:
        harden_owner_only(path)
    except OSError:
        pass
    return path


def load_verification_keys(
    api_base_url: str | None = None,
) -> dict[str, Any] | None:
    path = verification_keys_path(api_base_url)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def prepare_verification_keys(
    config: EntitlementClientConfig,
    entitlement: RuntimeEntitlementStatus,
) -> tuple[RuntimeVerificationKeyStatus, RuntimeSetupBlocker | None]:
    if entitlement.status == "not-required":
        return RuntimeVerificationKeyStatus(status="not-required", source="not-required", message="No entitlement receipt is required."), None
    if entitlement.status != "valid":
        return RuntimeVerificationKeyStatus(status="not-checked", source="none", message="Entitlement receipt is not valid yet."), None
    if not entitlement.keyId:
        blocker = _verification_key_blocker("entitlement.keys-incompatible", "Entitlement receipt does not identify a signing key.")
        return _blocked_verification_keys(blocker, source="none", entitlement=entitlement, config=config), blocker

    manual = os.environ.get("VERIFYSIGNAL_ENTITLEMENT_PUBLIC_KEYS_JSON")
    if manual:
        manual_data, blocker = _parse_manual_public_keys(manual)
        if blocker:
            return _blocked_verification_keys(blocker, source="manual-override", entitlement=entitlement, config=config), blocker
        status = _matching_key_status(manual_data, source="manual-override", entitlement=entitlement, config=config, require_binding=False)
        if status.status == "ready":
            return status, None
        blocker = _verification_key_blocker("entitlement.key-unknown")
        return _blocked_verification_keys(blocker, source="manual-override", entitlement=entitlement, config=config), blocker

    cached = load_verification_keys(api_base_url=config.apiBaseUrl)
    cached_status = _matching_key_status(cached, source="cache", entitlement=entitlement, config=config, require_binding=True)
    if cached_status.status == "ready":
        return cached_status, None

    fetched = RuntimeDistributionClient(config).fetch_verification_keys(issuer=entitlement.issuer)
    if fetched.blocker:
        return _blocked_verification_keys(fetched.blocker, source="none", entitlement=entitlement, config=config), fetched.blocker
    fetched_status = _matching_key_status(fetched.data, source="fetched", entitlement=entitlement, config=config, require_binding=True)
    if fetched_status.status == "ready":
        return fetched_status, None
    blocker = _verification_key_blocker("entitlement.key-unknown")
    return _blocked_verification_keys(blocker, source="fetched", entitlement=entitlement, config=config), blocker


def _parse_manual_public_keys(raw: str) -> tuple[dict[str, Any], RuntimeSetupBlocker | None]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}, _verification_key_blocker("entitlement.keys-incompatible")
    if isinstance(data, list):
        return {"keys": data}, None
    if isinstance(data, dict) and isinstance(data.get("keys"), list):
        return data, None
    return {}, _verification_key_blocker("entitlement.keys-incompatible")


def _matching_key_status(
    data: dict[str, Any] | None,
    *,
    source: str,
    entitlement: RuntimeEntitlementStatus,
    config: EntitlementClientConfig,
    require_binding: bool,
) -> RuntimeVerificationKeyStatus:
    if not isinstance(data, dict):
        return RuntimeVerificationKeyStatus(status="blocked", source=source, blockerCode="entitlement.keys-unavailable")
    if require_binding and not _key_cache_binding_matches(data, config=config, entitlement=entitlement):
        return RuntimeVerificationKeyStatus(status="blocked", source=source, blockerCode="entitlement.key-unknown")
    keys = data.get("keys")
    if not isinstance(keys, list):
        return RuntimeVerificationKeyStatus(status="blocked", source=source, blockerCode="entitlement.keys-incompatible")
    if not _has_active_key(keys, entitlement.keyId or ""):
        return RuntimeVerificationKeyStatus(status="blocked", source=source, blockerCode="entitlement.key-unknown")
    return RuntimeVerificationKeyStatus(
        status="ready",
        source=source,  # type: ignore[arg-type]
        matchedKeyId=entitlement.keyId,
        sourceApiBaseUrl=data.get("sourceApiBaseUrl") if isinstance(data.get("sourceApiBaseUrl"), str) else (config.apiBaseUrl if source == "fetched" else None),
        issuer=data.get("issuer") if isinstance(data.get("issuer"), str) else entitlement.issuer,
        message="Public verification keys are ready.",
    )


def _key_cache_binding_matches(data: dict[str, Any], *, config: EntitlementClientConfig, entitlement: RuntimeEntitlementStatus) -> bool:
    source_api_base_url = data.get("sourceApiBaseUrl")
    if source_api_base_url != config.apiBaseUrl:
        return False
    issuer = data.get("issuer")
    if issuer and entitlement.issuer and issuer != entitlement.issuer:
        return False
    return True


def _has_active_key(keys: list[Any], key_id: str) -> bool:
    for item in keys:
        if not isinstance(item, dict):
            continue
        if item.get("keyId") != key_id:
            continue
        status = item.get("status")
        if status in {None, "", "active"}:
            return True
    return False


def _blocked_verification_keys(
    blocker: RuntimeSetupBlocker,
    *,
    source: str,
    entitlement: RuntimeEntitlementStatus,
    config: EntitlementClientConfig,
) -> RuntimeVerificationKeyStatus:
    return RuntimeVerificationKeyStatus(
        status="blocked",
        source=source,  # type: ignore[arg-type]
        matchedKeyId=None,
        sourceApiBaseUrl=config.apiBaseUrl,
        issuer=entitlement.issuer,
        message=blocker.message,
        blockerCode=blocker.code,
    )


def _verification_key_blocker(code: str, message: str | None = None) -> RuntimeSetupBlocker:
    messages = {
        "entitlement.key-unknown": "No public verification key matched the entitlement receipt key.",
        "entitlement.keys-unavailable": "VerifySignal entitlement verification keys are unavailable.",
        "entitlement.keys-incompatible": "Entitlement verification key response is incompatible.",
    }
    return RuntimeSetupBlocker(
        code=code,
        message=message or messages.get(code, "VerifySignal entitlement trust material is unavailable."),
        recoveryCommand="Refresh the configured entitlement service, obtain a new receipt, or provide valid public verification keys.",
    )


def _download_artifact(url: str, destination: Path) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme == "file":
        shutil.copyfile(Path(urllib.request.url2pathname(parsed.path)), destination)
        return
    if parsed.scheme in {"http", "https"}:
        with urllib.request.urlopen(url, timeout=30) as response, destination.open("wb") as handle:  # nosec B310 - official manifest controls URL
            shutil.copyfileobj(response, handle)
        return
    source = Path(url).expanduser()
    if source.exists():
        shutil.copyfile(source, destination)
        return
    raise FileNotFoundError("Managed runtime artifact could not be downloaded.")


def _download_http_blocker(status: int, data: dict[str, Any]) -> RuntimeSetupBlocker:
    code = str(data.get("code") or "")
    if status in {500, 503}:
        mapped = code if code in {"distribution.unavailable", "api.unavailable"} else "api.unavailable"
    elif status == 403:
        mapped = code if code in {"distribution.unauthorized", "entitlement.expired", "entitlement.revoked", "entitlement.malformed", "entitlement.rejected"} else "distribution.unauthorized"
    elif status == 404:
        mapped = "distribution.unavailable"
    elif status == 400:
        mapped = "api.incompatible"
    else:
        mapped = code or "distribution.unavailable"
    return RuntimeSetupBlocker(code=mapped, message=_safe_distribution_message(mapped))


def _safe_distribution_message(code: str) -> str:
    messages = {
        "api.unavailable": "VerifySignal runtime distribution API is unavailable.",
        "api.incompatible": "VerifySignal runtime distribution response is incompatible with this CLI.",
        "distribution.unauthorized": "Runtime download is not authorized for this entitlement.",
        "distribution.unavailable": "No compatible VerifySignal runtime download is available.",
        "distribution.url-expired": "The authorized runtime download URL expired.",
        "entitlement.expired": "The entitlement receipt expired.",
        "entitlement.revoked": "The entitlement receipt was revoked.",
        "entitlement.rejected": "The entitlement receipt was rejected.",
        "entitlement.malformed": "The entitlement receipt is malformed.",
    }
    return messages.get(code, "VerifySignal runtime distribution is blocked.")


def _parse_json_response(raw: bytes) -> dict[str, Any]:
    try:
        data = json.loads(raw.decode("utf-8") or "{}")
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _is_expired(value: str | None) -> bool:
    if not value:
        return True
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return True
    return parsed <= datetime.now(UTC)
