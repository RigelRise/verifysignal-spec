from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from verifysignal_spec.runtime.env_file import (
    EnvironmentFileError,
    declared_environment_keys,
    parse_environment_text,
)
from verifysignal_spec.workspace.repository import load_use_case


SCHEMA = "verifysignal-spec-credential-preparation/v1"


def prepare(project: Path, alias: str, *, env_file: Path) -> dict[str, Any]:
    project = project.resolve()
    record = load_use_case(project, alias)
    declared = sorted(declared_environment_keys(record))
    target = env_file if env_file.is_absolute() else project / env_file
    target = target.resolve()
    try:
        relative = target.relative_to(project).as_posix()
    except ValueError:
        return _blocked(
            alias,
            str(env_file),
            "credentials.env-file-outside-project",
            "Credential preparation requires a project-local environment file.",
            declared,
        )
    try:
        exclude_path = _git_exclude_path(project)
        _ensure_exact_exclusion(exclude_path, relative)
        _verify_git_exclusion(project, relative)
    except (OSError, EnvironmentFileError, subprocess.SubprocessError) as exc:
        return _blocked(
            alias,
            relative,
            exc.code if isinstance(exc, EnvironmentFileError) else "credentials.git-exclusion-unavailable",
            exc.message
            if isinstance(exc, EnvironmentFileError)
            else "Git exclusion could not be guaranteed before preparing the test environment file.",
            declared,
        )

    existing_text = ""
    preserved: list[str] = []
    if target.exists():
        try:
            existing_text = target.read_text(encoding="utf-8")
            preserved = sorted(
                parse_environment_text(existing_text, allowed_keys=declared)
            )
        except (OSError, EnvironmentFileError) as exc:
            return _blocked(
                alias,
                relative,
                exc.code if isinstance(exc, EnvironmentFileError) else "credentials.env-file-unreadable",
                exc.message
                if isinstance(exc, EnvironmentFileError)
                else "The existing test environment file could not be read safely.",
                declared,
            )
    appended = [key for key in declared if key not in set(preserved)]
    content = existing_text
    if content and not content.endswith("\n"):
        content += "\n"
    content += "".join(f"{key}=\n" for key in appended)
    try:
        _atomic_owner_only_write(target, content)
    except OSError:
        return _blocked(
            alias,
            relative,
            "credentials.env-file-secure-write-failed",
            "The test environment file could not be written with owner-only permissions.",
            declared,
        )
    return {
        "schemaVersion": SCHEMA,
        "status": "prepared" if appended or not preserved else "unchanged",
        "alias": alias,
        "envFile": relative,
        "declaredKeys": declared,
        "appendedKeys": appended,
        "preservedKeys": preserved,
        "gitExcluded": True,
        "permissions": "0600",
        "valuesIncluded": False,
        "blockers": [],
    }


def _git_exclude_path(project: Path) -> Path:
    proc = subprocess.run(
        ["git", "-C", str(project), "rev-parse", "--git-path", "info/exclude"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        raise EnvironmentFileError(
            "credentials.git-exclusion-unavailable",
            "Credential preparation requires a Git repository with a writable info/exclude file.",
        )
    path = Path(proc.stdout.strip())
    return path if path.is_absolute() else (project / path).resolve()


def _ensure_exact_exclusion(path: Path, relative: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    if relative in existing.splitlines():
        return
    updated = existing
    if updated and not updated.endswith("\n"):
        updated += "\n"
    path.write_text(updated + f"{relative}\n", encoding="utf-8")


def _verify_git_exclusion(project: Path, relative: str) -> None:
    proc = subprocess.run(
        ["git", "-C", str(project), "check-ignore", "-q", "--no-index", relative],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        raise EnvironmentFileError(
            "credentials.git-exclusion-unavailable",
            "The exact test environment path is not excluded by Git.",
        )


def _atomic_owner_only_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp_path = Path(temporary)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
        temp_path.replace(path)
        path.chmod(0o600)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _blocked(
    alias: str,
    env_file: str,
    code: str,
    message: str,
    declared: list[str],
) -> dict[str, Any]:
    return {
        "schemaVersion": SCHEMA,
        "status": "blocked",
        "alias": alias,
        "envFile": env_file,
        "declaredKeys": declared,
        "appendedKeys": [],
        "preservedKeys": [],
        "gitExcluded": False,
        "permissions": "not-written",
        "valuesIncluded": False,
        "blockers": [
            {
                "code": code,
                "severity": "blocker",
                "category": "credentials",
                "message": message,
            }
        ],
    }
