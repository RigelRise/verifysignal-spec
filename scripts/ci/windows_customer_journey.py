"""The customer journey, on a real Windows machine.

Every other CI job in every VerifySignal repo runs on ubuntu, which is why Windows was the one
platform that broke: nobody had ever run it. Two Windows legs already exist and each proves one
END of the path -- the Spec repo's `windows-install` proves the advertised installer and the CLI it
produces, and this repo's `windows-launcher` proves the packaged `.cmd` runtime starts. Neither
proves the MIDDLE: that a customer can go from a downloaded runtime to a report.

This script is that middle. It is deliberately NOT `customer_journey.py`: that one's subject is
cross-repo trust plumbing (local Supabase, ephemeral keypairs, real HTTP), it shells out to `npm`
with a bare name, and it asserts `permissions == "0600"` -- none of which are answerable on a
hosted Windows runner. The question here is narrower and different: does the shipped thing work.

Each gate prints a ledger line and the script exits at the FIRST failure, naming the step, what was
observed, what was expected, and where to fix it. A gate that fails must say enough to act on
without opening the run log.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from install_with_embedded_anchor import synthesize_manifest  # noqa: E402

from verifysignal_spec.runtime.distribution import install_from_manifest, normalize_platform  # noqa: E402


class GateFailure(Exception):
    def __init__(self, gate: str, step: str, observed: object, expected: str, fix: str) -> None:
        super().__init__(gate)
        self.gate = gate
        self.step = step
        self.observed = observed
        self.expected = expected
        self.fix = fix


def _report(gate: str, ok: bool, detail: str = "") -> None:
    print(f"[windows-journey] {gate:<18} {'PASS' if ok else 'FAIL'}{('  ' + detail) if detail else ''}", flush=True)


def _cli(args: list[str], *, cwd: Path | None = None) -> tuple[int, str, str]:
    # The INSTALLED console script, not `python -m verifysignal_spec.cli`. cli.py has no
    # `if __name__ == "__main__"` block, so `-m` imports the module, never calls main(), and exits 0
    # with empty output -- which is exactly how this gate first failed. It is also the right choice
    # on its own terms: a customer runs `verifysignal`, so that is what this journey should run.
    executable = shutil.which("verifysignal")
    if not executable:
        raise GateFailure(
            "cliOnPath",
            "shutil.which('verifysignal')",
            None,
            "the installed console script on PATH",
            "the install step did not put verifysignal on PATH",
        )
    proc = subprocess.run(
        [executable, *args],
        cwd=str(cwd) if cwd else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return proc.returncode, proc.stdout, proc.stderr


def _json_or_fail(gate: str, step: str, raw: str, fix: str) -> dict:
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise GateFailure(gate, step, f"{raw[:200]!r}", "parseable JSON", fix) from exc


def gate_platform_resolved() -> str:
    resolved = normalize_platform()
    if resolved != "win32-x64":
        raise GateFailure(
            "platformResolved",
            "normalize_platform()",
            resolved,
            "win32-x64",
            "src/verifysignal_spec/runtime/distribution.py::normalize_platform",
        )
    return resolved


def gate_managed_install(artifact_dir: Path, workdir: Path, platform: str) -> str:
    manifest = synthesize_manifest(artifact_dir, workdir, platform=platform)
    entries = json.loads(manifest.read_text(encoding="utf-8"))["entries"]
    entry = next((item for item in entries if item["platform"] == platform), None)
    if entry is None:
        raise GateFailure(
            "managedInstall",
            "select_manifest_entry",
            [item["platform"] for item in entries],
            platform,
            "the Core release did not publish this platform",
        )
    command, blocker = install_from_manifest(entry)
    if blocker is not None or not command:
        raise GateFailure(
            "managedInstall",
            "install_from_manifest",
            getattr(blocker, "code", None) or "no runtime command",
            "an installed runtime command",
            "src/verifysignal_spec/runtime/distribution.py::install_from_manifest",
        )
    return command


def gate_packaged_identity(command: str) -> dict:
    from verifysignal_spec.process import launch_argv

    argv = launch_argv(command)
    proc = subprocess.run(
        [*argv, "version", "--json"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if proc.returncode != 0:
        raise GateFailure(
            "packagedIdentity",
            " ".join(argv) + " version --json",
            f"exit {proc.returncode}: {(proc.stderr or '').strip()[:200]}",
            "exit 0",
            "src/verifysignal_spec/process.py::launch_argv",
        )
    payload = _json_or_fail("packagedIdentity", "version --json", proc.stdout, "the packaged runtime bundle")
    package_id = payload.get("data", {}).get("runtime", {}).get("packageId")
    if not package_id or "win32-x64" not in package_id:
        raise GateFailure(
            "packagedIdentity",
            "version --json",
            package_id,
            "a packageId naming win32-x64",
            "scripts/runtime/build-runtime-package.ts in the Core repo",
        )
    return payload


def _blockers(payload: object) -> list[str]:
    """Every blocker anywhere in a CLI payload, as `code: message`, in the order found.

    The CLI nests its blocker differently per command (`runtime.blocker.code`, `blockers[].code`,
    one per stage), so a walk is more honest than guessing at a shape.

    The MESSAGE matters as much as the code, and leaving it out cost a full CI cycle: Core carries
    the underlying cause there (a spawn failure, a network failure and a version mismatch all share
    the code `browser-assets-unavailable`), so a ledger printing only the code cannot tell those
    apart -- and a rerun after a fix produced a byte-identical line, indistinguishable from the fix
    never having shipped.
    """

    found: list[str] = []
    if isinstance(payload, dict):
        code = payload.get("code")
        # Dotted (entitlement.unlock-required) or hyphenated (browser-assets-unavailable):
        # the CLI uses both shapes, and a dotted-only rule silently skipped the second.
        if isinstance(code, str) and ("." in code or "-" in code):
            message = payload.get("message")
            detail = str(message).strip() if isinstance(message, str) and message.strip() else ""
            found.append(f"{code}: {detail}" if detail else str(code))
        for value in payload.values():
            found.extend(_blockers(value))
    elif isinstance(payload, list):
        for value in payload:
            found.extend(_blockers(value))
    return found


def _failed(gate: str, step: str, code: int, out: str, err: str, fix: str) -> GateFailure:
    """Turn a non-zero CLI exit into a ledger line that names the PRODUCT blocker.

    With `--json` the structured payload goes to STDOUT even on failure, so reporting only stderr
    (which is usually empty) throws away the one thing worth reading.
    """

    try:
        payload = json.loads(out)
    except json.JSONDecodeError:
        detail = (err.strip() or out.strip() or "no output")[:200]
        return GateFailure(gate, step, f"exit {code}: {detail}", "exit 0", fix)
    codes = _blockers(payload)
    observed = f"exit {code}: {', '.join(dict.fromkeys(codes))}" if codes else f"exit {code}: {json.dumps(payload)[:200]}"
    return GateFailure(gate, step, observed, "exit 0", codes[0] if codes else fix)


def gate_init(project: Path, command: str) -> dict:
    code, out, err = _cli(["init", str(project), "--integration", "claude", "--core-cmd", command, "--json"])
    if code != 0:
        raise _failed("init", "verifysignal init --json", code, out, err, "verifysignal init on Windows")
    return _json_or_fail("init", "verifysignal init", out, "verifysignal init on Windows")


def gate_check(project: Path, command: str) -> dict:
    code, out, err = _cli(["check", "--project", str(project), "--core-cmd", command, "--json"])
    payload = _json_or_fail("check", "verifysignal check", out or err, "verifysignal check on Windows")
    readiness = payload.get("managedRuntimeReadiness") or payload.get("runtime") or {}
    blocker = (readiness.get("blocker") or {}).get("code")
    if blocker == "platform.unsupported":
        raise GateFailure(
            "check",
            "verifysignal check --json",
            blocker,
            "no platform blocker",
            "src/verifysignal_spec/runtime/distribution.py::normalize_platform",
        )
    if code != 0 and blocker:
        raise GateFailure("check", "verifysignal check --json", blocker, "a ready runtime", "the blocker named above")
    return payload


DRAFT_SKILL = """---
schemaVersion: qa-skill/v1
---

