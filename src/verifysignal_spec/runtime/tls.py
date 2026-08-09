"""TLS trust-store resolution for every runtime HTTPS call.

The installers this product advertises (install.sh via uv, python.org
framework builds on macOS) produce interpreters whose OpenSSL has NO default
CA bundle: ``ssl.get_default_verify_paths().cafile`` is ``None`` and the
default context trusts zero authorities. Plain ``urllib.request.urlopen``
then fails every HTTPS request with CERTIFICATE_VERIFY_FAILED, which the
distribution client can only surface as ``api.unavailable`` — a fresh Mac
install cannot reach the runtime API at all.

The context below keeps the system trust store whenever it actually contains
authorities (Linux distros, properly provisioned machines) and falls back to
certifi's bundle only when the store is empty, so behavior is unchanged on
systems that already work.
"""

from __future__ import annotations

import ssl
from functools import lru_cache


@lru_cache(maxsize=1)
def secure_ssl_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    if context.cert_store_stats().get("x509_ca", 0) > 0:
        return context
    try:
        import certifi
    except ImportError:
        return context
    return ssl.create_default_context(cafile=certifi.where())
