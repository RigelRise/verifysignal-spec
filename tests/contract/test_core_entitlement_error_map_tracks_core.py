"""Cross-repo ratchet: Spec's Core-entitlement error map must track the codes Core actually emits.

CORE_ENTITLEMENT_ERROR_MAP is a hand-maintained mirror of every ``entitlement.*`` rejection code Core
emits, each translated to a Spec-facing code. Nothing compared it to Core, and it had already drifted
both ways: Core emits ``entitlement.trust-key-context-disallowed`` (absent from the map, so it fell
through to a generic message) and the map carried ``entitlement.runtime-mismatch`` which Core never
emits (a dead translation). Declared-to-mirror-Core, never compared to it — the same class as the
release-golden drift.

This reads Core's entitlement source when the sibling repo resolves (a dev checkout has both, and that
is where the map is edited) and fails on any divergence. The local check runs regardless, so it is
never a no-op. The authoritative cross-repo gate is CI, still pending.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from verifysignal_spec.core.contracts import CORE_ENTITLEMENT_ERROR_MAP
from verifysignal_spec.repos import resolve_sibling_repo

SPEC_REPOSITORY = Path(__file__).resolve().parents[2]
CORE_REPOSITORY = resolve_sibling_repo("core", SPEC_REPOSITORY)
CORE_ENTITLEMENT_SRC = (
    CORE_REPOSITORY / "apps" / "verifysignal-cli" / "src" / "entitlement"
    if CORE_REPOSITORY is not None
    else SPEC_REPOSITORY / ".missing-core-entitlement-source"
)


def _core_emitted_codes() -> set[str]:
    codes: set[str] = set()
    for path in CORE_ENTITLEMENT_SRC.rglob("*.ts"):
        if path.name.endswith(".test.ts"):
            continue
        codes |= set(re.findall(r'"(entitlement\.[a-z-]+)"', path.read_text("utf-8")))
    return codes


def test_error_map_tracks_exactly_the_codes_core_emits() -> None:
    if not CORE_ENTITLEMENT_SRC.is_dir():
        pytest.skip(
            f"Core sibling not resolvable at {CORE_ENTITLEMENT_SRC}; cross-repo error-map identity NOT checked here "
            "— the authoritative gate is CI."
        )
    emitted = _core_emitted_codes()
    # Anti-vacuity: the scrape must see a real catalog, or an empty set would make every check pass.
    assert len(emitted) >= 10, f"extraction found only {len(emitted)} codes — the scrape or Core's source layout moved"

    mapped = set(CORE_ENTITLEMENT_ERROR_MAP)
    missing = emitted - mapped
    dead = mapped - emitted
    assert not missing, f"Core emits entitlement codes Spec does not map (they fall through to a generic message): {sorted(missing)}"
    assert not dead, f"Spec maps entitlement codes Core never emits (dead translations): {sorted(dead)}"


def test_every_mapped_value_is_a_well_formed_spec_code() -> None:
    # Local invariant — runs even in a Spec-only checkout, so this file is never a pure no-op.
    assert CORE_ENTITLEMENT_ERROR_MAP, "the error map is empty"
    for source, target in CORE_ENTITLEMENT_ERROR_MAP.items():
        assert re.fullmatch(r"entitlement\.[a-z-]+", source), f"malformed Core code key: {source!r}"
        assert re.fullmatch(r"(entitlement|core)\.[a-z-]+", target), f"malformed Spec-facing code: {target!r}"
