from __future__ import annotations

import stat
import subprocess
from pathlib import Path

import pytest

from verifysignal_spec.security import file_protection
from verifysignal_spec.security.file_protection import (
    ProtectionError,
    describe_protection,
    harden_owner_only,
    is_owner_only,
)

# The CLI writes bearer secrets to disk: the entitlement receipt, the durable refresh credential
# that mints receipts, and the test environment file. All three were protected with chmod(0o600),
# which on Windows honours only the read-only bit — the call succeeded and protected nothing.


def test_posix_protection_is_the_chmod_it_always_was(tmp_path: Path) -> None:
    secret = tmp_path / "receipt.json"
    secret.write_text("{}", encoding="utf-8")
    secret.chmod(0o644)

    assert is_owner_only(secret, is_windows=False) is False

    harden_owner_only(secret, is_windows=False)

    assert stat.S_IMODE(secret.stat().st_mode) == 0o600
    assert is_owner_only(secret, is_windows=False) is True


def test_describe_protection_reads_the_file_instead_of_asserting(tmp_path: Path) -> None:
    # The old payload said "permissions": "0600" unconditionally — even when the write had failed on
    # a different path, and even on a host where the number is meaningless.
    secret = tmp_path / "env"
    secret.write_text("K=\n", encoding="utf-8")
    secret.chmod(0o644)

    loose = describe_protection(secret, is_windows=False)
    assert loose == {"scheme": "posix-mode", "value": "0600", "enforced": False}

    harden_owner_only(secret, is_windows=False)
    assert describe_protection(secret, is_windows=False)["enforced"] is True

    # On Windows the descriptor names the mechanism that host actually enforces, rather than quoting
    # a POSIX mode number that means nothing there.
    assert describe_protection(secret, is_windows=True)["scheme"] == "windows-acl"


def test_windows_protection_grants_by_sid_and_breaks_inheritance(tmp_path: Path, monkeypatch) -> None:
    secret = tmp_path / "receipt.json"
    secret.write_text("{}", encoding="utf-8")
    calls: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        if command[0] == "whoami":
            return subprocess.CompletedProcess(command, 0, '"HOST\\\\user","S-1-5-21-1-2-3-1001"\n', "")
        return subprocess.CompletedProcess(command, 0, "processed file: 1\n", "")

    monkeypatch.setattr(file_protection, "run_text", fake_run)
    file_protection._current_user_sid.cache_clear()

    harden_owner_only(secret, is_windows=True)

    icacls = next(call for call in calls if call[0] == "icacls")
    # /inheritance:r is load-bearing: without it the parent's inherited "Users: Read" ACE survives
    # and the hardening is theatre.
    assert "/inheritance:r" in icacls
    # By SID, never by name — `Users`, `Utilisateurs` and `Benutzer` are the same group, and a
    # name-based rule silently fails on a localized install.
    assert "*S-1-5-21-1-2-3-1001:F" in icacls


def test_windows_protection_fails_loudly_rather_than_silently(tmp_path: Path, monkeypatch) -> None:
    secret = tmp_path / "receipt.json"
    secret.write_text("{}", encoding="utf-8")

    def failing_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if command[0] == "whoami":
            return subprocess.CompletedProcess(command, 0, '"HOST\\\\user","S-1-5-21-9"\n', "")
        return subprocess.CompletedProcess(command, 1, "Access is denied.\n", "")

    monkeypatch.setattr(file_protection, "run_text", failing_run)
    file_protection._current_user_sid.cache_clear()

    # A secret whose protection could not be applied must raise, never be reported as protected.
    # ProtectionError subclasses OSError so the credential command's existing handler still catches
    # it and returns a structured blocker instead of crashing.
    with pytest.raises(ProtectionError):
        harden_owner_only(secret, is_windows=True)
    assert issubclass(ProtectionError, OSError)


def test_windows_acl_parsing_ignores_localized_prose(tmp_path: Path, monkeypatch) -> None:
    secret = tmp_path / "receipt.json"
    secret.write_text("{}", encoding="utf-8")

    # Real icacls output, with a localized description and SYSTEM present. The ACE text differs per
    # install language; the SID column and the (F) mask do not, which is why only SIDs are parsed.
    owner_only = (
        "receipt.json S-1-5-21-1-2-3-1001:(F)\n"
        "             S-1-5-18:(F)\n"
        "\nAlgumas arquivos processados com xito\n"
    )
    shared = owner_only.replace("S-1-5-18:(F)", "S-1-5-32-545:(RX)")

    def reader(output: str):
        def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
            if command[0] == "whoami":
                return subprocess.CompletedProcess(command, 0, '"HOST\\\\user","S-1-5-21-1-2-3-1001"\n', "")
            return subprocess.CompletedProcess(command, 0, output, "")

        return fake_run

    monkeypatch.setattr(file_protection, "run_text", reader(owner_only))
    file_protection._current_user_sid.cache_clear()
    assert is_owner_only(secret, is_windows=True) is True

    # BUILTIN\Users (S-1-5-32-545) reading the file is exactly what /inheritance:r removes.
    monkeypatch.setattr(file_protection, "run_text", reader(shared))
    file_protection._current_user_sid.cache_clear()
    assert is_owner_only(secret, is_windows=True) is False
