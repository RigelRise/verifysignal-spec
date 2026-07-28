from __future__ import annotations

import json
import os
import hashlib
import urllib.parse
from pathlib import Path

from verifysignal_spec.core.contracts import PUBLIC_CONTRACT_VERSION
from verifysignal_spec.workspace.repository import now_iso

from .models import RuntimeCacheEntry

DEFAULT_API_BASE_URL = "https://www.verifysignal.io/api"


def canonical_api_base_url(api_base_url: str) -> str:
    parsed = urllib.parse.urlsplit(api_base_url.strip())
    scheme = parsed.scheme.lower()
    hostname = (parsed.hostname or "").lower()
    port = parsed.port
    if port and not (
        (scheme == "https" and port == 443)
        or (scheme == "http" and port == 80)
    ):
        authority = f"{hostname}:{port}"
    else:
        authority = hostname
    path = "/" + "/".join(part for part in parsed.path.split("/") if part)
    return urllib.parse.urlunsplit((scheme, authority, path, "", ""))


def endpoint_cache_namespace(api_base_url: str) -> str:
    canonical = canonical_api_base_url(api_base_url)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def cache_root(api_base_url: str | None = None) -> Path:
    override = os.environ.get("VERIFYSIGNAL_RUNTIME_CACHE_DIR")
    if override:
        return Path(override).expanduser().resolve()
    root = (Path.home() / ".cache" / "verifysignal" / "core").resolve()
    selected_api_base_url = (
        api_base_url
        or os.environ.get("VERIFYSIGNAL_API_BASE_URL")
        or DEFAULT_API_BASE_URL
    )
    if canonical_api_base_url(selected_api_base_url) == canonical_api_base_url(
        DEFAULT_API_BASE_URL
    ):
        return root
    return root / "endpoints" / endpoint_cache_namespace(selected_api_base_url)


def platform_cache_dir(
    core_version: str,
    platform: str,
    api_base_url: str | None = None,
) -> Path:
    return cache_root(api_base_url) / core_version / platform


def metadata_path(
    core_version: str,
    platform: str,
    api_base_url: str | None = None,
) -> Path:
    return (
        platform_cache_dir(core_version, platform, api_base_url)
        / "metadata.json"
    )


def save_cache_entry(
    *,
    core_version: str,
    platform: str,
    runtime_command: str,
    contract_version: str = PUBLIC_CONTRACT_VERSION,
    sha256: str = "",
    entitlement_receipt_id: str | None = None,
    api_base_url: str | None = None,
) -> RuntimeCacheEntry:
    root = platform_cache_dir(core_version, platform, api_base_url)
    root.mkdir(parents=True, exist_ok=True)
    timestamp = now_iso()
    path = metadata_path(core_version, platform, api_base_url)
    existing = load_cache_entry(
        platform=platform,
        version=core_version,
        api_base_url=api_base_url,
    )
    verified_at = existing.verifiedAt if existing else timestamp
    entry = RuntimeCacheEntry(
        coreVersion=core_version,
        contractVersion=contract_version,
        platform=platform,
        runtimeCommand=runtime_command,
        cachePath=str(root),
        sha256=sha256,
        verifiedAt=verified_at,
        lastUsedAt=timestamp,
        entitlementReceiptId=entitlement_receipt_id,
        metadataPath=path,
    )
    path.write_text(json.dumps(entry.to_dict(), indent=2), encoding="utf-8")
    return entry


def load_cache_entry(
    *,
    platform: str | None = None,
    version: str | None = None,
    api_base_url: str | None = None,
) -> RuntimeCacheEntry | None:
    root = cache_root(api_base_url)
    if not root.exists():
        return None
    candidates: list[Path] = []
    if version and platform:
        candidates = [metadata_path(version, platform, api_base_url)]
    elif platform:
        candidates = sorted(root.glob(f"*/{platform}/metadata.json"), reverse=True)
    else:
        candidates = sorted(root.glob("*/*/metadata.json"), reverse=True)
    for path in candidates:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            entry = RuntimeCacheEntry.from_dict(data, metadata_path=path)
            if entry.verificationStatus == "verified":
                return entry
        except Exception:
            continue
    return None


def mark_cache_used(
    entry: RuntimeCacheEntry,
    *,
    api_base_url: str | None = None,
) -> RuntimeCacheEntry:
    return save_cache_entry(
        core_version=entry.coreVersion,
        platform=entry.platform,
        runtime_command=entry.runtimeCommand,
        contract_version=entry.contractVersion,
        sha256=entry.sha256,
        entitlement_receipt_id=entry.entitlementReceiptId,
        api_base_url=api_base_url,
    )


def quarantine_cache_entry(entry: RuntimeCacheEntry) -> None:
    if not entry.metadataPath:
        return
    path = Path(entry.metadataPath)
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        data["verificationStatus"] = "corrupt"
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
