"""Resolve sibling VerifySignal repositories by identity instead of by directory name.

THE DRIFT THIS EXISTS TO CATCH. Every cross-repo reference used to be a hardcoded relative path
with a hardcoded DIRECTORY NAME (``../verifysignal``, ``../verifysignal-be``). Those names are a
local checkout detail, not an identity: one machine clones the backend as ``verifysignal-be``,
another as ``verifysignal-website``, and Core itself is ``verifysignal`` in one place and
``verifysignal-core`` in another. The cross-repo checks degrade to a warning or a skip when a
sibling does not resolve, so a mismatched directory name did not fail — it silently turned the
check off, which is exactly the drift those checks were written to catch.

Repos are resolved by IDENTITY (the package/project name they declare) or by an explicit env
override. Directory names are never consulted. ``SIBLING_IDENTITY`` below is the ONLY place that
knows what a repo has ever been called; today's published names are still the legacy ones.

This lives in the shipped package rather than under ``scripts/`` because the runtime resolver's
"local Core development checkout" step (see ``docs/installation.md``, resolution order step 5) needs
it at run time, not only in tests and CI.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

Role = str  # "core" | "spec" | "backend"

_PYPROJECT_NAME = re.compile(r'^\s*name\s*=\s*"([^"]+)"', re.MULTILINE)


@dataclass(frozen=True)
class Identity:
    #: Accepted ``name`` values, across renames. Matching any one of these identifies the repo.
    names: tuple[str, ...]
    #: Manifest that declares the name, relative to the repo root.
    manifest: str
    #: Env var that pins this repo explicitly, bypassing the scan.
    env: str


SIBLING_IDENTITY: dict[Role, Identity] = {
    "core": Identity(("verifysignal", "verifysignal-core"), "package.json", "VERIFYSIGNAL_CORE_DIR"),
    "spec": Identity(("verifysignal-spec",), "pyproject.toml", "VERIFYSIGNAL_SPEC_DIR"),
    "backend": Identity(
        ("verifysignal-be", "verifysignal-website"), "package.json", "VERIFYSIGNAL_BACKEND_DIR"
    ),
}


def find_repo_root(start: Path | None = None) -> Path:
    """Nearest ancestor of ``start`` holding a package manifest."""
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "package.json").exists() or (candidate / "pyproject.toml").exists():
            return candidate
    return current


def _declared_name(repo_dir: Path, manifest: str) -> str | None:
    path = repo_dir / manifest
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    if manifest == "package.json":
        try:
            name = json.loads(text).get("name")
        except (json.JSONDecodeError, AttributeError):
            return None
        return name if isinstance(name, str) else None
    match = _PYPROJECT_NAME.search(text)
    return match.group(1) if match else None


def _identifies(repo_dir: Path, identity: Identity) -> bool:
    return _declared_name(repo_dir, identity.manifest) in identity.names


def resolve_sibling_repo(role: Role, from_repo_root: Path | None = None) -> Path | None:
    """Absolute path to a sibling repo, or ``None`` when it is not present.

    An env override that is set but wrong raises instead of falling back: someone who pins a path is
    stating where the repo is, and silently scanning past their mistake would reintroduce exactly the
    "green but checked nothing" failure this module exists to prevent.
    """
    identity = SIBLING_IDENTITY[role]
    root = (from_repo_root or find_repo_root()).resolve()

    override = (os.environ.get(identity.env) or "").strip()
    if override:
        path = Path(override).resolve()
        if not path.exists():
            raise ValueError(f"{identity.env}={override} does not exist (resolved to {path})")
        if not _identifies(path, identity):
            raise ValueError(
                f"{identity.env}={override} is not the {role} repo: {identity.manifest} must "
                f"declare one of {', '.join(identity.names)}"
            )
        return path

    if _identifies(root, identity):
        return root

    try:
        entries = sorted(root.parent.iterdir())
    except OSError:
        return None
    for candidate in entries:
        if candidate == root or not candidate.is_dir():
            continue
        if _identifies(candidate, identity):
            return candidate
    return None


#: Executable file names a Core runtime can be published under. Unlike a repo directory, a binary IS
#: identified by its name — this is the same lookup ``shutil.which`` performs, one level out.
CORE_EXECUTABLE_NAMES = ("verifysignal", "verifysignal-core")

#: The npm script the adapter invokes for a directory-shaped Core command (see docs/installation.md:
#: "When the value points to a directory with package.json, VerifySignal runs npm ... verifysignal:dev").
CORE_DEV_SCRIPT = "verifysignal:dev"


def _is_core_dev_checkout(repo_dir: Path) -> bool:
    """Whether ``repo_dir`` is a directory the Core adapter can actually run.

    Two ways to qualify, neither of which looks at the directory name: the manifest declares a Core
    identity, or it exposes the dev script the adapter shells out to. The script check is the more
    fundamental of the two — it is what makes the directory *runnable* — and it keeps working for a
    checkout whose package.json has no ``name`` at all.
    """
    if _identifies(repo_dir, SIBLING_IDENTITY["core"]):
        return True
    try:
        manifest = json.loads((repo_dir / "package.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    scripts = manifest.get("scripts") if isinstance(manifest, dict) else None
    return isinstance(scripts, dict) and CORE_DEV_SCRIPT in scripts


def ancestor_core_candidates(project: Path) -> list[Path]:
    """Core commands sitting beside ``project`` or beside one of its ancestors.

    Two shapes are accepted, matching what the resolution order documents (see
    ``docs/installation.md``, step 5) and what the previous implementation happened to allow:

    * a **development checkout** — a directory confirmed by manifest identity or by the dev script
      the adapter runs, so it is found whether it is called ``verifysignal`` or ``verifysignal-core``.
      The old code joined the literal name ``verifysignal``, so this step quietly never fired on a
      checkout named anything else.
    * an **executable file** named after the Core binary. A binary is legitimately identified by its
      name, and dropping this would break the "a runtime next to your project" case.
    """
    start = project.resolve()
    found: list[Path] = []
    seen: set[Path] = set()
    for node in [start, *start.parents]:
        parent = node.parent
        try:
            entries = sorted(parent.iterdir())
        except OSError:
            continue
        for candidate in entries:
            # The old lookup was one stat per ancestor level; this lists each level instead, so keep
            # the per-entry work cheap and skip what can never be a checkout.
            if candidate.name.startswith(".") or candidate.name == "node_modules":
                continue
            resolved = candidate.resolve()
            if resolved == start or resolved in seen:
                continue
            seen.add(resolved)
            if candidate.is_dir():
                if _is_core_dev_checkout(resolved):
                    found.append(resolved)
            elif candidate.name in CORE_EXECUTABLE_NAMES:
                found.append(resolved)
    return found


def require_sibling_repo(role: Role, from_repo_root: Path | None = None) -> Path:
    """Same as :func:`resolve_sibling_repo`, for callers that treat a missing sibling as fatal."""
    path = resolve_sibling_repo(role, from_repo_root)
    if path is None:
        identity = SIBLING_IDENTITY[role]
        root = (from_repo_root or find_repo_root()).resolve()
        raise ValueError(
            f"{role} repo not found next to {root}; set {identity.env} to its checkout path"
        )
    return path
