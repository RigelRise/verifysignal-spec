from __future__ import annotations

from verifysignal_spec.core.contracts import REQUIRED_OPERATIONS, core_supports_probe
from verifysignal_spec.runtime.resolver import CONTEXT_REQUIRED_CAPABILITY, OPTIONAL_CAPABILITY_PROBES


def test_probe_is_optional_but_registered_for_capability_gating() -> None:
    assert "probe" not in REQUIRED_OPERATIONS
    assert CONTEXT_REQUIRED_CAPABILITY["probe"] == "probe"
    assert OPTIONAL_CAPABILITY_PROBES["probe"] is core_supports_probe


def test_probe_requires_exact_public_schema_and_version() -> None:
    assert core_supports_probe(
        {
            "data": {
                "operations": [
                    {
                        "name": "probe",
                        "schema": "verifysignal.probe/v1",
                        "schemaVersion": 1,
                    }
                ]
            }
        }
    )
    assert not core_supports_probe(
        {
            "data": {
                "operations": [
                    {
                        "name": "probe",
                        "schema": "verifysignal.probe/v1",
                        "schemaVersion": 2,
                    }
                ]
            }
        }
    )
