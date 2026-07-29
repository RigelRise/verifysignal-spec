from __future__ import annotations

import json
import os
import socket
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from verifysignal_spec import __version__

from .cache import DEFAULT_API_BASE_URL, cache_root
from .distribution import normalize_platform
from .models import (
    EntitlementClientConfig,
    RuntimeEntitlementReceipt,
    RuntimeEntitlementStatus,
    RuntimeSetupBlocker,
)

# The canonical API host is www: the apex (verifysignal.io) 308-redirects to it, and urllib does not
# reliably re-POST across a 308, so the CLI must target www directly or every POST (exchange/refresh/
# usage) fails. (The receipt ISSUER stays the apex — that is an identifier, not an HTTP target.)
PRODUCTION_RECEIPT_ISSUER = "https://verifysignal.io"
DEFAULT_HTTP_TIMEOUT_SECONDS = 30
MIN_HTTP_TIMEOUT_SECONDS = 1
MAX_HTTP_TIMEOUT_SECONDS = 120
# Refresh proactively once the receipt is within this window of expiry, so an active user renews
# BEFORE lapsing and an occasional offline moment never blocks a run (the 7-day receipt is still valid).
REFRESH_THRESHOLD_SECONDS = 2 * 24 * 60 * 60


@dataclass(slots=True)
class EntitlementResponse:
    data: dict[str, Any]
    blocker: RuntimeSetupBlocker | None = None


@dataclass(slots=True)
class TokenExchangeResponse:
    receipt: RuntimeEntitlementReceipt | None = None
    data: dict[str, Any] | None = None
    blocker: RuntimeSetupBlocker | None = None
    # The durable refresh credential the exchange bootstraps (None on the /refresh path, which reuses
    # the stored credential without rotating it).
    refresh_credential: str | None = None


def resolve_entitlement_config(
    *,
    api_base_url: str | None = None,
    workspace_api_base_url: str | None = None,
    source: str | None = None,
    timeout_seconds: int | None = None,
) -> EntitlementClientConfig:
    env_url = os.environ.get("VERIFYSIGNAL_API_BASE_URL")
    env_timeout = os.environ.get("VERIFYSIGNAL_API_TIMEOUT_SECONDS")
    if api_base_url:
        resolved = api_base_url
        resolved_source = source or "flag"
    elif env_url:
        resolved = env_url
        resolved_source = source or "environment"
    elif workspace_api_base_url:
        resolved = workspace_api_base_url
        resolved_source = source or "workspace"
    else:
        resolved = DEFAULT_API_BASE_URL
        resolved_source = source or "default"
    timeout = timeout_seconds
    if timeout is None and env_timeout:
        try:
            timeout = int(env_timeout)
        except ValueError:
            timeout = DEFAULT_HTTP_TIMEOUT_SECONDS
    timeout = max(MIN_HTTP_TIMEOUT_SECONDS, min(MAX_HTTP_TIMEOUT_SECONDS, int(timeout or DEFAULT_HTTP_TIMEOUT_SECONDS)))
    _validate_api_base_url(resolved)
    return EntitlementClientConfig(
        apiBaseUrl=resolved.rstrip("/"),
        source=resolved_source,  # type: ignore[arg-type]
        timeoutSeconds=timeout,
        cliVersion=__version__,
        platform=normalize_platform(),
    )


def receipt_path(api_base_url: str | None = None) -> Path:
    explicit = os.environ.get("VERIFYSIGNAL_ENTITLEMENT_RECEIPT_PATH")
    if explicit:
        return Path(explicit).expanduser().resolve()
    return cache_root(api_base_url) / "entitlement" / "receipt.json"


def load_receipt(
    api_base_url: str | None = None,
) -> RuntimeEntitlementReceipt | None:
    explicit = os.environ.get("VERIFYSIGNAL_ENTITLEMENT_RECEIPT") or os.environ.get("VERIFYSIGNAL_ENTITLEMENT_RECEIPT_PATH")
    path = (
        Path(explicit).expanduser()
        if explicit
        else receipt_path(api_base_url)
    )
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8").strip()
        data = json.loads(text)
        if isinstance(data, dict) and data.get("schema") == "verifysignal.entitlement-receipt/v1":
            receipt = RuntimeEntitlementReceipt.from_raw_receipt_payload(text)
        else:
            receipt = RuntimeEntitlementReceipt.from_dict(data)
        receipt.path = str(path)
        return receipt
    except Exception:
        return RuntimeEntitlementReceipt(receiptId="", status="malformed", path=str(path))


