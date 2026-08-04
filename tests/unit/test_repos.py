from __future__ import annotations

import json
from pathlib import Path

import pytest

from verifysignal_spec.repos import (
    CORE_DEV_SCRIPT,
    CORE_EXECUTABLE_NAMES,
    is_core_executable_name,
    SIBLING_IDENTITY,
    ancestor_core_candidates,
    find_repo_root,
    require_sibling_repo,
    resolve_sibling_repo,
)

# Covers the resolver the cross-repo checks and the runtime resolution order depend on. The point of
# the whole module is that a checkout's DIRECTORY NAME must not decide whether a repo is found, so
# every case here names the directory something other than what the repo is conventionally called.


@pytest.fixture(autouse=True)
def _isolate_override_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clear the pin variables so these tests exercise the SCAN, not the ambient environment.

    Without this the module was environment-dependent — the exact defect it exists to prevent. The
    product-truth CI job pins all three repos at job level, so every scan case here silently received
    the real checkout instead of its synthetic fixture and failed. Tests that mean to exercise a pin
    set it themselves.
    """
    for identity in SIBLING_IDENTITY.values():
        monkeypatch.delenv(identity.env, raising=False)


def _repo(parent: Path, dir_name: str, name: str, manifest: str = "package.json") -> Path:
    path = parent / dir_name
    path.mkdir(parents=True)
    if manifest == "package.json":
        (path / manifest).write_text(json.dumps({"name": name}), encoding="utf-8")
    else:
        (path / manifest).write_text(f'[project]\nname = "{name}"\n', encoding="utf-8")
    return path


@pytest.mark.parametrize("alias", SIBLING_IDENTITY["backend"].names)
def test_finds_a_sibling_under_every_name_that_repo_has_published(tmp_path: Path, alias: str) -> None:
    root = tmp_path / alias
    root.mkdir()
    own = _repo(root, "anything", "verifysignal")
    backend = _repo(root, f"checkout-of-{alias}", alias)
    assert resolve_sibling_repo("backend", own) == backend


def test_reads_a_python_sibling_identity_from_pyproject(tmp_path: Path) -> None:
    own = _repo(tmp_path, "core-checkout", "verifysignal")
    spec = _repo(tmp_path, "renamed-spec", "verifysignal-spec", manifest="pyproject.toml")
    assert resolve_sibling_repo("spec", own) == spec


def test_a_directory_named_like_the_backend_is_not_the_backend(tmp_path: Path) -> None:
    own = _repo(tmp_path, "core-checkout", "verifysignal")
    _repo(tmp_path, "verifysignal-be", "something-else")
    assert resolve_sibling_repo("backend", own) is None


def test_explicit_override_wins_over_the_sibling_scan(tmp_path: Path, monkeypatch) -> None:
    own = _repo(tmp_path, "core-checkout", "verifysignal")
    _repo(tmp_path, "nearby", "verifysignal-be")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    pinned = _repo(elsewhere, "pinned", "verifysignal-website")
    monkeypatch.setenv(SIBLING_IDENTITY["backend"].env, str(pinned))
    assert resolve_sibling_repo("backend", own) == pinned


def test_override_to_a_missing_path_raises_instead_of_falling_back(tmp_path: Path, monkeypatch) -> None:
    own = _repo(tmp_path, "core-checkout", "verifysignal")
    _repo(tmp_path, "nearby", "verifysignal-be")
    monkeypatch.setenv(SIBLING_IDENTITY["backend"].env, str(tmp_path / "no-such-directory"))
    # Never a silent fallback: a wrong pin that quietly resolved to nothing is how the cross-repo legs
    # went dark in the first place.
    with pytest.raises(ValueError, match="does not exist"):
        resolve_sibling_repo("backend", own)


def test_override_to_the_wrong_repo_raises(tmp_path: Path, monkeypatch) -> None:
    own = _repo(tmp_path, "core-checkout", "verifysignal")
    spec = _repo(tmp_path, "spec-checkout", "verifysignal-spec", manifest="pyproject.toml")
    monkeypatch.setenv(SIBLING_IDENTITY["backend"].env, str(spec))
    with pytest.raises(ValueError, match="is not the backend repo"):
        resolve_sibling_repo("backend", own)


def test_require_sibling_repo_names_the_override_variable(tmp_path: Path) -> None:
    own = _repo(tmp_path, "core-checkout", "verifysignal")
    with pytest.raises(ValueError, match="VERIFYSIGNAL_BACKEND_DIR"):
        require_sibling_repo("backend", own)


def test_find_repo_root_walks_up_to_the_nearest_manifest(tmp_path: Path) -> None:
    repo = _repo(tmp_path, "core-checkout", "verifysignal")
    nested = repo / "tests" / "unit"
    nested.mkdir(parents=True)
    assert find_repo_root(nested) == repo


# --- ancestor_core_candidates: the documented "local Core development checkout" resolution step ---


def test_ancestor_walk_finds_a_checkout_named_anything(tmp_path: Path) -> None:
    project = tmp_path / "workspace" / "target"
    project.mkdir(parents=True)
    core = _repo(project.parent, "verifysignal-core", "verifysignal")
    # The previous implementation joined the literal name "verifysignal", so this never fired.
    assert core in ancestor_core_candidates(project)


def test_ancestor_walk_accepts_a_checkout_identified_only_by_its_dev_script(tmp_path: Path) -> None:
    project = tmp_path / "workspace" / "target"
    project.mkdir(parents=True)
    core = project.parent / "renamed-core"
    core.mkdir()
    # No `name` at all: what makes a directory a RUNNABLE Core is the script the adapter shells out
    # to, which is also what the test fixtures build.
    (core / "package.json").write_text(json.dumps({"scripts": {CORE_DEV_SCRIPT: "x"}}), encoding="utf-8")
    assert core in ancestor_core_candidates(project)


def test_ancestor_walk_still_accepts_a_bare_executable(tmp_path: Path) -> None:
    project = tmp_path / "workspace" / "target"
    project.mkdir(parents=True)
    binary = project.parent / CORE_EXECUTABLE_NAMES[0]
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    # A binary IS identified by its name; dropping this would break "a runtime next to your project".
    assert binary in ancestor_core_candidates(project)


def test_core_executable_names_cover_the_windows_forms(monkeypatch) -> None:
    # On POSIX an executable carries no extension, so an exact match is the whole rule.
    assert is_core_executable_name("verifysignal")
    assert is_core_executable_name("verifysignal-core")
    assert not is_core_executable_name("verifysignal.exe")

    # On Windows the same runtime is `verifysignal.exe` (pip's console script) or
    # `verifysignal-core.cmd` (an npm shim). The exact-name match found NEITHER, so a Core sitting
    # next to the project was invisible there.
    monkeypatch.setenv("PATHEXT", ".COM;.EXE;.BAT;.CMD")
    assert is_core_executable_name("verifysignal.exe", os_name="nt")
    assert is_core_executable_name("verifysignal-core.cmd", os_name="nt")
    # PATHEXT is case-insensitive on Windows, and npm shims are routinely written `.CMD`.
    assert is_core_executable_name("verifysignal-core.CMD", os_name="nt")

    # A suffix PATHEXT does not list is not executable, so it is not a runtime either. `.ps1` is the
    # one that matters: npm ships one next to every shim and it cannot be launched directly.
    assert not is_core_executable_name("verifysignal.ps1", os_name="nt")
    assert not is_core_executable_name("verifysignal.txt", os_name="nt")
    # A different stem is not a Core runtime whatever its suffix.
    assert not is_core_executable_name("something.exe", os_name="nt")


def test_ancestor_walk_ignores_unrelated_directories(tmp_path: Path) -> None:
    project = tmp_path / "workspace" / "target"
    project.mkdir(parents=True)
    _repo(project.parent, "unrelated", "some-other-package")
    assert ancestor_core_candidates(project) == []