# Draft

```yaml
schemaVersion: qa-skill/v1
skill:
  id: skill.windows-journey
  version: 1.0.0
  kind: browser
  name: Windows journey
  description: A drafted skill used only to drive grounding against a live page.
browser:
  targets: {}
  steps:
    - id: open-page
      action: navigate
  assertions: []
```
"""


def gate_browser_ready(project: Path, command: str) -> dict:
    """Drive a real browser operation and report what the runtime says about its assets.

    `discover` is Core's entitlement-free grounding operation, and the cheapest path to
    `ensureBrowserAssetsReady` -- the one thing neither existing Windows leg reaches. It is the
    honest place for this journey to fail today, because NOTHING a customer runs installs a browser:
    Core's `prepare` only mkdirs the cache directory and never downloads, and
    `setup-playwright-mcp` runs `npm install --ignore-scripts`, which suppresses exactly that
    download. That is true on macOS and Linux too -- it has simply never surfaced there, because CI
    runs `playwright install` and a developer machine already has the cache.
    """

    skill = project / "draft.browser.md"
    skill.write_text(DRAFT_SKILL, encoding="utf-8")
    code, out, err = _cli(
        ["discover", "--url", "https://example.com", "--skill", str(skill), "--project", str(project), "--core-cmd", command, "--json"]
    )
    payload = _json_or_fail("browserReady", "verifysignal discover", out or err, "the browser adapter in the Core repo")
    reported = _blockers(payload)
    unavailable = next((item for item in reported if item.startswith("browser-assets-unavailable")), None)
    if unavailable:
        raise GateFailure(
            "browserReady",
            "verifysignal discover --json",
            unavailable,
            "a browser the packaged runtime can drive",
            "packages/adapter-browser-playwright/src/browser-readiness.ts::ensureBrowserAssetsReady "
            "-- its `prepare` mkdirs but never downloads, and the manifest already advertises "
            "browserAssets.happyPath = auto-prepare-or-verify",
        )
    if code != 0:
        raise GateFailure("browserReady", "verifysignal discover --json", f"exit {code}", "exit 0", "the payload above")
    return payload


def main() -> int:
    artifact_dir = Path(os.environ["VERIFYSIGNAL_RELEASE_ARTIFACT_DIR"]).resolve()
    workdir = Path(os.environ.get("RUNNER_TEMP", ".")).resolve() / "windows journey"
    workdir.mkdir(parents=True, exist_ok=True)
    # A space in the path is not contrived: the user who reported this was working in
    # `C:\Users\shima\Desktop\Pasta teste\`, and a space is where quoting breaks first.
    project = workdir / "target project"
    project.mkdir(parents=True, exist_ok=True)

    try:
        platform = gate_platform_resolved()
        _report("platformResolved", True, platform)

        command = gate_managed_install(artifact_dir, workdir, platform)
        _report("managedInstall", True, command)

        version = gate_packaged_identity(command)
        _report("packagedIdentity", True, version["data"]["runtime"]["packageId"])

        gate_init(project, command)
        _report("init", True, str(project))

        gate_check(project, command)
        _report("check", True)

        gate_browser_ready(project, command)
        _report("browserReady", True)
    except GateFailure as failure:
        _report(failure.gate, False)
        print(
            f"  step:     {failure.step}\n"
            f"  observed: {failure.observed}\n"
            f"  expected: {failure.expected}\n"
            f"  fix:      {failure.fix}",
            flush=True,
        )
        summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary:
            with open(summary, "a", encoding="utf-8") as handle:
                handle.write(
                    f"### Windows journey failed at `{failure.gate}`\n\n"
                    f"- **step**: `{failure.step}`\n"
                    f"- **observed**: `{failure.observed}`\n"
                    f"- **expected**: {failure.expected}\n"
                    f"- **fix**: `{failure.fix}`\n"
                )
        return 1

    print("[windows-journey] every gate passed on a real Windows host.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