def save_receipt(
    receipt: RuntimeEntitlementReceipt,
    *,
    api_base_url: str | None = None,
) -> RuntimeEntitlementReceipt:
    path = receipt_path(api_base_url)
    path.parent.mkdir(parents=True, exist_ok=True)
    if receipt.receiptPayload:
        path.write_text(receipt.receiptPayload, encoding="utf-8")
    else:
        path.write_text(json.dumps(receipt.to_file_dict(), indent=2), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    receipt.path = str(path)
    return receipt


def refresh_credential_path(api_base_url: str | None = None) -> Path:
    return cache_root(api_base_url) / "entitlement" / "refresh.json"


def save_refresh_credential(
    credential: str,
    *,
    api_base_url: str | None = None,
) -> None:
    """Persist the durable refresh credential 0600, next to the receipt.

    The credential is a secret bearer (it mints receipts); it is written with the same
    mkdir + write + chmod(0o600) pattern as save_receipt.
    """
    path = refresh_credential_path(api_base_url)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema": "verifysignal.refresh-credential/v1", "credential": credential}), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def load_refresh_credential(api_base_url: str | None = None) -> str | None:
    path = refresh_credential_path(api_base_url)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        credential = data.get("credential") if isinstance(data, dict) else None
        return credential if isinstance(credential, str) and credential else None
    except Exception:
        return None


def clear_refresh_credential(api_base_url: str | None = None) -> None:
    """Discard a dead refresh credential (revoked/rejected) so we stop retrying a doomed refresh."""
    try:
        refresh_credential_path(api_base_url).unlink(missing_ok=True)
    except OSError:
        pass


def refresh_pending_key_path(api_base_url: str | None = None) -> Path:
    return (
        cache_root(api_base_url)
        / "entitlement"
        / "refresh-pending.json"
    )


def load_or_create_pending_refresh_key(
    api_base_url: str | None = None,
) -> str:
    """The idempotency key for the CURRENT renewal attempt, persisted until it succeeds.

    A retry (including after a crash mid-request) reuses the same key, so the backend replays the
    already-minted receipt instead of double-minting. Only a successful renewal clears it.
    """
    path = refresh_pending_key_path(api_base_url)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        key = data.get("idempotencyKey") if isinstance(data, dict) else None
        if isinstance(key, str) and key:
            return key
    except Exception:
        pass
    key = f"refresh-{uuid.uuid4()}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema": "verifysignal.refresh-pending/v1", "idempotencyKey": key}), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return key


def clear_pending_refresh_key(api_base_url: str | None = None) -> None:
    try:
        refresh_pending_key_path(api_base_url).unlink(missing_ok=True)
    except OSError:
        pass


def receipt_status(receipt: dict[str, Any] | RuntimeEntitlementReceipt) -> RuntimeEntitlementStatus:
    parsed = receipt if isinstance(receipt, RuntimeEntitlementReceipt) else RuntimeEntitlementReceipt.from_dict(receipt)
    status = parsed.status
    if status == "expired-token":
        return RuntimeEntitlementStatus(
            status="rejected",
            receiptId=parsed.receiptId,
            expiresAt=parsed.expiresAt,
            message="Email unlock token expired before exchange.",
            blockerCode="entitlement.expired-token",
        )
    if status in {"revoked", "rejected", "malformed", "unverifiable"}:
        return RuntimeEntitlementStatus(
            status=status,  # type: ignore[arg-type]
            receiptId=parsed.receiptId,
            issuer=parsed.issuer,
            expiresAt=parsed.expiresAt,
            scopes=list(parsed.scopes),
            keyId=parsed.keyId,
            usePolicy=dict(parsed.usePolicy),
            tokenPolicy=dict(parsed.tokenPolicy),
            message=f"Entitlement receipt is {status}.",
            blockerCode=f"entitlement.{status}",
            receiptPath=parsed.path,
        )
    if status != "valid":
        return RuntimeEntitlementStatus(
            status="rejected",
            receiptId=parsed.receiptId,
            expiresAt=parsed.expiresAt,
            message="Entitlement receipt was rejected.",
            blockerCode="entitlement.rejected",
            receiptPath=parsed.path,
        )
    if _is_expired(parsed.expiresAt):
        return RuntimeEntitlementStatus(
            status="expired",
            receiptId=parsed.receiptId,
            issuer=parsed.issuer,
            expiresAt=parsed.expiresAt,
            scopes=list(parsed.scopes),
            keyId=parsed.keyId,
            usePolicy=dict(parsed.usePolicy),
            tokenPolicy=dict(parsed.tokenPolicy),
            message="Entitlement receipt expired.",
            blockerCode="entitlement.expired",
            receiptPath=parsed.path,
        )
    status_result = parsed.to_status()
    status_result.message = "Entitlement receipt is valid."
    return status_result


