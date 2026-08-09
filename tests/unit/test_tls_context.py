from __future__ import annotations

from verifysignal_spec.runtime.tls import secure_ssl_context


def test_secure_ssl_context_trusts_at_least_one_authority() -> None:
    """Interpreters shipped by the advertised installers (uv, python.org macOS)
    have an empty default trust store; the shared context must never be empty,
    falling back to certifi's bundle when the system store has no CAs."""

    context = secure_ssl_context()
    assert context.cert_store_stats().get("x509_ca", 0) > 0


def test_secure_ssl_context_is_cached() -> None:
    assert secure_ssl_context() is secure_ssl_context()
