from __future__ import annotations

import re
from pathlib import Path

# RATCHET (cross-repo reachability). Sibling repos used to be reached by hardcoded relative paths
# carrying a hardcoded DIRECTORY NAME. A directory name is a local checkout detail: the backend is
# `verifysignal-be` on one machine and `verifysignal-website` on another, and Core is `verifysignal`
# in CI and `verifysignal-core` in a fresh clone.
#
# Nothing failed when the name did not match. test_real_core_artifact_install.py built its path by
# joining a literal Core directory name onto the parent, so on any checkout that called Core
# something else it found no artifact and skipped CLEANLY — indistinguishable from "there is nothing
# to check", while the packaged-layout divergence it guards went unverified. The same shape in the
# sibling repos silently disabled the cross-repo golden and receipt-envelope checks.
#
# Everything now resolves through src/verifysignal_spec/repos.py, by IDENTITY. This guard keeps it that
# way, and matches the guards in the Core and BE repos. `specs/` is exempt: those are dated
# historical records of what was decided at the time, not instructions anyone follows today.

ROOT = Path(__file__).resolve().parents[2]
SCANNED_SUFFIXES = {".py", ".md", ".yml", ".yaml", ".json", ".toml", ".ts", ".mjs"}
SKIPPED_DIRECTORIES = {
    ".git",
    ".venv",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    "specs",
    ".pytest_cache",
}
EXEMPT_FILES = {
    # The resolver itself: the alias lists are the one place that legitimately knows these names.
    "src/verifysignal_spec/repos.py",
    "tests/contract/test_sibling_repo_paths.py",
}

# Only whole repo names count, so intra-repo paths such as `apps/verifysignal-cli` stay out of it.
_REPO_NAME = r"(?:verifysignal|verifysignal-be|verifysignal-core|verifysignal-spec|verifysignal-website)(?![a-z-])"

OFFENDING_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("relative path to a named sibling", re.compile(rf"\.\.[\\/]{_REPO_NAME}")),
    ("python parent-join to a named sibling", re.compile(rf'\.parent\s*/\s*"{_REPO_NAME}"')),
    (
        "path-join to a named sibling above the repo",
        re.compile(rf'(?:join|resolve)\([^)]*\.\.[^)]*["\']{_REPO_NAME}["\']'),
    ),
]


def _scanned_files() -> list[Path]:
    files: list[Path] = []
    stack = [ROOT]
    while stack:
        current = stack.pop()
        for entry in current.iterdir():
            if entry.is_dir():
                if entry.name in SKIPPED_DIRECTORIES:
                    continue
                stack.append(entry)
                continue
            if entry.suffix in SCANNED_SUFFIXES:
                files.append(entry)
    return files


def test_scan_covers_a_meaningful_slice_of_the_repo() -> None:
    # Anti-vacuity: a broken walker would report zero offenders forever.
    assert len(_scanned_files()) > 50


def test_no_hardcoded_path_to_a_sibling_repo_outside_the_resolver() -> None:
    offenders: list[str] = []
    for path in _scanned_files():
        relative = path.relative_to(ROOT).as_posix()
        if relative in EXEMPT_FILES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for label, pattern in OFFENDING_PATTERNS:
            match = pattern.search(text)
            if match:
                offenders.append(f"{relative}: {label} -> {match.group(0)}")
    assert offenders == [], (
        f"use resolve_sibling_repo() from src/verifysignal_spec/repos.py: {offenders}"
    )


def test_cross_repo_checks_still_route_through_the_resolver() -> None:
    # The opposite direction: removing the hardcoded path must not become "delete the cross-repo leg".
    install = (ROOT / "tests/integration/test_real_core_artifact_install.py").read_text(encoding="utf-8")
    assert "resolve_sibling_repo" in install
    ci_script = (ROOT / "scripts/ci/install_real_artifact.py").read_text(encoding="utf-8")
    assert "resolve_sibling_repo" in ci_script