def _try_silent_refresh(
    client: EntitlementClient,
    receipt: RuntimeEntitlementReceipt | None,
    status: RuntimeEntitlementStatus,
    *,
    api_base_url: str,
) -> RuntimeEntitlementStatus | None:
    """Silently re-mint a fresh 7-day receipt from the durable refresh credential (no email).

    Returns a resolved status when it acted (renewed, or an honest offline block), or None to let the
    normal email-token path handle it. Runs when the receipt is expired (reactive) or within the
    proactive window while still valid; a transient failure on a still-valid receipt keeps using it.
    """
    if receipt is None or status.status not in {"valid", "expired"}:
        return None
    credential = load_refresh_credential(api_base_url)
    if not credential:
        return None
    if status.status == "valid" and not _is_near_expiry(receipt.expiresAt, REFRESH_THRESHOLD_SECONDS):
        return None

    refreshed = client.refresh(
        credential,
        idempotency_key=load_or_create_pending_refresh_key(api_base_url),
    )
    if refreshed.receipt:
        # Success consumes the pending idempotency key; the NEXT renewal is a new attempt.
        clear_pending_refresh_key(api_base_url)
        return receipt_status(
            save_receipt(
                refreshed.receipt,
                api_base_url=api_base_url,
            )
        )

    blocker = refreshed.blocker
    if blocker and blocker.code in {"entitlement.invalid-token", "entitlement.expired-token", "entitlement.rejected"}:
        # The credential itself is dead (revoked/expired). Discard it and fall back to the email path
        # rather than retrying a doomed refresh on every run.
        clear_refresh_credential(api_base_url)
        clear_pending_refresh_key(api_base_url)
        return None
    if status.status == "valid":
        # Transient failure (offline) but the current receipt is still valid — keep using it.
        return status
    # Expired + transient failure: honest, no elaborate grace — reconnect to revalidate.
    return RuntimeEntitlementStatus(
        status="expired",
        receiptId=status.receiptId,
        expiresAt=status.expiresAt,
        message="Entitlement receipt expired; reconnect to the internet to revalidate automatically.",
        blockerCode="entitlement.expired",
    )


def ensure_entitlement(
    *,
    config: EntitlementClientConfig | None = None,
    email: str | None = None,
    token: str | None = None,
    request_delivery: bool = False,
    integration: str | None = None,
) -> RuntimeEntitlementStatus:
    config = config or resolve_entitlement_config()
    receipt = load_receipt(config.apiBaseUrl)
    status = receipt_status(receipt) if receipt else RuntimeEntitlementStatus(status="required", message="Email unlock token is required.", blockerCode="entitlement.unlock-required")
    client = EntitlementClient(config)

    refreshed = _try_silent_refresh(
        client,
        receipt,
        status,
        api_base_url=config.apiBaseUrl,
    )
    if refreshed is not None:
        return refreshed
    if status.status == "valid":
        return status

    raw_token = token or os.environ.get("VERIFYSIGNAL_EMAIL_UNLOCK_TOKEN")
    if raw_token:
        exchanged = client.exchange_token(raw_token)
        if exchanged.blocker:
            return RuntimeEntitlementStatus(status="rejected", message=exchanged.blocker.message, blockerCode=exchanged.blocker.code)
        if exchanged.receipt:
            if exchanged.refresh_credential:
                save_refresh_credential(
                    exchanged.refresh_credential,
                    api_base_url=config.apiBaseUrl,
                )
            saved = save_receipt(
                exchanged.receipt,
                api_base_url=config.apiBaseUrl,
            )
            return receipt_status(saved)
    delivery_email = email or os.environ.get("VERIFYSIGNAL_EMAIL")
    if request_delivery and delivery_email:
        delivery = client.request_email_token(delivery_email, integration=integration)
        if delivery.blocker:
            return RuntimeEntitlementStatus(status="required", message=delivery.blocker.message, blockerCode=delivery.blocker.code)
        return RuntimeEntitlementStatus(status="token-delivery-pending", message="Email unlock token delivery was requested.", blockerCode="entitlement.unlock-required")
    return status


