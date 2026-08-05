"""Owner-only file protection that means the same thing on POSIX and on Windows.

The CLI writes bearer secrets to disk: the entitlement receipt, the durable refresh credential that
mints receipts, and the test environment file. Every one of them was protected with
``chmod(0o600)``, and on Windows ``os.chmod`` honours only the read-only bit — the call succeeded
and protected nothing.

Three concrete defects, not one:

* ``os.fchmod`` **does not exist on Windows**. ``AttributeError`` is not an ``OSError``, so the
  handler guarding the credential write did not catch it and the CLI crashed with a traceback.
* ``stat.S_IMODE(...) & 0o077`` is **always truthy on Windows**, where Python synthesizes ``0o666``.
  Every explicitly selected ``--env-file`` was therefore rejected as insecure, which made
  credentials-by-env-file unusable there.
* The prepared-credentials payload reported ``"permissions": "0600"`` unconditionally — a number
  that is meaningless on Windows and was, there, simply false.

``icacls`` is used rather than ``pywin32``: it ships with every supported Windows, needs no
dependency (a binary wheel per interpreter is a poor trade for one function), and lets the ACL be
verified the same way it is applied.

Two details carry the whole Windows implementation:

* the grant is by **SID**, never by name. ``Users``, ``Utilisateurs`` and ``Benutzer`` are the same
  group, and a name-based rule silently fails on a localized install.
* ``/inheritance:r`` is load-bearing. Without it the parent directory's inherited "Users: Read" ACE
  survives and the hardening is theatre.
"""

from __future__ import annotations

import os
import re
import stat
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Any

from verifysignal_spec.process import run_text

__all__ = ["harden_owner_only", "is_owner_only", "describe_protection", "ProtectionError"]

_IS_WINDOWS = os.name == "nt"

#: Principals that cannot be meaningfully excluded from a file on Windows and are already
#: root-equivalent, so their presence does not make a file non-owner-only.
_TOLERATED_SIDS = frozenset({"S-1-5-18", "S-1-5-32-544"})


class ProtectionError(OSError):
    """Owner-only protection could not be applied. An OSError so existing handlers still catch it."""


def harden_owner_only(path: Path, *, is_windows: bool | None = None) -> None:
    """Restrict ``path`` to its owner, using whatever mechanism the host actually enforces."""

    if not _windows(is_windows):
        path.chmod(0o600)
        return

    sid = _current_user_sid()
    if not sid:
        raise ProtectionError(f"Could not determine the current user's SID to protect {path}.")
    result = _icacls(["icacls", str(path), "/inheritance:r", "/grant:r", f"*{sid}:F"])
    if result is None:
        raise ProtectionError(f"icacls is unavailable, so {path} cannot be restricted to its owner.")
    if result.returncode != 0:
        raise ProtectionError(f"icacls could not restrict {path} to its owner: {(result.stdout or '').strip()}")


def is_owner_only(path: Path, *, is_windows: bool | None = None) -> bool:
    """Whether ``path`` is readable and writable only by its owner."""

    if not _windows(is_windows):
        return stat.S_IMODE(path.stat().st_mode) & 0o077 == 0

    result = _icacls(["icacls", str(path)])
    if result is None or result.returncode != 0:
        return False
    sid = _current_user_sid()
    for principal in _granted_principals(result.stdout or ""):
        if principal == sid or principal in _TOLERATED_SIDS:
            continue
        return False
    return True


def describe_protection(path: Path, *, is_windows: bool | None = None) -> dict[str, Any]:
    """Public, honest description of how ``path`` is protected on THIS host.

    Replaces the old unconditional ``"permissions": "0600"``, which said a POSIX mode number even on
    a host where that number means nothing. ``enforced`` is read back from the file rather than
    assumed from the fact that a call was made.
    """

    if not _windows(is_windows):
        return {
            "scheme": "posix-mode",
            "value": "0600",
            "enforced": is_owner_only(path, is_windows=is_windows),
        }
    return {
        "scheme": "windows-acl",
        "value": "owner-only-acl",
        "enforced": is_owner_only(path, is_windows=is_windows),
    }


def _windows(override: bool | None) -> bool:
    return _IS_WINDOWS if override is None else override


#: A Windows SID. Scanned for anywhere on the line rather than parsed by column: the first line of
#: `icacls` output also carries the file path, the ACE description is localized, and the layout
#: differs between Windows versions. The SID text and the (F)/(M)/(R) masks are the stable parts.
_SID = re.compile(r"\bS-1-[0-9-]+", re.IGNORECASE)


def _granted_principals(icacls_output: str) -> list[str]:
    """SIDs granted access in ``icacls`` output."""

    return [match.group(0) for line in icacls_output.splitlines() for match in _SID.finditer(line)]


def _icacls(command: list[str]) -> subprocess.CompletedProcess[str] | None:
    """Run a Windows security tool, or return None when the host does not have it.

    A read-only predicate must not raise FileNotFoundError just because it was asked about a file on
    a host without `icacls`. "Cannot confirm owner-only" is the safe answer for a check; the WRITE
    path turns the same None into a ProtectionError, because silently not protecting a secret is not.
    """

    try:
        return run_text(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    except OSError:
        return None


@lru_cache(maxsize=1)
def _current_user_sid() -> str | None:
    result = _icacls(["whoami", "/user", "/fo", "csv", "/nh"])
    if result is None or result.returncode != 0:
        return None
    for field in reversed((result.stdout or "").strip().split(",")):
        candidate = field.strip().strip('"')
        if candidate.upper().startswith("S-1-"):
            return candidate
    return None
