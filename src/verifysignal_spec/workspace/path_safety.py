"""Fail-closed checks for project-owned authority paths."""

from __future__ import annotations

import os
import stat
from pathlib import Path

__all__ = [
    "ensure_no_casefold_sibling_collision",
    "ensure_unredirected_project_path",
]


def ensure_no_casefold_sibling_collision(
    path: Path,
    *,
    authority: str,
) -> Path:
    """Reject a sibling whose filename differs only by case.

    A workspace created on a case-sensitive filesystem can otherwise contain
    two authorities that collapse to one pathname on default Windows volumes.
    Enumerating the parent also catches a differently-cased existing name on a
    case-insensitive host before a write silently selects and replaces it.
    """

    candidate = Path(path)
    try:
        siblings = tuple(candidate.parent.iterdir())
    except FileNotFoundError:
        # A parent that does not exist has no sibling namespace to collide in.
        return candidate
    except OSError as exc:
        raise ValueError(
            f"{authority} sibling names cannot be verified safely."
        ) from exc

    folded_name = candidate.name.casefold()
    if any(
        sibling.name != candidate.name
        and sibling.name.casefold() == folded_name
        for sibling in siblings
    ):
        raise ValueError(
            f"{authority} filename has a case-insensitive sibling collision "
            "and is not portable across supported filesystems."
        )
    return candidate


def ensure_unredirected_project_path(
    project: Path,
    path: Path,
    *,
    authority: str,
) -> Path:
    """Reject authority paths redirected by an in-project filesystem link.

    The project itself is the trusted anchor: callers normally pass a resolved
    project root, and only components below that anchor are inspected.  This
    preserves repositories reached through a user-selected symlink while
    preventing a managed workspace directory or authority file from escaping
    that repository.

    Windows directory junctions and other reparse points are links for this
    purpose even when ``Path.is_symlink()`` reports false.
    """

    project_root = _lexical_absolute(project)
    candidate = _lexical_absolute(path)
    try:
        relative = candidate.relative_to(project_root)
    except ValueError as exc:
        raise ValueError(f"{authority} path is outside the project.") from exc

    current = project_root
    for component in relative.parts:
        current = current / component
        try:
            metadata = os.lstat(current)
        except FileNotFoundError:
            # A deeper component cannot exist until this one is created.
            break
        except OSError as exc:
            raise ValueError(f"{authority} path cannot be verified safely.") from exc
        if stat.S_ISLNK(metadata.st_mode) or _is_windows_reparse_point(
            current,
            metadata,
        ):
            raise ValueError(
                f"{authority} path contains an unsafe symbolic-link or "
                "Windows reparse-point component."
            )
    return candidate


def _lexical_absolute(path: Path) -> Path:
    """Normalize ``.``/``..`` without resolving filesystem links."""

    return Path(os.path.abspath(os.fspath(path)))


def _is_windows_reparse_point(path: Path, metadata: os.stat_result) -> bool:
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    attributes = getattr(metadata, "st_file_attributes", 0)
    if reparse_flag and attributes & reparse_flag:
        return True

    # ``Path.is_junction`` was added in Python 3.12. Keep the attribute check
    # above for Python 3.11 and use the explicit API when it is available.
    is_junction = getattr(path, "is_junction", None)
    if not callable(is_junction):
        return False
    try:
        return bool(is_junction())
    except OSError as exc:
        raise ValueError(
            "Authority path junction status cannot be verified safely."
        ) from exc