def valid_receipt_path(api_base_url: str | None = None) -> str | None:
    receipt = load_receipt(api_base_url)
    if not receipt:
        return None
    status = receipt_status(receipt)
    return status.receiptPath if status.status == "valid" else None


def api_base_url_for_runtime(
    managed_runtime: Any,
    fallback: str | None = None,
) -> str | None:
    """Resolve an endpoint without requiring older runtime doubles to expose it."""
    api = getattr(managed_runtime, "api", None)
    if isinstance(api, dict):
        value = api.get("baseUrl")
    else:
        value = getattr(api, "baseUrl", None)
    return value if isinstance(value, str) and value else fallback


def exchange_email_token(token: str, *, config: EntitlementClientConfig | None = None) -> RuntimeEntitlementReceipt:
    """Compatibility wrapper for tests and older callers.

    Production code should use EntitlementClient.exchange_token() so backend
    failure blockers are preserved. This wrapper still returns a receipt object.
    """
    result = EntitlementClient(config or resolve_entitlement_config()).exchange_token(token)
    if result.receipt:
        return result.receipt
    blocker = result.blocker
    status = "expired-token" if blocker and blocker.code == "entitlement.expired-token" else "rejected"
    return RuntimeEntitlementReceipt(receiptId="", status=status)


class EntitlementClient:
    def __init__(self, config: EntitlementClientConfig | None = None) -> None:
        self.config = config or resolve_entitlement_config()

    def request_email_token(self, email: str, *, integration: str | None = None) -> EntitlementResponse:
        payload = {
            "schema": "verifysignal.entitlement-token-request/v1",
            "schemaVersion": 1,
            "email": email,
            "client": {
                "cliVersion": self.config.cliVersion,
                "platform": self.config.platform,
                "integration": integration,
            },
        }
        status, data, transport_blocker = self._json_request("POST", "/entitlements/request-token", payload=payload)
        if transport_blocker:
            return EntitlementResponse(data={}, blocker=transport_blocker)
        if status != 200:
            return EntitlementResponse(data={}, blocker=_http_blocker(status, data, delivery=True))
        blocker = _validate_token_delivery(data, production=self.config.apiBaseUrl == DEFAULT_API_BASE_URL)
        return EntitlementResponse(data=data, blocker=blocker)

    def exchange_token(self, token: str) -> TokenExchangeResponse:
        payload = {
            "schema": "verifysignal.entitlement-exchange-request/v1",
            "schemaVersion": 1,
            "token": token,
            "client": {
                "cliVersion": self.config.cliVersion,
                "platform": self.config.platform,
            },
        }
        status, data, transport_blocker = self._json_request("POST", "/entitlements/exchange", payload=payload)
        if transport_blocker:
            return TokenExchangeResponse(data={}, blocker=transport_blocker)
        if status != 200:
            return TokenExchangeResponse(data={}, blocker=_http_blocker(status, data, exchange=True))
        blocker = _validate_exchange(data, production=self.config.apiBaseUrl == DEFAULT_API_BASE_URL)
        if blocker:
            return TokenExchangeResponse(data=data, blocker=blocker)
        receipt = RuntimeEntitlementReceipt.from_dict(data)
        credential = data.get("refreshCredential")
        return TokenExchangeResponse(
            receipt=receipt,
            data=data,
            refresh_credential=credential if isinstance(credential, str) and credential else None,
        )

    def refresh(self, credential: str, *, idempotency_key: str | None = None) -> TokenExchangeResponse:
        """Silently re-mint a fresh 7-day receipt from the durable refresh credential (no email)."""
        payload: dict[str, Any] = {
            "schema": "verifysignal.entitlement-refresh-request/v1",
            "schemaVersion": 1,
            "credential": credential,
            "client": {
                "cliVersion": self.config.cliVersion,
                "platform": self.config.platform,
            },
        }
        if idempotency_key:
            payload["idempotencyKey"] = idempotency_key
        status, data, transport_blocker = self._json_request("POST", "/entitlements/refresh", payload=payload)
        if transport_blocker:
            return TokenExchangeResponse(data={}, blocker=transport_blocker)
        if status != 200:
            return TokenExchangeResponse(data={}, blocker=_http_blocker(status, data, exchange=True))
        blocker = _validate_refresh(data, production=self.config.apiBaseUrl == DEFAULT_API_BASE_URL)
        if blocker:
            return TokenExchangeResponse(data=data, blocker=blocker)
        receipt = RuntimeEntitlementReceipt.from_dict(data)
        return TokenExchangeResponse(receipt=receipt, data=data)

    def _json_request(self, method: str, path: str, *, payload: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> tuple[int, dict[str, Any], RuntimeSetupBlocker | None]:
        url = f"{self.config.apiBaseUrl}{path}"
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(
            url,
            data=body,
            method=method,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Cache-Control": "no-store",
                **(headers or {}),
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.config.timeoutSeconds) as response:  # nosec B310 - official/explicit API URL
                data = _parse_json_response(response.read())
                return response.status, data, None
        except urllib.error.HTTPError as exc:
            return exc.code, _parse_json_response(exc.read()), None
        except (urllib.error.URLError, TimeoutError, socket.timeout, OSError):
            return 0, {}, RuntimeSetupBlocker(code="api.unavailable", message="VerifySignal entitlement API is unavailable.")


def _validate_api_base_url(value: str) -> None:
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("VerifySignal API base URL must be an http(s) URL.")
    if parsed.username or parsed.password or parsed.query:
        raise ValueError("VerifySignal API base URL must not contain credentials or query secrets.")


def _parse_json_response(raw: bytes) -> dict[str, Any]:
    try:
        data = json.loads(raw.decode("utf-8") or "{}")
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _validate_token_delivery(data: dict[str, Any], *, production: bool) -> RuntimeSetupBlocker | None:
    policy = data.get("tokenPolicy") if isinstance(data.get("tokenPolicy"), dict) else {}
    if data.get("schema") != "verifysignal.entitlement-token-delivery/v1" or data.get("schemaVersion") != 1 or data.get("status") != "accepted":
        return RuntimeSetupBlocker(code="api.incompatible", message="Entitlement token delivery response did not match the public contract.")
    if production and (policy.get("maxExchanges") != 1 or policy.get("maxExchangesPerHour") != 1 or policy.get("defaultTokenTtlDays") != 30):
        return RuntimeSetupBlocker(code="api.incompatible", message="Production entitlement token policy did not match the public/free contract.")
    return None


def _validate_exchange(data: dict[str, Any], *, production: bool) -> RuntimeSetupBlocker | None:
    summary = data.get("receiptSummary") if isinstance(data.get("receiptSummary"), dict) else {}
    token_policy = summary.get("tokenPolicy") if isinstance(summary.get("tokenPolicy"), dict) else {}
    use_policy = summary.get("usePolicy") if isinstance(summary.get("usePolicy"), dict) else {}
    if data.get("schema") != "verifysignal.entitlement-exchange/v1" or data.get("schemaVersion") != 1:
        return RuntimeSetupBlocker(code="api.incompatible", message="Entitlement exchange response did not match the public contract.")
    if not isinstance(data.get("receipt"), str) or not data.get("receipt") or not summary.get("receiptId"):
        return RuntimeSetupBlocker(code="entitlement.malformed", message="Entitlement exchange did not include a usable receipt.")
    if production and summary.get("issuer") != PRODUCTION_RECEIPT_ISSUER:
        return RuntimeSetupBlocker(code="entitlement.rejected", message="Production entitlement receipt issuer is not trusted.")
    if use_policy.get("policyId") != "public-free":
        return RuntimeSetupBlocker(code="api.incompatible", message="Entitlement receipt use policy did not match the expected public/free contract.")
    if token_policy.get("maxExchanges") != 1 or token_policy.get("maxExchangesPerHour") != 1:
        return RuntimeSetupBlocker(code="api.incompatible", message="Entitlement exchange policy did not expose the expected exchange limits.")
    return None


def _validate_refresh(data: dict[str, Any], *, production: bool) -> RuntimeSetupBlocker | None:
    summary = data.get("receiptSummary") if isinstance(data.get("receiptSummary"), dict) else {}
    use_policy = summary.get("usePolicy") if isinstance(summary.get("usePolicy"), dict) else {}
    if data.get("schema") != "verifysignal.entitlement-refresh/v1" or data.get("schemaVersion") != 1:
        return RuntimeSetupBlocker(code="api.incompatible", message="Entitlement refresh response did not match the public contract.")
    if not isinstance(data.get("receipt"), str) or not data.get("receipt") or not summary.get("receiptId"):
        return RuntimeSetupBlocker(code="entitlement.malformed", message="Entitlement refresh did not include a usable receipt.")
    if production and summary.get("issuer") != PRODUCTION_RECEIPT_ISSUER:
        return RuntimeSetupBlocker(code="entitlement.rejected", message="Production entitlement receipt issuer is not trusted.")
    if use_policy.get("policyId") != "public-free":
        return RuntimeSetupBlocker(code="api.incompatible", message="Refreshed entitlement receipt use policy did not match the expected public/free contract.")
    return None


def _http_blocker(status: int, data: dict[str, Any], *, delivery: bool = False, exchange: bool = False) -> RuntimeSetupBlocker:
    code = str(data.get("code") or "")
    if status in {500, 503}:
        mapped = "entitlement.delivery-unavailable" if delivery and status == 503 else "api.unavailable"
    elif status == 429:
        mapped = "entitlement.delivery-throttled" if delivery else "entitlement.exchange-throttled"
    elif exchange and status == 401:
        mapped = "entitlement.invalid-token"
    elif exchange and status == 403:
        mapped = code if code in {"entitlement.expired-token", "entitlement.exchange-limit", "entitlement.exchange-throttled", "entitlement.rejected"} else "entitlement.rejected"
    elif status == 400:
        mapped = "api.incompatible"
    else:
        mapped = code if code else "api.unavailable"
    return RuntimeSetupBlocker(code=mapped, message=_safe_failure_message(mapped))


def _safe_failure_message(code: str) -> str:
    messages = {
        "api.unavailable": "VerifySignal entitlement API is unavailable.",
        "api.incompatible": "VerifySignal entitlement API response is incompatible with this CLI.",
        "entitlement.delivery-unavailable": "VerifySignal could not send an unlock token right now.",
        "entitlement.delivery-throttled": "Unlock token delivery is temporarily throttled.",
        "entitlement.invalid-token": "The unlock token was rejected.",
        "entitlement.expired-token": "The unlock token has expired.",
        "entitlement.exchange-limit": "The unlock token exchange limit has been reached.",
        "entitlement.exchange-throttled": "Unlock token exchange is temporarily throttled.",
        "entitlement.rejected": "The entitlement request was rejected.",
        "entitlement.malformed": "The entitlement receipt is malformed.",
    }
    return messages.get(code, "VerifySignal runtime entitlement is blocked.")


def _is_expired(value: str | None) -> bool:
    if not value:
        return True
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return True
    return parsed <= datetime.now(UTC)


def _is_near_expiry(value: str | None, within_seconds: int) -> bool:
    """True when the receipt expires within `within_seconds` (or is unparseable). Used to renew
    proactively while the receipt is still valid, so an active user never actually lapses."""
    if not value:
        return True
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return True
    return (parsed - datetime.now(UTC)).total_seconds() <= within_seconds
