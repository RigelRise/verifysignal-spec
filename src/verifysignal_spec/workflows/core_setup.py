from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from verifysignal_spec.core.adapter import CoreAdapter, resolve_persistable_core_command
from verifysignal_spec.core.contracts import CompatibilityResult, PUBLIC_CONTRACT_VERSION, public_contract_summary
from verifysignal_spec.core.errors import CoreExecutionError, CoreMissingError
from verifysignal_spec.repos import ancestor_core_candidates
from verifysignal_spec.workspace.repository import (
    get_core_command,
    init_workspace,
    save_core_configuration,
)

from .models import CoreCandidateAttempt, CoreSetupResult

TERMINAL_CONFIG_SOURCES = {"explicit", "workspace", "env"}
SECRET_MARKERS = (
    "password",
    "passwd",
    "secret",
    "token",
    "api-key",
    "api_key",
    "apikey",
    "credential",
    "bearer ",
)
REDACTED_COMMAND = "[redacted]"


@dataclass(frozen=True, slots=True)
class CoreSetupCandidate:
    source: str
    command: str
    display_path: str | None = None
    missing_message: str | None = None

    @property
    def public_command(self) -> str:
        return REDACTED_COMMAND if _looks_secret_like(self.command) else self.command

    @property
    def public_display_path(self) -> str | None:
        if self.display_path is None:
            return None
        return REDACTED_COMMAND if _looks_secret_like(self.display_path) else self.display_path

    def to_attempt(
        self,
        *,
        status: str = "available",
        terminal: bool = False,
        version: str | None = None,
        message: str = "",
    ) -> CoreCandidateAttempt:
        return CoreCandidateAttempt(
            source=self.source,  # type: ignore[arg-type]
            command=self.public_command,
            displayPath=self.public_display_path,
            status=status,  # type: ignore[arg-type]
            terminal=terminal,
            version=version,
            message=message,
        )


def discover_candidates(project: Path, explicit_core_cmd: str | None = None) -> list[CoreCandidateAttempt]:
    return [candidate.to_attempt(status="missing" if candidate.missing_message else "available", message=candidate.missing_message or "") for candidate in _discover_candidate_records(project, explicit_core_cmd)]


def verify_candidate(
    project: Path,
    *,
    source: str,
    command: str,
    display_path: str | None = None,
) -> tuple[CoreCandidateAttempt, CompatibilityResult | None]:
    candidate = CoreSetupCandidate(source=source, command=command, display_path=display_path or _display_path(command))
    terminal = source in TERMINAL_CONFIG_SOURCES
    if _looks_secret_like(command):
        return (
            candidate.to_attempt(
                status="error",
                terminal=terminal,
                message="Core command value looks credential-bearing and was not used or persisted.",
            ),
            None,
        )

    try:
        compatibility = CoreAdapter(executable=command, cwd=project).check_compatibility()
    except CoreMissingError as exc:
        return (candidate.to_attempt(status="missing", terminal=terminal, message=str(exc)), None)
    except CoreExecutionError as exc:
        return (candidate.to_attempt(status="error", terminal=terminal, message=str(exc)), None)
    except Exception as exc:
        return (candidate.to_attempt(status="error", terminal=terminal, message=str(exc)), None)

    if compatibility.compatible:
        return (
            candidate.to_attempt(
                status="compatible",
                terminal=True,
                version=compatibility.verifysignalVersion,
                message="Core command verified through public CLI contract.",
            ),
            compatibility,
        )
    return (
        candidate.to_attempt(
            status="incompatible",
            terminal=terminal,
            version=compatibility.verifysignalVersion,
            message="Configured or discovered Core is incompatible with the required operations.",
        ),
        compatibility,
    )


def run_core_setup(project: Path, explicit_core_cmd: str | None = None, *, persist: bool = True) -> CoreSetupResult:
    project = project.resolve()
    init_workspace(project)
    attempts: list[CoreCandidateAttempt] = []
    last_compatibility: CompatibilityResult | None = None
    last_blocking_attempt: CoreCandidateAttempt | None = None

    for candidate in _discover_candidate_records(project, explicit_core_cmd):
        if candidate.missing_message:
            attempts.append(candidate.to_attempt(status="missing", terminal=False, message=candidate.missing_message))
            continue
        attempt, compatibility = verify_candidate(
            project,
            source=candidate.source,
            command=candidate.command,
            display_path=candidate.display_path,
        )
        attempts.append(attempt)
        if attempt.status == "compatible" and compatibility:
            one_time = candidate.source == "explicit" and not persist
            persisted = False
            core_command = resolve_persistable_core_command(candidate.command, cwd=project)
            if persist:
                save_core_configuration(project, core_command, source=candidate.source, version=compatibility.verifysignalVersion)
                persisted = True
            selected = CoreCandidateAttempt(
                source=attempt.source,
                command=core_command,
                displayPath=attempt.displayPath,
                status=attempt.status,
                terminal=True,
                version=attempt.version,
                message=attempt.message,
            )
            attempts[-1] = selected
            return CoreSetupResult(
                status="ready",
                coreCommand=core_command,
                source=candidate.source,  # type: ignore[arg-type]
                selectedCandidate=selected,
                persisted=persisted,
                oneTime=one_time,
                version=compatibility.verifysignalVersion,
                contractVersion=compatibility.contractVersion or PUBLIC_CONTRACT_VERSION,
                missingOperations=[],
                incompatibleOperations=[],
                attempts=attempts,
                message="VerifySignal Core is ready.",
                nextAction="Continue with validation or run.",
            )
        if compatibility:
            last_compatibility = compatibility
        if attempt.terminal:
            last_blocking_attempt = attempt
            break
        if attempt.status in {"incompatible", "error"}:
            last_blocking_attempt = attempt

    return _blocked_result(attempts, last_blocking_attempt, last_compatibility)


