from __future__ import annotations

import contextlib
import io
import os
import sys
import tempfile
import unittest
from collections.abc import Iterable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# Re-exported so tests never reach for a sibling repo by directory name.
from verifysignal_spec.repos import (  # noqa: E402
    SIBLING_IDENTITY,
    ancestor_core_candidates,
    require_sibling_repo,
    resolve_sibling_repo,
)

FAKE_CORE = ROOT / "tests" / "fixtures" / "verifysignal-core" / "fake_verifysignal.py"
TEMPLATE_DIR = ROOT / "src" / "verifysignal_spec" / "templates" / "agent-commands"


class CliTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.project = Path(self.tmp.name)
        self.old_core = os.environ.get("VERIFYSIGNAL_CORE_CMD")
        self.old_mode = os.environ.get("FAKE_VERIFYSIGNAL_MODE")
        self.old_runtime_cache = os.environ.get("VERIFYSIGNAL_RUNTIME_CACHE_DIR")
        os.environ["VERIFYSIGNAL_CORE_CMD"] = str(FAKE_CORE)
        os.environ["VERIFYSIGNAL_RUNTIME_CACHE_DIR"] = str(self.project / "runtime-cache")
        os.environ.pop("FAKE_VERIFYSIGNAL_MODE", None)

    def tearDown(self) -> None:
        self.tmp.cleanup()
        if self.old_core is None:
            os.environ.pop("VERIFYSIGNAL_CORE_CMD", None)
        else:
            os.environ["VERIFYSIGNAL_CORE_CMD"] = self.old_core
        if self.old_mode is None:
            os.environ.pop("FAKE_VERIFYSIGNAL_MODE", None)
        else:
            os.environ["FAKE_VERIFYSIGNAL_MODE"] = self.old_mode
        if self.old_runtime_cache is None:
            os.environ.pop("VERIFYSIGNAL_RUNTIME_CACHE_DIR", None)
        else:
            os.environ["VERIFYSIGNAL_RUNTIME_CACHE_DIR"] = self.old_runtime_cache

    def cli(self, args: list[str]) -> tuple[int, str, str]:
        from verifysignal_spec.cli import main

        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(args)
        return code, stdout.getvalue(), stderr.getvalue()


def agent_template(stage: str) -> str:
    return (TEMPLATE_DIR / f"verifysignal.{stage}.md").read_text(encoding="utf-8")


def assert_guardrail_template(content: str, stage: str) -> None:
    assert f"verifysignal workflow check {stage}" in content
    assert "workflow.guardrails/v1" in content
    assert "Do not use `npx` or package-runner wrappers" in content
    assert "verifysignal-spec-fe" not in content
    assert "Do not write managed `.verifysignal/` artifacts directly" in content


def assert_public_workflow_contract_guidance(content: str) -> None:
    assert "workflow info verifysignal-use-case --json" in content
    assert "stagePayloadContracts" in content
    assert "public workflow contract" in content.lower()
    assert "stage_persistence.py" not in content
    assert "site-packages" not in content


def assert_no_core_contract_snapshots(project: Path) -> None:
    forbidden_roots = [project / ".verifysignal", project / "runtime-cache", project / "user-cache"]
    suspicious_names = {
        "core-contract.json",
        "core-contract.yaml",
        "contracts.json",
        "contracts.yaml",
        "core-executable-contract.json",
        "core-contract-projection.json",
        "core-contract-projection.yaml",
        "core-contract-cache.json",
        "core-contract-cache.yaml",
        "projection-cache.json",
        "projection-cache.yaml",
    }
    offenders: list[str] = []
    for root in forbidden_roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            lower_name = path.name.lower()
            rel = path.relative_to(project)
            if lower_name in suspicious_names or "core-contract" in lower_name or "executable-contract" in lower_name:
                offenders.append(str(rel))
    assert offenders == []


