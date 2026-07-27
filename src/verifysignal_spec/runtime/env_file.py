from __future__ import annotations

import re
import stat
from pathlib import Path
from typing import Iterable

from verifysignal_spec.workspace.repository import (
    credential_runtime_requirements,
    load_document,
    load_registry,
    load_use_case,
)


KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
ASSIGNMENT_RE = re.compile(
    r"^(?:export[ \t]+)?([A-Za-z_][A-Za-z0-9_]*)[ \t]*=[ \t]*(.*)$"
)


class EnvironmentFileError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def blocker(self) -> dict[str, str]:
        return {
            "code": self.code,
            "severity": "blocker",
            "category": "credentials",
            "message": self.message,
        }


def declared_environment_keys(record: object) -> set[str]:
    keys: set[str] = set()
    for group in credential_runtime_requirements(record):  # type: ignore[arg-type]
        keys.update(str(item) for item in group.get("runtimeNames", []) if item)
    session_ref = getattr(record, "sessionRef", None)
    if isinstance(session_ref, dict) and session_ref.get("source") == "environment":
        if session_ref.get("key"):
            keys.add(str(session_ref["key"]))
    for item in getattr(record, "runtimeInputs", []):
        if getattr(item, "envVar", None):
            keys.add(str(item.envVar))
    return {key for key in keys if KEY_RE.fullmatch(key)}


def declared_environment_keys_for_run_request(
    project: Path,
    run_request: Path,
) -> set[str]:
    resolved = run_request.resolve()
    for entry in load_registry(project).get("useCases", []):
        alias = entry.get("alias") if isinstance(entry, dict) else None
        if not alias:
            continue
        try:
            record = load_use_case(project, str(alias))
        except FileNotFoundError:
            continue
        reference = getattr(record, "runRequest", None)
        if reference and (project / reference.path).resolve() == resolved:
            return declared_environment_keys(record)

    data = load_document(resolved, default={}) or {}
    keys: set[str] = set()
    refs = data.get("credentialRefs") if isinstance(data, dict) else {}
    if isinstance(refs, dict):
        for group in refs.values():
            if not isinstance(group, dict):
                continue
            group_keys = group.get("keys")
            if isinstance(group_keys, dict):
                keys.update(str(value) for value in group_keys.values() if value)
    session = data.get("sessionRef") if isinstance(data, dict) else None
    if isinstance(session, dict) and session.get("source") == "environment" and session.get("key"):
        keys.add(str(session["key"]))
    return {key for key in keys if KEY_RE.fullmatch(key)}


def parse_environment_text(
    text: str,
    *,
    allowed_keys: Iterable[str],
) -> dict[str, str]:
    allowed = set(allowed_keys)
    values: dict[str, str] = {}
    for number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = ASSIGNMENT_RE.fullmatch(line)
        if not match:
            raise EnvironmentFileError(
                "credentials.env-file-invalid-assignment",
                f"Environment file line {number} is not a supported literal assignment.",
            )
        key, raw_value = match.groups()
        if key not in allowed:
            raise EnvironmentFileError(
                "credentials.env-file-undeclared-key",
                f"Environment file key {key} is not declared by this use case.",
            )
        if key in values:
            raise EnvironmentFileError(
                "credentials.env-file-duplicate-key",
                f"Environment file key {key} is assigned more than once.",
            )
        values[key] = _literal_value(raw_value, number)
    return values


def _literal_value(raw_value: str, line_number: int) -> str:
    value = raw_value.strip()
    if "$(" in value or "`" in value:
        raise EnvironmentFileError(
            "credentials.env-file-executable-syntax",
            f"Environment file line {line_number} contains executable syntax.",
        )
    if "${" in value or re.search(r"\$[A-Za-z_]", value):
        raise EnvironmentFileError(
            "credentials.env-file-interpolation",
            f"Environment file line {line_number} contains interpolation.",
        )
    if value.endswith("\\"):
        raise EnvironmentFileError(
            "credentials.env-file-invalid-assignment",
            f"Environment file line {line_number} cannot continue onto another line.",
        )
    if not value:
        return ""
    if value[0] in {"'", '"'}:
        quote = value[0]
        if len(value) < 2 or value[-1] != quote:
            raise EnvironmentFileError(
                "credentials.env-file-invalid-assignment",
                f"Environment file line {line_number} has an unterminated quote.",
            )
        return value[1:-1]
    if value.endswith(("'", '"')):
        raise EnvironmentFileError(
            "credentials.env-file-invalid-assignment",
            f"Environment file line {line_number} has invalid quoting.",
        )
    return value


def load_environment_file(
    path: Path,
    *,
    declared_keys: Iterable[str],
) -> dict[str, str]:
    if not path.exists() or not path.is_file():
        raise EnvironmentFileError(
            "credentials.env-file-missing",
            "The explicitly selected test environment file does not exist.",
        )
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise EnvironmentFileError(
            "credentials.env-file-insecure-permissions",
            "The test environment file must be readable and writable only by its owner (0600).",
        )
    return parse_environment_text(
        path.read_text(encoding="utf-8"),
        allowed_keys=set(declared_keys),
    )


def resolve_environment_file_path(project: Path, path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (project / path).resolve()


def build_child_environment_values(
    explicit_values: dict[str, str],
    *,
    declared_keys: Iterable[str],
) -> dict[str, str]:
    allowed = set(declared_keys)
    undeclared = sorted(set(explicit_values) - allowed)
    if undeclared:
        raise EnvironmentFileError(
            "credentials.env-file-undeclared-key",
            f"Environment values include undeclared key {undeclared[0]}.",
        )
    return {key: explicit_values[key] for key in explicit_values if key in allowed}
