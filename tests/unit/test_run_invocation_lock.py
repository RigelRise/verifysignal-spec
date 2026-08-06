from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import pytest

from verifysignal_spec.workspace.models import LastCoreAttempt
from verifysignal_spec.workspace.repository import (
    LastCoreAttemptOwnershipError,
    clear_last_core_attempt,
    create_default_use_case,
    load_use_case,
    save_last_core_attempt,
    save_use_case,
)
from verifysignal_spec.workflows.run_lock import acquire_run_invocation_lease


def test_run_invocation_lease_is_exclusive_per_project_alias(
    tmp_path: Path,
) -> None:
    first = acquire_run_invocation_lease(tmp_path, "localized-home")
    assert first is not None
    other_alias = None
    reacquired = None
    try:
        assert acquire_run_invocation_lease(tmp_path, "localized-home") is None
        other_alias = acquire_run_invocation_lease(tmp_path, "other-use-case")
        assert other_alias is not None
    finally:
        if other_alias is not None:
            other_alias.release()
        first.release()

    try:
        reacquired = acquire_run_invocation_lease(tmp_path, "localized-home")
        assert reacquired is not None
    finally:
        if reacquired is not None:
            reacquired.release()


def test_run_invocation_lease_is_released_when_holder_process_terminates(
    tmp_path: Path,
) -> None:
    source_root = Path(__file__).resolve().parents[2] / "src"
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join(
        [str(source_root), environment.get("PYTHONPATH", "")]
    ).rstrip(os.pathsep)
    script = """
from pathlib import Path
import sys
from verifysignal_spec.workflows.run_lock import acquire_run_invocation_lease

lease = acquire_run_invocation_lease(Path(sys.argv[1]), sys.argv[2])
if lease is None:
    raise SystemExit(2)
print("locked", flush=True)
sys.stdin.read()
"""
    child = subprocess.Popen(
        [sys.executable, "-c", script, str(tmp_path), "localized-home"],
        env=environment,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    parent_lease = None
    try:
        assert child.stdout is not None
        assert child.stdout.readline().strip() == "locked"
        assert acquire_run_invocation_lease(tmp_path, "localized-home") is None
        child.terminate()
        child.wait(timeout=10)
        parent_lease = acquire_run_invocation_lease(tmp_path, "localized-home")
        assert parent_lease is not None
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=10)
        if parent_lease is not None:
            parent_lease.release()


@pytest.mark.skipif(os.name != "posix", reason="POSIX directory-lock semantics")
def test_run_invocation_lease_survives_identity_directory_replacement(
    tmp_path: Path,
) -> None:
    source_root = Path(__file__).resolve().parents[2] / "src"
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join(
        [str(source_root), environment.get("PYTHONPATH", "")]
    ).rstrip(os.pathsep)
    alias = "localized-home"
    first = acquire_run_invocation_lease(tmp_path, alias)
    assert first is not None
    identity_dir = tmp_path / ".verifysignal" / ".run-locks" / alias
    displaced_identity_dir = identity_dir.with_name(f"{alias}-displaced")
    identity_dir.rename(displaced_identity_dir)
    script = """
from pathlib import Path
import sys
from verifysignal_spec.workflows.run_lock import acquire_run_invocation_lease

lease = acquire_run_invocation_lease(Path(sys.argv[1]), sys.argv[2])
if lease is None:
    print("blocked")
else:
    print("acquired")
    lease.release()
"""

    try:
        contender = subprocess.run(
            [sys.executable, "-c", script, str(tmp_path), alias],
            env=environment,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
    finally:
        first.release()

    assert contender.stdout.strip() == "blocked"


def test_last_core_attempt_replacement_and_clear_require_exact_ownership(
    tmp_path: Path,
) -> None:
    record = create_default_use_case(tmp_path, "localized-home", "Localized home")
    save_use_case(tmp_path, record)
    first = _attempt("2026-08-05T01:00:00.000000001Z")
    second = _attempt("2026-08-05T01:00:00.000000002Z")
    save_last_core_attempt(tmp_path, record.alias, first)

    with pytest.raises(LastCoreAttemptOwnershipError):
        save_last_core_attempt(
            tmp_path,
            record.alias,
            second,
            expected_attempted_at="2026-08-05T01:00:00.000000000Z",
        )
    with pytest.raises(LastCoreAttemptOwnershipError):
        clear_last_core_attempt(
            tmp_path,
            record.alias,
            expected_attempted_at="2026-08-05T01:00:00.000000000Z",
        )
    assert load_use_case(tmp_path, record.alias).lastCoreAttempt == first

    save_last_core_attempt(
        tmp_path,
        record.alias,
        second,
        expected_attempted_at=first.attemptedAt,
    )
    assert load_use_case(tmp_path, record.alias).lastCoreAttempt == second
    clear_last_core_attempt(
        tmp_path,
        record.alias,
        expected_attempted_at=second.attemptedAt,
    )
    assert load_use_case(tmp_path, record.alias).lastCoreAttempt is None


def _attempt(attempted_at: str) -> LastCoreAttempt:
    return LastCoreAttempt(
        attemptedAt=attempted_at,
        operation="run",
        schema=None,
        status="unknown",
        errorCode=None,
        executionState="unknown",
        sideEffectMayExist=True,
    )
