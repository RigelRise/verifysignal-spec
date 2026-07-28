"""Cross-repo ratchet: Spec's REQUIRED_OPERATIONS must match Core's published operation contract.

REQUIRED_OPERATIONS is a hand-written mirror of Core's public operation table — each operation Spec
requires, with the schema name and version Core advertises for it. validate_version_response enforces
this mirror against a Core `version` payload at runtime, but Spec's own tests only ever run it against
a self-authored fake whose schema names are ALSO hand-typed in this repo to match. Nothing read Core's
real public-contract.ts, so a Core rename or version bump (report-inspection/v1 -> v2) would leave the
mirror and the fake stale together while Spec's suite stayed green and the real Core binary advertised
a contract Spec would reject as incompatible. Declared-to-mirror-Core, never compared to it.

This resolves Core's authoritative op -> (schema, version) table from public-contract.ts when the
sibling repo is present (a dev checkout, where the mirror is edited) and fails on any divergence for
the operations Spec requires. The local well-formedness check runs regardless. Authoritative gate: CI.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from verifysignal_spec.core.contracts import REQUIRED_OPERATIONS

CORE_REPOSITORY = Path(
    os.environ.get(
        "VERIFYSIGNAL_REAL_CORE_REPOSITORY",
        str(Path(__file__).resolve().parents[3] / "verifysignal"),
    )
).expanduser()
CORE_PUBLIC_CONTRACT = (
    CORE_REPOSITORY
    / "apps"
    / "verifysignal-cli"
    / "src"
    / "output"
    / "public-contract.ts"
)


def _core_operation_table() -> dict[str, tuple[str, int]]:
    """op display-name -> (schema string, schema version), resolved from public-contract.ts."""
    source = CORE_PUBLIC_CONTRACT.read_text("utf-8")

    schemas_block = re.search(r"export const publicSchemas = \{(.*?)\} as const;", source, re.DOTALL)
    assert schemas_block, "could not locate publicSchemas in Core public-contract.ts"
    schema_by_key = dict(re.findall(r"(\w+):\s*\"([^\"]+)\"", schemas_block.group(1)))

    table: dict[str, tuple[str, int]] = {}
    for name, schema_key, version in re.findall(
        r"\{\s*name:\s*\"([^\"]+)\",\s*schema:\s*publicSchemas\.(\w+),\s*schemaVersion:\s*(\d+)",
        source,
    ):
        assert schema_key in schema_by_key, f"operation {name} references unknown publicSchemas.{schema_key}"
        table[name] = (schema_by_key[schema_key], int(version))
    return table


def test_required_operations_match_cores_published_contract() -> None:
    if not CORE_PUBLIC_CONTRACT.is_file():
        pytest.skip(
            f"Core sibling not resolvable at {CORE_PUBLIC_CONTRACT}; cross-repo operation-contract identity NOT "
            "checked here — the authoritative gate is CI."
        )
    core = _core_operation_table()
    # Anti-vacuity: the parse must have found a real table with the operations Spec requires.
    assert len(core) >= len(REQUIRED_OPERATIONS), f"parsed only {len(core)} Core operations — the scrape or source moved"

    mismatches = []
    for name, (schema, version) in REQUIRED_OPERATIONS.items():
        if name not in core:
            mismatches.append(f"{name}: Core no longer advertises this operation")
        elif core[name] != (schema, version):
            mismatches.append(f"{name}: Spec mirrors {(schema, version)} but Core advertises {core[name]}")
    assert not mismatches, "REQUIRED_OPERATIONS has drifted from Core's published contract: " + "; ".join(mismatches)


def test_required_operations_is_well_formed() -> None:
    # Local invariant — never a no-op even without the Core sibling.
    assert REQUIRED_OPERATIONS, "REQUIRED_OPERATIONS is empty"
    for name, entry in REQUIRED_OPERATIONS.items():
        assert re.fullmatch(r"[a-z.-]+", name), f"malformed operation name: {name!r}"
        schema, version = entry
        assert re.fullmatch(r"verifysignal\.[a-z-]+/v\d+", schema), f"malformed schema: {schema!r}"
        assert isinstance(version, int) and version >= 1
