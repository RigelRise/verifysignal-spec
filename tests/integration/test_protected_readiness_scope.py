from __future__ import annotations

from pathlib import Path

from tests.fixtures.workflows.main_skill_run_coverage import (
    ALIAS,
    create_main_skill_coverage_workspace,
)
from tests.helpers import FAKE_CORE
from verifysignal_spec.commands.validate import run as validate_run
from verifysignal_spec.runtime.resolver import ensure_core_runtime
from verifysignal_spec.workspace import layout
from verifysignal_spec.workspace.repository import (
    load_readiness_snapshot,
    save_document,
)


def _assert_layered_readiness(
    payload: dict[str, object],
    *,
    protected_status: str,
    scope: str,
) -> None:
    assert payload["commandCompatibilityStatus"] == "passed"
    assert payload["trustMaterialStatus"] == "ready"
    assert payload["protectedOperationStatus"] == protected_status
    assert payload["readinessScope"] == scope


def test_compatible_runtime_inputs_do_not_claim_protected_operation_readiness(
    tmp_path: Path,
    monkeypatch,
) -> None:
    create_main_skill_coverage_workspace(tmp_path)
    monkeypatch.delenv("FAKE_VERIFYSIGNAL_MODE", raising=False)

    readiness = ensure_core_runtime(
        tmp_path,
        explicit_core_cmd=str(FAKE_CORE),
        context="validate",
    ).to_dict()

    assert readiness["status"] == "ready"
    _assert_layered_readiness(
        readiness,
        protected_status="not-checked",
        scope="command-and-trust-inputs",
    )


def test_protected_authoring_pass_upgrades_readiness_scope_and_snapshot(
    tmp_path: Path,
    monkeypatch,
) -> None:
    create_main_skill_coverage_workspace(tmp_path)
    monkeypatch.delenv("FAKE_VERIFYSIGNAL_MODE", raising=False)

    result = validate_run(
        tmp_path,
        ALIAS,
        runtime_readiness=True,
        core_cmd=str(FAKE_CORE),
    )

    assert result["status"] == "passed"
    assert result["runtimeReadiness"]["status"] == "passed"
    _assert_layered_readiness(
        result["runtimeReadiness"],
        protected_status="passed",
        scope="protected-operation",
    )
    snapshot = load_readiness_snapshot(tmp_path, ALIAS)
    assert snapshot is not None
    assert snapshot.status == "ready"
    assert snapshot.commandCompatibilityStatus == "passed"
    assert snapshot.trustMaterialStatus == "ready"
    assert snapshot.protectedOperationStatus == "passed"
    assert snapshot.readinessScope == "protected-operation"


def test_public_entitlement_error_blocks_protected_scope_with_normalized_code(
    tmp_path: Path,
    monkeypatch,
) -> None:
    create_main_skill_coverage_workspace(tmp_path)
    monkeypatch.setenv("FAKE_VERIFYSIGNAL_MODE", "current-entitlement-error")

    result = validate_run(
        tmp_path,
        ALIAS,
        runtime_readiness=True,
        core_cmd=str(FAKE_CORE),
    )

    assert result["status"] == "blocked"
    assert [item["code"] for item in result["blockers"]] == [
        "entitlement.unverifiable"
    ]
    assert result["runtimeReadiness"]["status"] == "blocked"
    _assert_layered_readiness(
        result["runtimeReadiness"],
        protected_status="blocked",
        scope="protected-operation",
    )
    snapshot = load_readiness_snapshot(tmp_path, ALIAS)
    assert snapshot is not None
    assert snapshot.status == "blocked"
    assert snapshot.protectedOperationStatus == "blocked"
    assert snapshot.readinessScope == "protected-operation"


def test_legacy_readiness_snapshot_decodes_with_conservative_layer_defaults(
    tmp_path: Path,
) -> None:
    create_main_skill_coverage_workspace(tmp_path)
    snapshot_path = layout.readiness_snapshot_path(tmp_path, ALIAS)
    save_document(
        snapshot_path,
        {
            "schemaVersion": "verifysignal-spec-readiness-snapshot/v1",
            "alias": ALIAS,
            "status": "ready",
            "checkedAt": "2026-08-04T00:00:00Z",
            "artifactFingerprints": {},
            "sideEffectClass": "none",
        },
    )

    snapshot = load_readiness_snapshot(tmp_path, ALIAS)

    assert snapshot is not None
    assert snapshot.schemaVersion == "verifysignal-spec-readiness-snapshot/v1"
    assert snapshot.status == "ready"
    assert snapshot.commandCompatibilityStatus == "not-checked"
    assert snapshot.trustMaterialStatus == "not-checked"
    assert snapshot.protectedOperationStatus == "not-checked"
    assert snapshot.readinessScope == "command-and-trust-inputs"
    assert snapshot.to_dict()["protectedOperationStatus"] == "not-checked"
