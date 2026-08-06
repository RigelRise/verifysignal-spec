from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from verifysignal_spec.commands import run_request_preparation as preparation


def _read_windows_file_with_core_compatible_sharing(path: Path) -> bytes:
    """Read through the same Windows share-mode contract used by Node/libuv."""
    import ctypes
    import msvcrt
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    create_file.restype = wintypes.HANDLE
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [wintypes.HANDLE]
    close_handle.restype = wintypes.BOOL

    generic_read = 0x80000000
    share_read_write_delete = 0x00000001 | 0x00000002 | 0x00000004
    open_existing = 3
    file_attribute_normal = 0x00000080
    handle = create_file(
        str(path),
        generic_read,
        share_read_write_delete,
        None,
        open_existing,
        file_attribute_normal,
        None,
    )
    invalid_handle_value = wintypes.HANDLE(-1).value
    if handle in {None, invalid_handle_value}:
        raise ctypes.WinError(ctypes.get_last_error())

    numeric_handle = int(handle)
    try:
        descriptor = msvcrt.open_osfhandle(
            numeric_handle,
            os.O_RDONLY | getattr(os, "O_BINARY", 0),
        )
    except OSError:
        close_handle(wintypes.HANDLE(numeric_handle))
        raise

    chunks: list[bytes] = []
    try:
        while chunk := os.read(descriptor, 8192):
            chunks.append(chunk)
    finally:
        os.close(descriptor)
    return b"".join(chunks)


@pytest.mark.skipif(os.name != "nt", reason="Native Windows handle semantics")
def test_windows_native_handle_create_read_and_cleanup(tmp_path: Path) -> None:
    output_dir = tmp_path / ".verifysignal" / "runs" / "localized-home"

    ownership = preparation.write_owned_prepared_run_request(
        tmp_path,
        output_dir,
        "attempt",
        {"safe": True},
    )

    try:
        assert ownership.createdByThisInvocation is True
        assert ownership.cleanupMode == "windows-handle"
        assert ownership.fileFd is not None
        assert ownership.windowsDirectoryHandles
        # Node/libuv shares read, write, and delete access for ordinary file reads.
        # Match that Core contract while Spec retains DELETE ownership of the file.
        assert _read_windows_file_with_core_compatible_sharing(ownership.path) == (
            b'{\n  "safe": true\n}\n'
        )
        removed = preparation.cleanup_owned_prepared_run_request(
            tmp_path,
            ownership,
        )
    finally:
        preparation.release_prepared_run_request_ownership(ownership)

    assert removed is True
    assert ownership.fileFd is None
    assert ownership.windowsDirectoryHandles == ()
    assert ownership.path.exists() is False


def test_missing_posix_primitives_dispatch_to_the_windows_anchored_writer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[Path, Path, str]] = []

    def windows_writer(
        project_root: Path,
        output_dir: Path,
        filename: str,
        document: dict[str, object],
    ):
        calls.append((project_root, output_dir, filename))
        output_dir.mkdir(parents=True)
        path = output_dir / filename
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.write(descriptor, (json.dumps(document) + "\n").encode("utf-8"))
        return (
            path,
            os.fstat(descriptor),
            None,
            descriptor,
            "windows-handle",
            (),
        )

    monkeypatch.setattr(preparation, "_supports_anchored_file_operations", lambda: False)
    monkeypatch.setattr(preparation, "_write_windows_anchored_exclusive", windows_writer)
    output_dir = tmp_path / ".verifysignal" / "runs" / "alias"

    ownership = preparation.write_owned_prepared_run_request(
        tmp_path,
        output_dir,
        "attempt",
        {"safe": True},
    )

    assert calls == [(tmp_path.resolve(), output_dir, "attempt.run-request.json")]
    assert ownership.createdByThisInvocation is True
    assert ownership.cleanupMode == "windows-handle"
    assert ownership.fileFd is not None
    descriptor = ownership.fileFd

    preparation.release_prepared_run_request_ownership(ownership)

    assert ownership.fileFd is None
    with pytest.raises(OSError):
        os.fstat(descriptor)
    assert ownership.path.read_text(encoding="utf-8") == '{"safe": true}\n'


def test_unsupported_anchored_writers_fail_closed_without_creating_a_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(preparation, "_supports_anchored_file_operations", lambda: False)
    monkeypatch.setattr(preparation, "_write_windows_anchored_exclusive", lambda *_args: None)
    output_dir = tmp_path / ".verifysignal" / "runs" / "alias"

    ownership = preparation.write_owned_prepared_run_request(
        tmp_path,
        output_dir,
        "attempt",
        {"safe": True},
    )

    assert ownership.createdByThisInvocation is False
    assert output_dir.exists() is False


@pytest.mark.parametrize("error", [80, 183])
def test_windows_existing_file_errors_preserve_exclusive_collision_retry(
    tmp_path: Path,
    error: int,
) -> None:
    with pytest.raises(FileExistsError):
        preparation._raise_windows_create_error(tmp_path / "attempt.json", error)


def test_windows_unexpected_creation_error_remains_an_os_error(tmp_path: Path) -> None:
    with pytest.raises(OSError) as raised:
        preparation._raise_windows_create_error(tmp_path / "attempt.json", 5)

    assert not isinstance(raised.value, FileExistsError)
    assert raised.value.errno == 5


def test_windows_cleanup_uses_the_owned_handle_not_a_replacement_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_dir = tmp_path / ".verifysignal" / "runs" / "alias"
    output_dir.mkdir(parents=True)
    expected = output_dir / "attempt.run-request.json"
    expected.write_text('{"owner":"invocation"}\n', encoding="utf-8")
    detached = output_dir / "detached.run-request.json"
    expected.rename(detached)
    descriptor = os.open(detached, os.O_RDONLY)
    observed = os.fstat(descriptor)
    expected.write_text('{"owner":"replacement"}\n', encoding="utf-8")
    replacement = expected.read_bytes()
    deleted_identities: list[tuple[int, int]] = []

    def delete_exact_handle(file_fd: int) -> bool:
        file_stat = os.fstat(file_fd)
        deleted_identities.append((file_stat.st_dev, file_stat.st_ino))
        return True

    monkeypatch.setattr(preparation, "_delete_windows_file_by_handle", delete_exact_handle)
    ownership = preparation.PreparedRunRequestOwnership(
        path=expected,
        expectedPath=expected,
        createdByThisInvocation=True,
        device=observed.st_dev,
        inode=observed.st_ino,
        fileFd=descriptor,
        cleanupMode="windows-handle",
    )

    assert preparation.cleanup_owned_prepared_run_request(tmp_path, ownership) is True

    assert deleted_identities == [(observed.st_dev, observed.st_ino)]
    assert expected.read_bytes() == replacement
    assert detached.read_text(encoding="utf-8") == '{"owner":"invocation"}\n'
    assert ownership.fileFd is None
