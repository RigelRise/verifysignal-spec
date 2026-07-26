from __future__ import annotations

from pathlib import Path

import pytest

from tests.fixtures.managed_runtime import write_fake_core_executable
from verifysignal_spec.runtime.resolver import (
    CONTEXT_REQUIRED_CAPABILITY,
    OPTIONAL_CAPABILITY_PROBES,
    capability_blocker_code,
    ensure_core_runtime,
)

# CLASS RATCHET (optional-capability negotiation).
#
# Optional Core operations (`discover`, `crystallize`, ...) are deliberately excluded from
# REQUIRED_OPERATIONS, so a Core can be fully compatible and still not implement them. Invoking one
# regardless crashes inside Core on an unknown subcommand.
#
# The original bug was `discover`-shaped: only the managed-cache branch consulted the capability, so
# the override/env/workspace/PATH, valid-cache, and managed-download paths all resolved `ready` and
# failed later. Fixing just `discover` on just those paths would have left the CLASS open — the next
# optional operation wired up (crystallize) would reintroduce it.
#
# So this guard is parametrized over the REGISTRY rather than over a hand-listed pair of operations:
# every context in CONTEXT_REQUIRED_CAPABILITY must block, with its own capability code, when the
# resolved Core does not advertise the operation. Registering a new optional capability without also
# providing a Core fixture that omits it fails `test_every_registered_capability_has_a_lacking_core_fixture`
# — the guard cannot be silently outgrown.

# capability -> fake-Core mode whose `version` omits exactly that operation.
CORE_LACKING_CAPABILITY = {
    "discover": "ok",  # the default fake Core implements discover but never advertises it
    "crystallize": "omits-crystallize",
    "probe": "ok",
    # run --record/--replay are MODES of run; the default fake Core's run entry has no `modes`,
    # standing in for an older Core that predates the advertisement.
    "run-record": "ok",
    "run-replay": "ok",
}


def test_every_registered_capability_has_a_lacking_core_fixture() -> None:
    # Keeps the parametrization below honest: a newly registered optional capability must come with a
    # Core fixture that lacks it, or this guard fails instead of silently skipping the new capability.
    assert set(OPTIONAL_CAPABILITY_PROBES) == set(CORE_LACKING_CAPABILITY)
    assert set(CONTEXT_REQUIRED_CAPABILITY.values()) <= set(OPTIONAL_CAPABILITY_PROBES)


def test_known_optional_operation_contexts_stay_registered() -> None:
    # The gate below is parametrized over the registry, which auto-covers new capabilities but would
    # silently stop testing one that gets DE-registered (the parametrization would just shrink). Pin
    # the contexts known to invoke an optional operation so removing a gate fails loudly here.
    assert {"discover", "crystallize", "probe"} <= set(CONTEXT_REQUIRED_CAPABILITY)


@pytest.mark.parametrize(("context", "capability"), sorted(CONTEXT_REQUIRED_CAPABILITY.items()))
def test_context_blocks_when_resolved_core_lacks_its_required_capability(
    context: str, capability: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VERIFYSIGNAL_RUNTIME_CACHE_DIR", str(tmp_path / "cache"))
    core = write_fake_core_executable(tmp_path / "bin" / "verifysignal-core", mode=CORE_LACKING_CAPABILITY[capability])
    monkeypatch.setenv("VERIFYSIGNAL_CORE_CMD", str(core))

    result = ensure_core_runtime(tmp_path, context=context)

    assert result.status == "blocked"
    assert any(blocker.code == capability_blocker_code(capability) for blocker in result.blockers), (
        f"context {context!r} resolved a Core lacking {capability!r} without a capability blocker: "
        f"{[blocker.code for blocker in result.blockers]}"
    )


def test_capability_gate_does_not_fire_for_contexts_that_do_not_need_the_operation() -> None:
    # Scope guard. A Core lacking an OPTIONAL operation is still a perfectly good Core for everything
    # else, so only registered contexts may demand it. `run`/`runtime` must not be in the registry —
    # otherwise every pre-crystallize Core becomes unusable for running.
    assert "run" not in CONTEXT_REQUIRED_CAPABILITY
    assert "runtime" not in CONTEXT_REQUIRED_CAPABILITY


@pytest.mark.parametrize("capability", ["run-record", "run-replay"])
def test_run_mode_capability_blocks_only_when_requested(
    capability: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # CONDITIONAL requirement: --record/--replay demand the advertised run mode, but a plain run must
    # keep working against an older Core (the mode gate must not make every old Core unusable).
    monkeypatch.setenv("VERIFYSIGNAL_RUNTIME_CACHE_DIR", str(tmp_path / "cache"))
    lacking = write_fake_core_executable(tmp_path / "bin" / "verifysignal-core", mode="ok")
    monkeypatch.setenv("VERIFYSIGNAL_CORE_CMD", str(lacking))

    blocked = ensure_core_runtime(tmp_path, context="run", required_capability=capability)
    assert blocked.status == "blocked"
    assert any(blocker.code == capability_blocker_code(capability) for blocker in blocked.blockers)

    plain = ensure_core_runtime(tmp_path, context="run")
    assert plain.status == "ready"


@pytest.mark.parametrize("capability", ["run-record", "run-replay"])
def test_run_mode_capability_passes_when_core_advertises_modes(
    capability: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VERIFYSIGNAL_RUNTIME_CACHE_DIR", str(tmp_path / "cache"))
    advertising = write_fake_core_executable(tmp_path / "bin" / "verifysignal-core", mode="advertises-run-modes")
    monkeypatch.setenv("VERIFYSIGNAL_CORE_CMD", str(advertising))

    result = ensure_core_runtime(tmp_path, context="run", required_capability=capability)

    assert result.status == "ready"
