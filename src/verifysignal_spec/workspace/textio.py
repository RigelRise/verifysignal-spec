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

__all__ = ["write_text_lf", "atomic_write_text_lf"]


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
