from __future__ import annotations

from pathlib import Path

from verifysignal_spec.runtime.cache import (
    cache_root,
    load_cache_entry,
    save_cache_entry,
)
from verifysignal_spec.runtime.distribution import (
    load_verification_keys,
    save_verification_keys,
    verification_keys_path,
)
from verifysignal_spec.runtime.entitlement import (
    DEFAULT_API_BASE_URL,
    load_receipt,
    receipt_path,
    save_receipt,
)
from verifysignal_spec.runtime.models import RuntimeEntitlementReceipt


LOCAL_API = "http://127.0.0.1:3210/api"
SECOND_LOCAL_API = "http://127.0.0.1:3211/api"


def _isolate_default_cache(monkeypatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("VERIFYSIGNAL_RUNTIME_CACHE_DIR", raising=False)
    monkeypatch.delenv("VERIFYSIGNAL_API_BASE_URL", raising=False)
    return tmp_path / ".cache" / "verifysignal" / "core"


def test_default_production_cache_path_is_unchanged(monkeypatch, tmp_path) -> None:
    expected = _isolate_default_cache(monkeypatch, tmp_path)

    assert cache_root() == expected
    assert cache_root(DEFAULT_API_BASE_URL) == expected
    assert cache_root(f"{DEFAULT_API_BASE_URL}/") == expected
    assert receipt_path(DEFAULT_API_BASE_URL) == expected / "entitlement" / "receipt.json"


def test_non_default_api_urls_have_stable_distinct_namespaces(
    monkeypatch, tmp_path
) -> None:
    default_root = _isolate_default_cache(monkeypatch, tmp_path)

    local_root = cache_root(LOCAL_API)
    equivalent_local_root = cache_root("http://127.0.0.1:3210/api/")
    second_root = cache_root(SECOND_LOCAL_API)

    assert local_root.parent == default_root / "endpoints"
    assert local_root == equivalent_local_root
    assert local_root != second_root
    assert local_root.name


def test_explicit_runtime_cache_override_keeps_existing_semantics(
    monkeypatch, tmp_path
) -> None:
    override = tmp_path / "explicit-cache"
    monkeypatch.setenv("VERIFYSIGNAL_RUNTIME_CACHE_DIR", str(override))

    assert cache_root() == override
    assert cache_root(LOCAL_API) == override
    assert receipt_path(LOCAL_API) == override / "entitlement" / "receipt.json"


def test_api_environment_selects_namespace_when_no_url_is_passed(
    monkeypatch, tmp_path
) -> None:
    _isolate_default_cache(monkeypatch, tmp_path)
    monkeypatch.setenv("VERIFYSIGNAL_API_BASE_URL", LOCAL_API)

    assert cache_root() == cache_root(LOCAL_API)
    assert receipt_path() == receipt_path(LOCAL_API)


def test_production_receipt_cannot_satisfy_local_entitlement(
    monkeypatch, tmp_path
) -> None:
    _isolate_default_cache(monkeypatch, tmp_path)
    production = RuntimeEntitlementReceipt(
        receiptId="receipt-production",
        status="valid",
    )

    save_receipt(production, api_base_url=DEFAULT_API_BASE_URL)

    assert load_receipt(api_base_url=DEFAULT_API_BASE_URL) is not None
    assert load_receipt(api_base_url=LOCAL_API) is None
    assert receipt_path(DEFAULT_API_BASE_URL) != receipt_path(LOCAL_API)


def test_verification_keys_are_isolated_by_api_endpoint(
    monkeypatch, tmp_path
) -> None:
    _isolate_default_cache(monkeypatch, tmp_path)
    local_keys = {
        "schema": "verifysignal.entitlement-keys/v1",
        "schemaVersion": 1,
        "keys": [{"keyId": "local-key", "status": "active"}],
    }

    save_verification_keys(local_keys, source_api_base_url=LOCAL_API)

    assert load_verification_keys(api_base_url=LOCAL_API) is not None
    assert load_verification_keys(api_base_url=DEFAULT_API_BASE_URL) is None
    assert verification_keys_path(LOCAL_API) != verification_keys_path(
        DEFAULT_API_BASE_URL
    )


def test_managed_runtime_cache_is_isolated_by_api_endpoint(
    monkeypatch, tmp_path
) -> None:
    _isolate_default_cache(monkeypatch, tmp_path)
    runtime = tmp_path / "verifysignal-core"
    runtime.write_text("#!/bin/sh\n", encoding="utf-8")

    save_cache_entry(
        core_version="0.6.0",
        platform="darwin-arm64",
        runtime_command=str(runtime),
        api_base_url=LOCAL_API,
    )

    assert (
        load_cache_entry(platform="darwin-arm64", api_base_url=LOCAL_API)
        is not None
    )
    assert (
        load_cache_entry(
            platform="darwin-arm64",
            api_base_url=DEFAULT_API_BASE_URL,
        )
        is None
    )
