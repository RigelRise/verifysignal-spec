"""Subprocess helpers with the decoding and lookup rules Windows actually needs.

Three defects this exists to make unrepeatable, all of them invisible on POSIX:

**Decoding.** ``subprocess.run(..., text=True)`` with no ``encoding`` decodes with
``locale.getencoding()`` — cp1252 on most Windows installs. Core emits UTF-8 JSON, so a single
accented character in a page title, a selector or an error message either raises
``UnicodeDecodeError`` mid-run or mojibakes into ``json.loads``. The correct incantation is two
keyword arguments, not one, and repeating a two-part rule at six call sites is how the seventh gets
it wrong.

**Console flashes.** On Windows a GUI-hosted agent spawning a console subprocess pops a window each
time unless ``CREATE_NO_WINDOW`` is set.

**Tool lookup.** ``shutil.which`` applies PATHEXT and will find ``npm.cmd``, but ``CreateProcess``
cannot execute a ``.cmd`` from an argv vector — it needs ``cmd.exe``. A bare ``"npm"`` therefore
resolves and then fails to launch.

``errors="replace"`` is deliberate: a stray byte in a subprocess's output must never take down the
CLI mid-run. Losing one character is recoverable; losing the run is not.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from typing import Any

__all__ = ["run_text", "popen_text", "resolve_tool", "split_command", "join_command", "configure_stdio"]

_IS_WINDOWS = os.name == "nt"

#: Suffixes that need cmd.exe rather than a direct CreateProcess call.
_SHIM_SUFFIXES = (".cmd", ".bat")


def _text_kwargs(overrides: dict[str, Any]) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"encoding": "utf-8", "errors": "replace", **overrides}
    if _IS_WINDOWS:
        creationflags = kwargs.get("creationflags", 0)
        kwargs["creationflags"] = creationflags | getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return kwargs


def run_text(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    """``subprocess.run`` that always decodes as UTF-8, whatever the host locale is."""

    return subprocess.run(command, **_text_kwargs(kwargs))


def popen_text(command: list[str], **kwargs: Any) -> subprocess.Popen[str]:
    """``subprocess.Popen`` with the same decoding rules as :func:`run_text`."""

    return subprocess.Popen(command, **_text_kwargs(kwargs))


def resolve_tool(name: str, *, is_windows: bool | None = None) -> list[str] | None:
    """Argv prefix that actually launches ``name``, or ``None`` when it is not installed.

    On POSIX this is ``shutil.which``. On Windows the resolved path may be a ``.cmd``/``.bat`` shim
    — npm ships one for every binary it installs — and ``CreateProcess`` cannot execute those from an
    argv vector, so the shim is wrapped in ``cmd.exe /d /s /c``.

    ``is_windows`` is injectable so the Windows branch is testable from a POSIX host, the same seam
    ``normalize_platform(system=, machine=)`` already uses.
    """

    resolved = shutil.which(name)
    if not resolved:
        return None
    windows = _IS_WINDOWS if is_windows is None else is_windows
    if windows and resolved.lower().endswith(_SHIM_SUFFIXES):
        return [os.environ.get("COMSPEC") or "cmd.exe", "/d", "/s", "/c", resolved]
    return [resolved]


def split_command(raw: str, *, is_windows: bool | None = None) -> list[str]:
    """Split a persisted command string into argv.

    ``shlex.split`` runs in POSIX mode, where a backslash is an ESCAPE character: it turns
    ``C:\\Tools\\core.exe --flag`` into ``C:Toolscore.exe``, silently eating every separator in a
    Windows path. Windows quoting is handled by ``posix=False`` plus a quote strip, which is the
    closest stdlib equivalent to how ``CreateProcess`` parses a command line.
    """

    windows = _IS_WINDOWS if is_windows is None else is_windows
    if not windows:
        return shlex.split(raw)
    return [part.strip('"') for part in shlex.split(raw, posix=False)]


def join_command(parts: list[str], *, is_windows: bool | None = None) -> str:
    """Inverse of :func:`split_command`, for a command we persist and later re-parse."""

    windows = _IS_WINDOWS if is_windows is None else is_windows
    return subprocess.list2cmdline(parts) if windows else shlex.join(parts)


def configure_stdio() -> None:
    """Force UTF-8 on our own stdout/stderr when they are redirected.

    Python's Windows *console* IO is UTF-16 backed and fine. A REDIRECTED stream falls back to the
    locale encoding, so `verifysignal list > out.txt` raises UnicodeEncodeError on the status icons
    the CLI prints — and agents pipe `--json` output constantly.
    """

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):  # pragma: no cover - a stream that refuses is not fatal
            continue