def workspace_file_snapshot(project: Path) -> dict[str, bytes]:
    """Capture project-local workspace files without following symlinks."""
    root = project / ".verifysignal"
    if not root.exists():
        return {}
    if root.is_symlink():
        raise ValueError("Workspace snapshot refuses a symlinked .verifysignal root.")
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file() and not path.is_symlink()
    }


def assert_exact_workspace_file_changes(
    project: Path,
    before: dict[str, bytes],
    *,
    created: Iterable[str] = (),
    changed: Iterable[str] = (),
    removed: Iterable[str] = (),
) -> None:
    """Assert exact path ownership for a workspace mutation."""
    expected_created = _safe_workspace_paths(created)
    expected_changed = _safe_workspace_paths(changed)
    expected_removed = _safe_workspace_paths(removed)
    after = workspace_file_snapshot(project)
    before_paths = set(before)
    after_paths = set(after)
    actual_created = after_paths - before_paths
    actual_removed = before_paths - after_paths
    actual_changed = {
        path
        for path in before_paths & after_paths
        if before[path] != after[path]
    }
    assert actual_created == expected_created
    assert actual_changed == expected_changed
    assert actual_removed == expected_removed


def assert_secret_canary_absent(project: Path, canary: str, *captured_outputs: str) -> None:
    """Scan all workspace files and captured output without echoing the canary."""
    if not canary:
        raise ValueError("Secret canary must be non-empty.")
    canary_bytes = canary.encode("utf-8")
    offenders = [
        f"captured-output[{index}]"
        for index, output in enumerate(captured_outputs)
        if canary in output
    ]
    offenders.extend(
        f".verifysignal/{path}"
        for path, content in workspace_file_snapshot(project).items()
        if canary_bytes in content
    )
    assert offenders == [], f"Secret canary found in project-local outputs: {offenders}"


def _safe_workspace_paths(paths: Iterable[str]) -> set[str]:
    normalized: set[str] = set()
    for value in paths:
        path = Path(value)
        if path.is_absolute() or path.as_posix() == "." or ".." in path.parts:
            raise ValueError("Expected workspace paths must be project-relative.")
        normalized.add(path.as_posix())
    return normalized


def row_by_alias(payload: dict, alias: str) -> dict:
    return next(item for item in payload["useCases"] if item["alias"] == alias)


def assert_compact_readiness_row(row: dict) -> None:
    assert set(["alias", "lastRun", "current", "requirements", "risk"]).issubset(row)
    assert set(["status", "runId"]).issubset(row["lastRun"])
    assert set(["status", "checked", "reasons"]).issubset(row["current"])
    assert set(["runtimeInputs", "credentials", "sideEffectClass", "cleanupPolicy"]).issubset(row["requirements"])
    assert set(["classes", "write", "cleanupPolicy", "requiresConfirmation"]).issubset(row["risk"])


def assert_guided_choices(finding: dict, expected: set[str]) -> None:
    assert expected <= {choice.get("id") for choice in finding.get("guidedChoices", [])}


def assert_secret_safe_bindings(bindings: list[dict]) -> None:
    for binding in bindings:
        assert_no_secret_values(binding)
        assert binding.get("status") in {"prepared", "committed", "discarded"}


def assert_effective_rerun_decision(decision: dict, expected: str) -> None:
    assert decision.get("decision") == expected
    assert decision.get("nextAction")


def assert_placeholder_finding(finding: dict, *, code: str, placeholder: str) -> None:
    assert finding["severity"] == "blocking"
    assert finding["code"] == code
    assert finding["category"] == "side-effect-confirmation"
    assert finding["placeholder"] == placeholder
    assert finding["path"].startswith("sideEffects.confirmationSignals[")
    assert finding.get("nextAction")


def assert_prepared_confirmation_value(document: dict, signal_id: str, field: str, expected: str) -> None:
    policy = document.get("sideEffectPolicy") or document.get("sideEffects") or {}
    signal = next(item for item in policy["confirmationSignals"] if item["id"] == signal_id)
    assert signal[field] == expected
