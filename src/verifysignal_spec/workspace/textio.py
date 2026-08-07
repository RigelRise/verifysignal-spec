"""LF-pinned text writes for content whose bytes we also hash."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

# Python's text mode translates "\n" to os.linesep on write, so on Windows a file written from an
# LF string lands on disk as CRLF. That is invisible until the same content is HASHED, which this
# codebase does in three places:
#
#   * integrations/manifests.py hashes the rendered string, writes the file, and later re-reads its
#     BYTES to decide whether the user edited it. With translation, current != stored on the very
#     first re-read, so every managed integration file is classified as user-modified forever: never
#     refreshed, never removed on uninstall. `init` is silently non-idempotent.
#   * commands/repair.py reports an `after` hash taken from the LF string while writing CRLF bytes,
#     so the reported hash does not describe the file it names.
#   * workspace/repository.py writes every workspace document through a text-mode handle.
#
# Pinning the WRITE (rather than normalizing at hash time) keeps the hash a hash of the file, which
# is the property the change detection depends on. It also means a workspace produced on Windows and
# one produced on macOS are byte-identical.

__all__ = [
    "write_text_lf",
    "atomic_write_text_lf",
    "durable_atomic_write_text_lf",
    "durable_create_text_lf",
]


def write_text_lf(path: Path, text: str) -> None:
    """Write ``text`` as UTF-8 with LF endings, whatever the host's convention is."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def atomic_write_text_lf(path: Path, text: str) -> None:
    """``write_text_lf`` via a temp file in the same directory, then an atomic replace.

    Same-directory temp file so the replace stays on one filesystem and is therefore atomic.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        Path(tmp).replace(path)
    finally:
        tmp_path = Path(tmp)
        if tmp_path.exists():
            tmp_path.unlink()


def durable_atomic_write_text_lf(path: Path, text: str) -> None:
    """Atomically replace text and durably order file plus directory metadata."""

    created_directories = _missing_directories(path.parent)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        _durable_replace(Path(tmp), path)
        if os.name != "nt":
            for directory in created_directories:
                _fsync_directory(directory.parent)
    finally:
        tmp_path = Path(tmp)
        if tmp_path.exists():
            tmp_path.unlink()


def durable_create_text_lf(path: Path, text: str) -> None:
    """Durably create immutable text without replacing an existing identity."""

    created_directories = _missing_directories(path.parent)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    tmp_path = Path(tmp)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        if os.name == "nt":
            _windows_write_through_move_new(tmp_path, path)
        else:
            os.link(tmp_path, path, follow_symlinks=False)
            tmp_path.unlink()
            _fsync_directory(path.parent)
        if os.name != "nt":
            for directory in created_directories:
                _fsync_directory(directory.parent)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def _durable_replace(source: Path, target: Path) -> None:
    if os.name == "nt":
        _windows_write_through_replace(source, target)
        return
    os.replace(source, target)
    _fsync_directory(target.parent)


def _fsync_directory(directory: Path) -> None:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    directory_fd = os.open(directory, flags)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _missing_directories(directory: Path) -> list[Path]:
    """Return missing directories from leaf upward before ``mkdir -p``."""

    missing: list[Path] = []
    current = directory
    while True:
        try:
            current.lstat()
            return missing
        except FileNotFoundError:
            missing.append(current)
        parent = current.parent
        if parent == current:
            raise OSError(f"No existing ancestor for durable path: {directory}")
        current = parent


def _windows_write_through_replace(source: Path, target: Path) -> None:
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    move_file = kernel32.MoveFileExW
    move_file.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD]
    move_file.restype = wintypes.BOOL
    replace_existing = 0x00000001
    write_through = 0x00000008
    if not move_file(
        str(source),
        str(target),
        replace_existing | write_through,
    ):
        raise OSError(ctypes.get_last_error(), "Durable file replacement failed")


def _windows_write_through_move_new(source: Path, target: Path) -> None:
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    move_file = kernel32.MoveFileExW
    move_file.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD]
    move_file.restype = wintypes.BOOL
    write_through = 0x00000008
    if move_file(str(source), str(target), write_through):
        return
    error = ctypes.get_last_error()
    if error in {80, 183}:  # ERROR_FILE_EXISTS | ERROR_ALREADY_EXISTS
        raise FileExistsError(error, "Durable file already exists", str(target))
    raise OSError(error, "Durable file creation failed")
