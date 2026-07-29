from __future__ import annotations

import contextlib
import io
import json
from unittest.mock import patch

import pytest

from helpers import FAKE_CORE
from verifysignal_spec.repos import CORE_EXECUTABLE_NAMES
from verifysignal_spec.runtime.distribution import load_verification_keys, save_verification_keys
from verifysignal_spec.runtime.entitlement import load_receipt, receipt_path
from verifysignal_spec.runtime.resolver import normalize_platform
from verifysignal_spec.runtime.resolver import ensure_core_runtime
from verifysignal_spec.workspace.repository import load_document
from tests.fixtures.managed_runtime import build_managed_runtime_distribution, serve_fake_entitlement_backend, write_fake_core_executable
from tests.fixtures.workflows.main_skill_run_coverage import create_main_skill_coverage_workspace


def test_override_core_is_ready_but_not_managed_entitlement_success(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("VERIFYSIGNAL_RUNTIME_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.delenv("VERIFYSIGNAL_EMAIL_UNLOCK_TOKEN", raising=False)
    monkeypatch.delenv("VERIFYSIGNAL_ENTITLEMENT_RECEIPT", raising=False)
    monkeypatch.delenv("VERIFYSIGNAL_ENTITLEMENT_RECEIPT_PATH", raising=False)
    monkeypatch.delenv("VERIFYSIGNAL_ENTITLEMENT_PUBLIC_KEYS_JSON", raising=False)
    monkeypatch.delenv("FAKE_VERIFYSIGNAL_MODE", raising=False)

    result = ensure_core_runtime(tmp_path, explicit_core_cmd=str(FAKE_CORE))
    payload = result.to_dict()

    assert payload["status"] == "ready"
    assert payload["source"] == "explicit"
    assert payload["entitlement"]["status"] == "not-required"
    assert payload["source"] != "managed-download"


def test_override_core_init_exchanges_token_for_protected_operations(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("VERIFYSIGNAL_RUNTIME_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("FAKE_VERIFYSIGNAL_MODE", "requires-entitlement")
    monkeypatch.delenv("VERIFYSIGNAL_EMAIL_UNLOCK_TOKEN", raising=False)
    monkeypatch.delenv("VERIFYSIGNAL_ENTITLEMENT_RECEIPT", raising=False)
    monkeypatch.delenv("VERIFYSIGNAL_ENTITLEMENT_RECEIPT_PATH", raising=False)

    with serve_fake_entitlement_backend() as (api_base_url, state):
        result = ensure_core_runtime(
            tmp_path,
            explicit_core_cmd=str(FAKE_CORE),
            api_base_url=api_base_url,
            token="vs_valid",
            integration="claude",
            context="init",
        )

    payload = result.to_dict()
    assert payload["status"] == "ready"
    assert payload["source"] == "explicit"
    assert payload["entitlement"]["status"] == "valid"
    assert payload["verificationKeys"]["status"] == "ready"
    assert payload["verificationKeys"]["source"] == "fetched"
    assert payload["verificationKeys"]["matchedKeyId"] == "ps-entitlement-2026-06"
    assert load_receipt() is not None
    assert any(request["path"] == "/entitlements/exchange" for request in state.requests)
    assert any(request["path"] == "/entitlements/keys" for request in state.requests)
    cached = load_verification_keys()
    assert cached is not None
    assert cached["sourceApiBaseUrl"] == api_base_url
    assert cached["issuer"] == "https://verifysignal.io"
    assert cached["retrievedAt"]
    assert cached["keys"][0]["keyId"] == "ps-entitlement-2026-06"


def test_init_cli_with_override_core_exchanges_interactive_token(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("VERIFYSIGNAL_RUNTIME_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("FAKE_VERIFYSIGNAL_MODE", "requires-entitlement")
    monkeypatch.delenv("VERIFYSIGNAL_EMAIL", raising=False)
    monkeypatch.delenv("VERIFYSIGNAL_EMAIL_UNLOCK_TOKEN", raising=False)
    monkeypatch.delenv("VERIFYSIGNAL_ENTITLEMENT_RECEIPT", raising=False)
    monkeypatch.delenv("VERIFYSIGNAL_ENTITLEMENT_RECEIPT_PATH", raising=False)

    with serve_fake_entitlement_backend() as (api_base_url, state):
        code, out, err = _cli(
            [
                "init",
                str(tmp_path),
                "--integration",
                "claude",
                "--core-cmd",
                str(FAKE_CORE),
                "--api-base-url",
                api_base_url,
                "--json",
            ],
            stdin="qa@example.com\nps_valid\n",
        )

    assert code == 0, err
    payload = json.loads(out)
    assert payload["runtime"]["source"] == "explicit"
    assert payload["runtime"]["entitlement"]["status"] == "valid"
    assert payload["runtime"]["verificationKeys"]["status"] == "ready"
    assert load_receipt() is not None
    assert [request["path"] for request in state.requests] == [
        "/entitlements/request-token",
        "/entitlements/exchange",
        "/entitlements/keys",
    ]
    assert "qa@example.com" not in out
    assert "vs_valid" not in out


@pytest.mark.parametrize(
    ("delivery_status", "blocker_code"),
    [
        ("unavailable", "entitlement.delivery-unavailable"),
        ("throttled", "entitlement.delivery-throttled"),
    ],
)
def test_init_cli_does_not_prompt_for_token_when_delivery_was_not_accepted(
    tmp_path,
    monkeypatch,
    delivery_status,
    blocker_code,
) -> None:
    monkeypatch.setenv("VERIFYSIGNAL_RUNTIME_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("FAKE_VERIFYSIGNAL_MODE", "requires-entitlement")
    monkeypatch.delenv("VERIFYSIGNAL_EMAIL", raising=False)
    monkeypatch.delenv("VERIFYSIGNAL_EMAIL_UNLOCK_TOKEN", raising=False)
    monkeypatch.delenv("VERIFYSIGNAL_ENTITLEMENT_RECEIPT", raising=False)
    monkeypatch.delenv("VERIFYSIGNAL_ENTITLEMENT_RECEIPT_PATH", raising=False)

    with serve_fake_entitlement_backend() as (api_base_url, state):
        state.delivery_status = delivery_status
        code, out, err = _cli(
            [
                "init",
                str(tmp_path),
                "--integration",
                "codex",
                "--core-cmd",
                str(FAKE_CORE),
                "--api-base-url",
                api_base_url,
                "--json",
            ],
            stdin="qa@example.com\nvs_invalid\n",
        )

    assert code == 2, err
    payload = json.loads(out)
    assert payload["status"] == "blocked"
    assert payload["runtime"]["entitlement"]["blockerCode"] == blocker_code
    assert [request["path"] for request in state.requests] == [
        "/entitlements/request-token",
    ]
    assert "VerifySignal email unlock token" not in err


def test_init_cli_preserves_pending_delivery_when_token_did_not_arrive(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("VERIFYSIGNAL_RUNTIME_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("FAKE_VERIFYSIGNAL_MODE", "requires-entitlement")
    monkeypatch.delenv("VERIFYSIGNAL_EMAIL", raising=False)
    monkeypatch.delenv("VERIFYSIGNAL_EMAIL_UNLOCK_TOKEN", raising=False)
    monkeypatch.delenv("VERIFYSIGNAL_ENTITLEMENT_RECEIPT", raising=False)
    monkeypatch.delenv("VERIFYSIGNAL_ENTITLEMENT_RECEIPT_PATH", raising=False)

    with serve_fake_entitlement_backend() as (api_base_url, state):
        code, out, err = _cli(
            [
                "init",
                str(tmp_path),
                "--integration",
                "codex",
                "--core-cmd",
                str(FAKE_CORE),
                "--api-base-url",
                api_base_url,
                "--json",
            ],
            stdin="qa@example.com\n\n",
        )

    assert code == 2, err
    payload = json.loads(out)
    assert payload["runtime"]["entitlement"]["status"] == (
        "token-delivery-pending"
    )
    assert payload["runtime"]["entitlement"]["blockerCode"] == (
        "entitlement.unlock-required"
    )
    assert [request["path"] for request in state.requests] == [
        "/entitlements/request-token",
    ]
    assert "press Enter if it did not arrive" in err


def test_validate_cli_with_override_core_uses_cached_entitlement_receipt(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("VERIFYSIGNAL_RUNTIME_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("FAKE_VERIFYSIGNAL_MODE", "requires-entitlement")
    monkeypatch.delenv("VERIFYSIGNAL_EMAIL_UNLOCK_TOKEN", raising=False)
    monkeypatch.delenv("VERIFYSIGNAL_ENTITLEMENT_RECEIPT", raising=False)
    monkeypatch.delenv("VERIFYSIGNAL_ENTITLEMENT_RECEIPT_PATH", raising=False)
    create_main_skill_coverage_workspace(tmp_path)

    with serve_fake_entitlement_backend() as (api_base_url, _state):
        unlocked = ensure_core_runtime(
            tmp_path,
            explicit_core_cmd=str(FAKE_CORE),
            api_base_url=api_base_url,
            token="vs_valid",
            integration="claude",
            context="init",
        )
    assert unlocked.entitlement.status == "valid"

    code, out, err = _cli(
        [
            "validate",
            "profile-view-unauth",
            "--project",
            str(tmp_path),
            "--runtime-readiness",
            "--core-cmd",
            str(FAKE_CORE),
            "--api-base-url",
            api_base_url,
            "--json",
        ]
    )

    assert code == 0, err
    payload = json.loads(out)
    assert payload["status"] == "passed"
    assert payload["managedRuntimeReadiness"]["source"] == "explicit"
    assert payload["managedRuntimeReadiness"]["entitlement"]["status"] == "valid"
    assert payload["managedRuntimeReadiness"]["verificationKeys"]["status"] == "ready"
    assert payload["managedRuntimeReadiness"]["verificationKeys"]["source"] == "cache"
    assert payload["authoredEvidenceCoverageStatus"] == "complete"
    assert payload["core"]["status"] == "passed"


def test_validate_cli_with_ancestor_sibling_core_reports_cached_entitlement(tmp_path, monkeypatch) -> None:
    project = tmp_path / "Demo" / "web-app"
    project.mkdir(parents=True)
    # Named from the real executable list, so the fixture follows if the binary is ever renamed.
    write_fake_core_executable(project.parent / CORE_EXECUTABLE_NAMES[0], mode="requires-entitlement")
    monkeypatch.setenv("VERIFYSIGNAL_RUNTIME_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("FAKE_VERIFYSIGNAL_MODE", "requires-entitlement")
    monkeypatch.delenv("VERIFYSIGNAL_CORE_CMD", raising=False)
    monkeypatch.delenv("VERIFYSIGNAL_EMAIL_UNLOCK_TOKEN", raising=False)
    monkeypatch.delenv("VERIFYSIGNAL_ENTITLEMENT_RECEIPT", raising=False)
    monkeypatch.delenv("VERIFYSIGNAL_ENTITLEMENT_RECEIPT_PATH", raising=False)
    create_main_skill_coverage_workspace(project)

    with serve_fake_entitlement_backend() as (api_base_url, _state):
        unlocked = ensure_core_runtime(
            project,
            api_base_url=api_base_url,
            token="vs_valid",
            integration="claude",
            context="init",
        )
    assert unlocked.source == "ancestor-sibling"
    assert unlocked.entitlement.status == "valid"

    code, out, err = _cli(
        [
            "validate",
            "profile-view-unauth",
            "--project",
            str(project),
            "--runtime-readiness",
            "--api-base-url",
            api_base_url,
            "--json",
        ]
    )

    assert code == 0, err
    payload = json.loads(out)
    assert payload["status"] == "passed"
    assert payload["managedRuntimeReadiness"]["source"] == "ancestor-sibling"
    assert payload["managedRuntimeReadiness"]["entitlement"]["status"] == "valid"
    assert payload["managedRuntimeReadiness"]["verificationKeys"]["status"] == "ready"
    assert payload["core"]["status"] == "passed"


def test_validate_cli_with_override_core_blocks_expired_receipt_before_core_missing(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("VERIFYSIGNAL_RUNTIME_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("FAKE_VERIFYSIGNAL_MODE", "requires-entitlement")
    monkeypatch.delenv("VERIFYSIGNAL_EMAIL_UNLOCK_TOKEN", raising=False)
    monkeypatch.delenv("VERIFYSIGNAL_ENTITLEMENT_RECEIPT", raising=False)
    monkeypatch.delenv("VERIFYSIGNAL_ENTITLEMENT_RECEIPT_PATH", raising=False)
    create_main_skill_coverage_workspace(tmp_path)
    path = receipt_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "receiptSummary": {
                    "receiptId": "rcpt_expired",
                    "status": "valid",
                    "expiresAt": "2000-01-01T00:00:00Z",
                }
            }
        ),
        encoding="utf-8",
    )

    code, out, err = _cli(
        [
            "validate",
            "profile-view-unauth",
            "--project",
            str(tmp_path),
            "--runtime-readiness",
            "--core-cmd",
            str(FAKE_CORE),
            "--json",
        ]
    )

    assert code == 2, err
    payload = json.loads(out)
    assert payload["status"] == "blocked"
    assert payload["managedRuntimeReadiness"]["source"] == "none"
    assert payload["managedRuntimeReadiness"]["entitlement"]["status"] == "expired"
    assert payload["blockers"][0]["code"] == "entitlement.expired"


def test_init_api_base_url_persists_for_later_validate(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("VERIFYSIGNAL_RUNTIME_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("VERIFYSIGNAL_EMAIL_UNLOCK_TOKEN", "vs_valid")
    monkeypatch.setenv("FAKE_VERIFYSIGNAL_MODE", "requires-entitlement")
    monkeypatch.delenv("VERIFYSIGNAL_API_BASE_URL", raising=False)
    monkeypatch.delenv("VERIFYSIGNAL_ENTITLEMENT_RECEIPT", raising=False)
    monkeypatch.delenv("VERIFYSIGNAL_ENTITLEMENT_RECEIPT_PATH", raising=False)
    create_main_skill_coverage_workspace(tmp_path)

    with serve_fake_entitlement_backend() as (api_base_url, state):
        init_code, _init_out, init_err = _cli(
            [
                "init",
                str(tmp_path),
                "--integration",
                "claude",
                "--core-cmd",
                str(FAKE_CORE),
                "--api-base-url",
                api_base_url,
                "--json",
            ]
        )
        assert init_code == 0, init_err
        workspace = load_document(tmp_path / ".verifysignal" / "workspace.yaml")
        assert workspace["entitlementApiBaseUrl"] == api_base_url

        receipt = receipt_path()
        receipt.unlink()
        validate_code, validate_out, validate_err = _cli(
            [
                "validate",
                "profile-view-unauth",
                "--project",
                str(tmp_path),
                "--runtime-readiness",
                "--core-cmd",
                str(FAKE_CORE),
                "--json",
            ]
        )

    assert validate_code == 0, validate_err
    payload = json.loads(validate_out)
    assert payload["managedRuntimeReadiness"]["api"]["baseUrl"] == api_base_url
    assert payload["managedRuntimeReadiness"]["api"]["source"] == "workspace"
    assert payload["managedRuntimeReadiness"]["entitlement"]["status"] == "valid"
    assert payload["managedRuntimeReadiness"]["verificationKeys"]["status"] == "ready"
    assert [request["path"] for request in state.requests if request["path"] == "/entitlements/exchange"] == [
        "/entitlements/exchange",
        "/entitlements/exchange",
    ]


def test_managed_runtime_sources_prepare_verification_keys(tmp_path, monkeypatch) -> None:
    platform = normalize_platform()
    assert platform is not None
    monkeypatch.setenv("VERIFYSIGNAL_RUNTIME_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("VERIFYSIGNAL_CORE_VERSION", "0.5.1")
    monkeypatch.delenv("VERIFYSIGNAL_CORE_CMD", raising=False)
    monkeypatch.delenv("VERIFYSIGNAL_ENTITLEMENT_PUBLIC_KEYS_JSON", raising=False)
    monkeypatch.delenv("VERIFYSIGNAL_ENTITLEMENT_RECEIPT", raising=False)
    monkeypatch.delenv("VERIFYSIGNAL_ENTITLEMENT_RECEIPT_PATH", raising=False)
    distribution = build_managed_runtime_distribution(tmp_path / "distribution", platform=platform, mode="requires-entitlement")

    with serve_fake_entitlement_backend(distribution) as (api_base_url, state):
        downloaded = ensure_core_runtime(
            tmp_path,
            api_base_url=api_base_url,
            token="vs_valid",
            integration="claude",
            context="init",
        )
        state.keys_status = "unavailable"
        cached = ensure_core_runtime(
            tmp_path,
            api_base_url=api_base_url,
            integration="claude",
            context="validate",
        )

    assert downloaded.status == "ready"
    assert downloaded.source == "managed-download"
    assert downloaded.verificationKeys.status == "ready"
    assert downloaded.verificationKeys.source == "fetched"
    assert any(request["path"] == "/entitlements/keys" for request in state.requests)
    assert cached.status == "ready"
    assert cached.source == "managed-cache"
    assert cached.verificationKeys.status == "ready"
    assert cached.verificationKeys.source == "cache"


def test_init_blocks_when_verification_keys_are_unavailable_after_exchange(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("VERIFYSIGNAL_RUNTIME_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("VERIFYSIGNAL_EMAIL_UNLOCK_TOKEN", "vs_valid")
    monkeypatch.setenv("FAKE_VERIFYSIGNAL_MODE", "requires-entitlement")
    monkeypatch.delenv("VERIFYSIGNAL_ENTITLEMENT_PUBLIC_KEYS_JSON", raising=False)
    monkeypatch.delenv("VERIFYSIGNAL_ENTITLEMENT_RECEIPT", raising=False)
    monkeypatch.delenv("VERIFYSIGNAL_ENTITLEMENT_RECEIPT_PATH", raising=False)

    with serve_fake_entitlement_backend() as (api_base_url, state):
        state.keys_status = "unavailable"
        code, out, err = _cli(
            [
                "init",
                str(tmp_path),
                "--integration",
                "claude",
                "--core-cmd",
                str(FAKE_CORE),
                "--api-base-url",
                api_base_url,
                "--json",
            ]
        )

    assert code == 2, err
    payload = json.loads(out)
    assert payload["status"] == "blocked"
    assert payload["runtime"]["verificationKeys"]["status"] == "blocked"
    assert payload["runtime"]["verificationKeys"]["blockerCode"] == "entitlement.keys-unavailable"
    assert payload["runtime"]["blockers"][0]["code"] == "entitlement.keys-unavailable"


def test_runtime_readiness_reports_key_unknown_when_fetched_keys_omit_receipt_key(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("VERIFYSIGNAL_RUNTIME_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("FAKE_VERIFYSIGNAL_MODE", "requires-entitlement")
    monkeypatch.delenv("VERIFYSIGNAL_ENTITLEMENT_PUBLIC_KEYS_JSON", raising=False)
    monkeypatch.delenv("VERIFYSIGNAL_ENTITLEMENT_RECEIPT", raising=False)
    monkeypatch.delenv("VERIFYSIGNAL_ENTITLEMENT_RECEIPT_PATH", raising=False)

    with serve_fake_entitlement_backend() as (api_base_url, state):
        state.keys_status = "mismatched"
        result = ensure_core_runtime(
            tmp_path,
            explicit_core_cmd=str(FAKE_CORE),
            api_base_url=api_base_url,
            token="vs_valid",
            integration="claude",
            context="init",
        )

    payload = result.to_dict()
    assert payload["status"] == "blocked"
    assert payload["verificationKeys"]["status"] == "blocked"
    assert payload["verificationKeys"]["blockerCode"] == "entitlement.key-unknown"
    blocker = payload["blockers"][0]
    assert blocker["code"] == "entitlement.key-unknown"
    assert blocker["repairable"] is False
    assert payload["nextAction"] == blocker["recoveryCommand"]
    assert "public verification keys" in blocker["recoveryCommand"]
    assert "init" not in blocker["recoveryCommand"].lower()
    assert "core setup" not in blocker["recoveryCommand"].lower()


def test_cached_matching_verification_keys_are_reused_when_key_service_is_unavailable(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("VERIFYSIGNAL_RUNTIME_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("FAKE_VERIFYSIGNAL_MODE", "requires-entitlement")
    monkeypatch.delenv("VERIFYSIGNAL_ENTITLEMENT_PUBLIC_KEYS_JSON", raising=False)
    monkeypatch.delenv("VERIFYSIGNAL_ENTITLEMENT_RECEIPT", raising=False)
    monkeypatch.delenv("VERIFYSIGNAL_ENTITLEMENT_RECEIPT_PATH", raising=False)

    with serve_fake_entitlement_backend() as (api_base_url, state):
        unlocked = ensure_core_runtime(
            tmp_path,
            explicit_core_cmd=str(FAKE_CORE),
            api_base_url=api_base_url,
            token="vs_valid",
            integration="claude",
            context="init",
        )
        state.keys_status = "unavailable"
        cached = ensure_core_runtime(
            tmp_path,
            explicit_core_cmd=str(FAKE_CORE),
            api_base_url=api_base_url,
            integration="claude",
            context="validate",
        )

    assert unlocked.status == "ready"
    assert cached.status == "ready"
    assert cached.verificationKeys.status == "ready"
    assert cached.verificationKeys.source == "cache"


def test_cache_binding_mismatch_refreshes_verification_keys_before_readiness(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("VERIFYSIGNAL_RUNTIME_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("FAKE_VERIFYSIGNAL_MODE", "requires-entitlement")
    monkeypatch.delenv("VERIFYSIGNAL_ENTITLEMENT_PUBLIC_KEYS_JSON", raising=False)
    monkeypatch.delenv("VERIFYSIGNAL_ENTITLEMENT_RECEIPT", raising=False)
    monkeypatch.delenv("VERIFYSIGNAL_ENTITLEMENT_RECEIPT_PATH", raising=False)
    save_verification_keys(
        {
            "schema": "verifysignal.entitlement-keys/v1",
            "schemaVersion": 1,
            "sourceApiBaseUrl": "http://old.example/api",
            "issuer": "https://verifysignal.io",
            "keys": [{"keyId": "ps-entitlement-2026-06", "algorithm": "ed25519", "publicKeyPem": "public", "status": "active"}],
        }
    )

    with serve_fake_entitlement_backend() as (api_base_url, state):
        result = ensure_core_runtime(
            tmp_path,
            explicit_core_cmd=str(FAKE_CORE),
            api_base_url=api_base_url,
            token="vs_valid",
            integration="claude",
            context="init",
        )

    assert result.status == "ready"
    assert result.verificationKeys.status == "ready"
    assert result.verificationKeys.source == "fetched"
    assert state.request_paths("/entitlements/keys") == ["/entitlements/keys"]
    cached = load_verification_keys()
    assert cached is not None
    assert cached["sourceApiBaseUrl"] == api_base_url


def _cli(args: list[str], *, stdin: str = "") -> tuple[int, str, str]:
    from verifysignal_spec.cli import main

    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr), patch("sys.stdin", _TtyInput(stdin)):
        code = main(args)
    return code, stdout.getvalue(), stderr.getvalue()


class _TtyInput(io.StringIO):
    def isatty(self) -> bool:
        return True
