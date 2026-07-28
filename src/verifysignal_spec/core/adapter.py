from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .contracts import CompatibilityResult, normalize_status, validate_version_response
from .errors import CoreExecutionError, CoreIncompatibleError, CoreMissingError

CORE_SETUP_HINT = (
    "Run `verifysignal core setup --json` to discover and persist an existing "
    "VerifySignal Core command, or pass `--core-cmd /path/to/verifysignal` for a "
    "one-off command."
)


class CoreAdapter:
    def __init__(self, executable: str | None = None, cwd: Path | None = None) -> None:
        self.executable = executable or os.environ.get("VERIFYSIGNAL_CORE_CMD")
        self.cwd = cwd

    def _base_command(self) -> list[str]:
        if not self.executable:
            raise CoreMissingError(
                "VerifySignal Core command is not configured. "
                f"{CORE_SETUP_HINT}"
            )
        raw = self.executable.strip()
        path = Path(raw).expanduser()
        if path.exists() and path.is_dir():
            if (path / "package.json").exists():
                return ["npm", "--silent", "--prefix", str(path.resolve()), "run", "verifysignal:dev", "--"]
            raise CoreMissingError(f"VerifySignal Core path is a directory without package.json: {path}. {CORE_SETUP_HINT}")
        if path.exists() and path.is_file():
            return [str(path.resolve())]

        parts = shlex.split(raw)
        if len(parts) > 1:
            resolved = shutil.which(parts[0])
            if not resolved:
                raise CoreMissingError(f"VerifySignal Core command not found: {parts[0]}. {CORE_SETUP_HINT}")
            return [resolved, *parts[1:]]

        resolved = shutil.which(raw)
        if not resolved:
            raise CoreMissingError(f"VerifySignal Core executable not found: {self.executable}. {CORE_SETUP_HINT}")
        return [resolved]

    def resolved_command(self) -> str:
        return shlex.join(self._base_command())

    def _run(self, args: list[str], env: dict[str, str] | None = None) -> dict[str, Any]:
        base_command = self._base_command()
        proc = subprocess.run(
            [*base_command, *args],
            cwd=str(self.cwd) if self.cwd else None,
            env={**os.environ, **(env or {})},
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if proc.returncode != 0 and not proc.stdout.strip():
            raise CoreExecutionError(proc.stderr.strip() or f"VerifySignal Core exited with {proc.returncode}")
        try:
            return json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            start = proc.stdout.find("{")
            end = proc.stdout.rfind("}")
            if start != -1 and end > start:
                try:
                    return json.loads(proc.stdout[start : end + 1])
                except json.JSONDecodeError:
                    pass
            raise CoreExecutionError(f"VerifySignal Core returned non-JSON output: {proc.stdout[:200]}") from exc

    def version(self) -> dict[str, Any]:
        return self._run(["version", "--json"])

    def contracts(self) -> dict[str, Any]:
        self.require_compatible()
        return self._run(["contracts", "--json"])

    def check_compatibility(self) -> CompatibilityResult:
        return validate_version_response(self.version())

    def require_compatible(self) -> CompatibilityResult:
        result = self.check_compatibility()
        if not result.compatible:
            raise CoreIncompatibleError(result.message)
        return result

    def authoring_check(
        self,
        run_request: Path,
        main_skill: Path,
        skills: list[Path],
        runtime_readiness: bool = False,
        entitlement_receipt: Path | str | None = None,
    ) -> dict[str, Any]:
        compatibility = self.require_compatible()
        args = ["authoring-check", "run-request", str(run_request), "--skill", str(main_skill)]
        for skill in skills:
            if skill != main_skill:
                args.extend(["--skill", str(skill)])
        if runtime_readiness:
            args.append("--runtime-readiness")
        args.append("--json")
        return self._run(
            args,
            env=_receipt_env(
                entitlement_receipt,
                compatibility=compatibility,
            ),
        )

    def run(
        self,
        run_request: Path,
        main_skill: Path,
        skills: list[Path],
        output_dir: Path | None = None,
        headed: bool = False,
        slow_mo_ms: int = 0,
        record: bool = False,
        replay: Path | str | None = None,
        env: dict[str, str] | None = None,
        entitlement_receipt: Path | str | None = None,
    ) -> dict[str, Any]:
        compatibility = self.require_compatible()
        args = ["run", str(run_request), "--skill", str(main_skill)]
        for skill in skills:
            if skill != main_skill:
                args.extend(["--skill", str(skill)])
        if output_dir:
            args.extend(["--output-dir", str(output_dir)])
        if headed:
            args.append("--headed")
        if slow_mo_ms:
            args.extend(["--slow-mo", str(slow_mo_ms)])
        if record:
            args.append("--record")
        if replay:
            args.extend(["--replay", str(replay)])
        args.append("--json")
        return self._run(
            args,
            env={
                **(env or {}),
                **_receipt_env(
                    entitlement_receipt,
                    compatibility=compatibility,
                ),
            },
        )

    def probe(
        self,
        run_request: Path,
        main_skill: Path,
        skills: list[Path],
        headed: bool = False,
        slow_mo_ms: int = 0,
        env: dict[str, str] | None = None,
        entitlement_receipt: Path | str | None = None,
    ) -> dict[str, Any]:
        """Exercise a run request only through its pre-commit boundary.

        Credential and session material stays referenced by the run request.
        The public Core invocation receives artifact paths and presentation
        options only.
        """
        compatibility = self.require_compatible()
        args = ["probe", str(run_request), "--skill", str(main_skill)]
        for skill in skills:
            if skill != main_skill:
                args.extend(["--skill", str(skill)])
        if headed:
            args.append("--headed")
        if slow_mo_ms:
            args.extend(["--slow-mo", str(slow_mo_ms)])
        args.append("--json")
        return self._run(
            args,
            env={
                **(env or {}),
                **_receipt_env(
                    entitlement_receipt,
                    compatibility=compatibility,
                ),
            },
        )

    def discover(
        self,
        *,
        url: str,
        skill: Path,
        headed: bool = False,
        env: dict[str, str] | None = None,
        entitlement_receipt: Path | str | None = None,
    ) -> dict[str, Any]:
        """Ground a drafted skill's targets against the live DOM via Core's
        optional, entitlement-free `discover` operation (Core feature 016)."""
        compatibility = self.require_compatible()
        args = ["discover", "--url", url, "--skill", str(skill)]
        if headed:
            args.append("--headed")
        args.append("--json")
        return self._run(
            args,
            env={
                **(env or {}),
                **_receipt_env(
                    entitlement_receipt,
                    compatibility=compatibility,
                ),
            },
        )

    def crystallize(
        self,
        *,
        run_dir: Path | str,
        out: Path | str | None = None,
        env: dict[str, str] | None = None,
        entitlement_receipt: Path | str | None = None,
    ) -> dict[str, Any]:
        """Crystallize a completed run into a reusable fixture via Core's
        optional, entitlement-PROTECTED `crystallize` operation (schema
        `verifysignal.crystallize/v1`). It reads private evidence, so callers
        supply an entitlement receipt just like `run`."""
        compatibility = self.require_compatible()
        args = ["crystallize", str(run_dir)]
        if out:
            args.extend(["--out", str(out)])
        args.append("--json")
        return self._run(
            args,
            env={
                **(env or {}),
                **_receipt_env(
                    entitlement_receipt,
                    compatibility=compatibility,
                ),
            },
        )

    def inspect_report(self, report_path: Path, entitlement_receipt: Path | str | None = None) -> dict[str, Any]:
        compatibility = self.require_compatible()
        return self._run(
            ["report", "inspect", str(report_path), "--json"],
            env=_receipt_env(
                entitlement_receipt,
                compatibility=compatibility,
            ),
        )


def _receipt_env(
    entitlement_receipt: Path | str | None,
    *,
    compatibility: CompatibilityResult | None = None,
) -> dict[str, str]:
    env: dict[str, str] = {}
    if entitlement_receipt:
        env["VERIFYSIGNAL_ENTITLEMENT_RECEIPT"] = str(entitlement_receipt)
    if (
        not _uses_packaged_runtime_trust(compatibility)
        and not os.environ.get("VERIFYSIGNAL_ENTITLEMENT_PUBLIC_KEYS_JSON")
    ):
        try:
            from verifysignal_spec.runtime.distribution import load_verification_keys

            cached = load_verification_keys()
            keys = cached.get("keys") if isinstance(cached, dict) else None
            if isinstance(keys, list):
                env["VERIFYSIGNAL_ENTITLEMENT_PUBLIC_KEYS_JSON"] = json.dumps(keys, separators=(",", ":"))
        except Exception:
            pass
    return env


def _uses_packaged_runtime_trust(
    compatibility: CompatibilityResult | None,
) -> bool:
    raw = compatibility.raw if compatibility else None
    if not isinstance(raw, dict):
        return False
    data = raw.get("data")
    if not isinstance(data, dict):
        return False
    runtime = data.get("runtime")
    if not isinstance(runtime, dict):
        return False
    package_id = runtime.get("packageId")
    return isinstance(package_id, str) and bool(package_id.strip())


def readiness(executable: str | None = None, cwd: Path | None = None) -> dict[str, Any]:
    adapter = CoreAdapter(executable=executable, cwd=cwd)
    try:
        result = adapter.check_compatibility()
        return {"available": True, **result.to_dict()}
    except CoreMissingError as exc:
        return {"available": False, "compatible": False, "message": str(exc), "missingOperations": []}
    except Exception as exc:
        return {"available": True, "compatible": False, "message": str(exc), "missingOperations": []}


def core_status(result: dict[str, Any]) -> str:
    return normalize_status(result)


def resolve_persistable_core_command(command: str, *, cwd: Path | None = None) -> str:
    path = Path(command.strip()).expanduser()
    if path.exists() and path.is_dir():
        return CoreAdapter(executable=command, cwd=cwd).resolved_command()
    return command