def onboarding_core_status(result: CoreSetupResult) -> dict[str, object]:
    selected = result.selectedCandidate.to_dict() if result.selectedCandidate else None
    if result.status == "ready":
        return {
            "statusMarker": "[READY]",
            "summary": "VerifySignal Core is ready.",
            "source": result.source,
            "coreCommand": result.coreCommand,
            "selectedCandidate": selected,
            "nextAction": "Continue with validation or run.",
            "guideText": "VerifySignal Core is ready. Full validation and browser execution can use the selected Core command.",
        }
    if result.status == "missing":
        return {
            "statusMarker": "[BLOCKED]",
            "summary": "Core was not found. Specification and authoring can continue, but full validation and browser execution require Core.",
            "source": None,
            "coreCommand": None,
            "selectedCandidate": None,
            "nextAction": result.recoveryCommand,
            "guideText": "Specification, understanding, planning, task generation, and artifact authoring can continue without Core. Full validation and browser execution remain blocked until Core setup succeeds.",
        }
    if result.status == "incompatible":
        return {
            "statusMarker": "[INCOMPATIBLE]",
            "summary": "The configured/discovered Core command does not satisfy required operations.",
            "source": result.source,
            "coreCommand": result.coreCommand,
            "selectedCandidate": None,
            "nextAction": "Fix the configured command or rerun setup with a compatible Core.",
            "guideText": "The configured/discovered VerifySignal Core command is incompatible with the public CLI JSON contract. Specification and authoring can continue, but full validation and browser execution require compatible Core setup.",
        }
    return {
        "statusMarker": "[ERROR]",
        "summary": "Core setup could not complete safely.",
        "source": result.source,
        "coreCommand": result.coreCommand,
        "selectedCandidate": None,
        "nextAction": "Inspect setup attempts and rerun verifysignal core setup --json.",
        "guideText": "Core setup could not complete safely. Specification and authoring can continue, but full validation and browser execution require a successful Core setup.",
    }


def _discover_candidate_records(project: Path, explicit_core_cmd: str | None = None) -> list[CoreSetupCandidate]:
    candidates: list[CoreSetupCandidate] = []
    seen: set[tuple[str, str]] = set()

    def add(source: str, command: str, display_path: str | None = None, missing_message: str | None = None) -> None:
        key = (source, command)
        if key in seen:
            return
        seen.add(key)
        candidates.append(CoreSetupCandidate(source=source, command=command, display_path=display_path, missing_message=missing_message))

    if explicit_core_cmd:
        add("explicit", explicit_core_cmd, _display_path(explicit_core_cmd))

    workspace_cmd = get_core_command(project)
    if workspace_cmd:
        add("workspace", workspace_cmd, _display_path(workspace_cmd))

    env_cmd = os.environ.get("VERIFYSIGNAL_CORE_CMD")
    if env_cmd:
        add("env", env_cmd, _display_path(env_cmd))

    path_cmd = shutil.which("verifysignal")
    if path_cmd:
        add("path", path_cmd, _display_path(path_cmd))
    else:
        add("path", "verifysignal", None, "No verifysignal command found on PATH.")

    for candidate in _ancestor_sibling_paths(project):
        add("ancestor-sibling", str(candidate), str(candidate))

    return candidates


def _ancestor_sibling_paths(project: Path) -> list[Path]:
    # By identity, not by directory name — see verifysignal_spec.repos.
    return ancestor_core_candidates(project)


def _blocked_result(
    attempts: list[CoreCandidateAttempt],
    last_blocking_attempt: CoreCandidateAttempt | None,
    compatibility: CompatibilityResult | None,
) -> CoreSetupResult:
    contract = public_contract_summary()
    if last_blocking_attempt and last_blocking_attempt.status == "error":
        return CoreSetupResult(
            status="error",
            source=last_blocking_attempt.source,
            version=last_blocking_attempt.version,
            contractVersion=contract["contractVersion"],
            attempts=attempts,
            message="Core setup could not complete safely.",
            nextAction="Inspect setup attempts and rerun verifysignal core setup --json.",
        )
    if last_blocking_attempt and last_blocking_attempt.status == "incompatible":
        return CoreSetupResult(
            status="incompatible",
            coreCommand=last_blocking_attempt.command,
            source=last_blocking_attempt.source,
            version=last_blocking_attempt.version,
            contractVersion=(compatibility.contractVersion if compatibility else None) or contract["contractVersion"],
            missingOperations=(compatibility.missingOperations if compatibility else []) or [],
            incompatibleOperations=(compatibility.incompatibleOperations if compatibility else []) or [],
            attempts=attempts,
            message="Configured or discovered VerifySignal Core is incompatible.",
            nextAction="Fix the configured command or rerun setup with a compatible Core.",
        )
    return CoreSetupResult(
        status="missing",
        contractVersion=contract["contractVersion"],
        attempts=attempts,
        message="VerifySignal Core was not found.",
        nextAction="Install or provide an existing Core command, then rerun setup.",
    )


def _display_path(command: str) -> str | None:
    first = command.strip().split()[0] if command.strip() else command
    path = Path(first).expanduser()
    if path.exists():
        return str(path.resolve())
    return None


def _looks_secret_like(value: str) -> bool:
    lower = value.lower()
    return any(marker in lower for marker in SECRET_MARKERS)
