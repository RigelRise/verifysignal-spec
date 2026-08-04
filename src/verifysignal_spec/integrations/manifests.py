from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from verifysignal_spec.workspace import layout
from verifysignal_spec.workspace.models import AgentIntegrationState, ManagedFileRecord
from verifysignal_spec.workspace.repository import load_document, now_iso, save_document
from verifysignal_spec.workspace.textio import write_text_lf

from .base import RenderedFile


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def load_manifest(project: Path, key: str) -> AgentIntegrationState | None:
    data = load_document(layout.manifest_path(project, key))
    return AgentIntegrationState.from_dict(data) if data else None


def save_manifest(project: Path, state: AgentIntegrationState) -> None:
    save_document(layout.manifest_path(project, state.key), state.to_dict())
    update_integration_state(project, state)


def load_all_states(project: Path) -> dict[str, Any]:
    return load_document(layout.integration_state_path(project), default={"schemaVersion": "verifysignal-spec-integrations/v1", "integrations": {}})


def update_integration_state(project: Path, state: AgentIntegrationState) -> None:
    data = load_all_states(project)
    integrations = dict(data.get("integrations", {}))
    if state.default:
        for value in integrations.values():
            if isinstance(value, dict):
                value["default"] = False
    integrations[state.key] = {
        "displayName": state.displayName,
        "installedAt": state.installedAt,
        "default": state.default,
        "invokeStyle": state.invokeStyle,
    }
    data["integrations"] = integrations
    save_document(layout.integration_state_path(project), data)


def install_rendered_files(project: Path, key: str, display_name: str, invoke_style: str, files: list[RenderedFile], force: bool = False, default: bool = True) -> AgentIntegrationState:
    previous = load_manifest(project, key)
    previous_hashes = {item.path: item.sha256 for item in previous.managedFiles} if previous else {}
    rendered_paths = {item.path for item in files}
    records: list[ManagedFileRecord] = []
    if previous:
        for item in previous.managedFiles:
            if item.path in rendered_paths:
                continue
            target = project / item.path
            if not target.exists():
                continue
            current_hash = sha256_bytes(target.read_bytes())
            if current_hash == item.sha256 or force:
                target.unlink()
    for item in files:
        target = project / item.path
        content_hash = sha256_text(item.content)
        if target.exists() and not force:
            current_hash = sha256_bytes(target.read_bytes())
            previous_hash = previous_hashes.get(item.path)
            if previous_hash and current_hash != previous_hash:
                records.append(ManagedFileRecord(path=item.path, sha256=current_hash, source=item.source, kind=item.kind))
                continue
            if not previous_hash:
                # User-owned existing file. Preserve by default.
                records.append(ManagedFileRecord(path=item.path, sha256=current_hash, source=item.source, kind=item.kind))
                continue
        # LF, because content_hash above was taken from the LF string and the next run compares it
        # against these bytes. A CRLF translation makes every managed file read as user-modified
        # forever: never refreshed, never removed on uninstall.
        write_text_lf(target, item.content)
        records.append(ManagedFileRecord(path=item.path, sha256=content_hash, source=item.source, kind=item.kind))
    state = AgentIntegrationState(
        key=key,
        displayName=display_name,
        installedAt=previous.installedAt if previous else now_iso(),
        default=default,
        managedFiles=records,
        invokeStyle=invoke_style,
    )
    save_manifest(project, state)
    return state


def remove_integration(project: Path, key: str, force: bool = False) -> list[str]:
    manifest = load_manifest(project, key)
    preserved: list[str] = []
    if manifest:
        for item in manifest.managedFiles:
            target = project / item.path
            if not target.exists():
                continue
            current_hash = sha256_bytes(target.read_bytes())
            if current_hash != item.sha256 and not force:
                preserved.append(item.path)
                continue
            target.unlink()
        manifest_path = layout.manifest_path(project, key)
        if manifest_path.exists():
            manifest_path.unlink()
    data = load_all_states(project)
    integrations = dict(data.get("integrations", {}))
    integrations.pop(key, None)
    data["integrations"] = integrations
    save_document(layout.integration_state_path(project), data)
    return preserved


def set_default(project: Path, key: str) -> None:
    data = load_all_states(project)
    integrations = dict(data.get("integrations", {}))
    if key not in integrations:
        raise ValueError(f"Integration is not installed: {key}")
    for name, value in integrations.items():
        if isinstance(value, dict):
            value["default"] = name == key
    data["integrations"] = integrations
    save_document(layout.integration_state_path(project), data)
