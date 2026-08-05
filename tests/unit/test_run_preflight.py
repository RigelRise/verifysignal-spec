from __future__ import annotations

from pathlib import Path

import pytest

from tests.fixtures.workflows.entitlement_preflight_recovery import (
    build_protected_readiness_snapshot,
)
from tests.fixtures.workflows.prerequisites import create_current_understanding_workspace
from tests.fixtures.workflows.side_effect_contract_alignment import create_write_policy_workspace
from tests.helpers import FAKE_CORE
from verifysignal_spec.commands import run as run_command
from verifysignal_spec.runtime.models import ManagedRuntimeReadinessResult
from verifysignal_spec.workspace import layout
from verifysignal_spec.workspace.models import ArtifactReference
from verifysignal_spec.workspace.repository import (
    artifact_fingerprints,
    load_readiness_snapshot,
    load_use_case,
    now_iso,
    save_document,
    save_use_case,
)
from verifysignal_spec.workflows.prerequisites import check_prerequisites


@pytest.mark.parametrize(
    ("record_status", "protected_status", "readiness_scope", "expected_code"),
    [
        ("blocked", "passed", "protected-operation", "workflow.prerequisite-missing"),
        ("ready", "not-checked", "command-and-trust-inputs", "runtime.protected-readiness-required"),
    ],
)
def test_direct_run_and_workflow_check_share_blocked_preflight_before_runtime_resolution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    record_status: str,
    protected_status: str,
    readiness_scope: str,
    expected_code: str,
) -> None:
    """A local metadata blocker must be identical at both run entry points.

    Runtime resolution is deliberately spied here because resolving a command is
    already too late: blocked run metadata must be decided without consulting
    Core, dotenv files, generated inputs, or prepared artifacts.
    """

    alias = _prepare_run_workspace(
        tmp_path,
        monkeypatch,
        record_status=record_status,
        protected_status=protected_status,
        readiness_scope=readiness_scope,
    )
    calls = {"runtimeResolution": 0}

    def resolve_runtime(*_args: object, **_kwargs: object) -> ManagedRuntimeReadinessResult:
        calls["runtimeResolution"] += 1
        return ManagedRuntimeReadinessResult(
            status="ready",
            source="explicit",
            runtimeCommand=str(FAKE_CORE),
            runtimeVersion="0.1.0",
            contractVersion="verifysignal-public-cli-json/v1",
        )

    monkeypatch.setattr(run_command, "ensure_core_runtime", resolve_runtime)

    workflow_result = check_prerequisites(tmp_path, "run", alias=alias)
    direct_result = run_command.run(
        tmp_path,
        alias,
        interactive=False,
        core_cmd=str(FAKE_CORE),
    )

    assert workflow_result["canProceed"] is False
    assert direct_result["status"] == "blocked"
    assert _blocker_codes(workflow_result) == [expected_code]
    assert _blocker_codes(direct_result) == [expected_code]
    assert calls == {"runtimeResolution": 0}


def test_stale_artifact_fingerprint_blocks_both_entry_points_before_runtime_resolution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    alias = _prepare_run_workspace(
        tmp_path,
        monkeypatch,
        record_status="ready",
        protected_status="passed",
        readiness_scope="protected-operation",
    )
    record = load_use_case(tmp_path, alias)
    snapshot = load_readiness_snapshot(tmp_path, alias)
    assert snapshot is not None
    snapshot.artifactFingerprints = artifact_fingerprints(tmp_path, record)
    save_document(layout.readiness_snapshot_path(tmp_path, alias), snapshot.to_dict())
    main_skill = tmp_path / record.mainSkill.path
    main_skill.write_text(
        main_skill.read_text(encoding="utf-8") + "\n<!-- changed after validation -->\n",
        encoding="utf-8",
    )
    calls = _install_runtime_resolution_spy(monkeypatch)

    workflow_result = check_prerequisites(tmp_path, "run", alias=alias)
    direct_result = run_command.run(
        tmp_path,
        alias,
        interactive=False,
        core_cmd=str(FAKE_CORE),
    )

    assert _blocker_codes(workflow_result) == ["runtime.protected-readiness-required"]
    assert _blocker_codes(direct_result) == ["runtime.protected-readiness-required"]
    assert calls == {"runtimeResolution": 0}


def test_missing_source_only_skill_blocks_both_entry_points_before_runtime_resolution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    alias = _prepare_run_workspace(
        tmp_path,
        monkeypatch,
        record_status="ready",
        protected_status="passed",
        readiness_scope="protected-operation",
    )
    record = load_use_case(tmp_path, alias)
    record.sourceOnlySkills.append(
        ArtifactReference(
            path=".verifysignal/skills/missing-source-only.browser.md",
            kind="skill",
            id="skill.missing-source-only",
        )
    )
    save_use_case(tmp_path, record)
    calls = _install_runtime_resolution_spy(monkeypatch)

    workflow_result = check_prerequisites(tmp_path, "run", alias=alias)
    direct_result = run_command.run(
        tmp_path,
        alias,
        interactive=False,
        core_cmd=str(FAKE_CORE),
    )

    assert _blocker_codes(workflow_result) == ["workflow.prerequisite-missing"]
    assert _blocker_codes(direct_result) == ["workflow.prerequisite-missing"]
    assert calls == {"runtimeResolution": 0}


def test_unknown_side_effect_class_blocks_both_entry_points_before_runtime_resolution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    alias = _prepare_run_workspace(
        tmp_path,
        monkeypatch,
        record_status="ready",
        protected_status="passed",
        readiness_scope="protected-operation",
    )
    record = load_use_case(tmp_path, alias)
    record.sideEffects = {"class": "unknown", "mode": "observe"}
    save_use_case(tmp_path, record)
    calls = _install_runtime_resolution_spy(monkeypatch)

    workflow_result = check_prerequisites(tmp_path, "run", alias=alias)
    direct_result = run_command.run(
        tmp_path,
        alias,
        interactive=False,
        core_cmd=str(FAKE_CORE),
    )

    expected = ["runtime.side-effect-class-unknown"]
    assert _blocker_codes(workflow_result) == expected
    assert _blocker_codes(direct_result) == expected
    assert calls == {"runtimeResolution": 0}


def _prepare_run_workspace(
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    record_status: str,
    protected_status: str,
    readiness_scope: str,
) -> str:
    monkeypatch.setenv("VERIFYSIGNAL_CORE_CMD", str(FAKE_CORE))
    monkeypatch.setenv("FAKE_VERIFYSIGNAL_MODE", "ok")
    monkeypatch.setenv("VERIFYSIGNAL_RUNTIME_CACHE_DIR", str(project / "runtime-cache"))
    create_current_understanding_workspace(project)
    record = create_write_policy_workspace(project)
    record.status = record_status
    record.artifactCapabilities = {
        "capabilities": [
            "explicit-confirmation",
            "generated-runtime-inputs",
            "resource-identity",
            "side-effect-lifecycle",
            "write-activity-interpretation",
        ]
    }
    record.rerunPolicy = {
        "afterNoCommit": "allowed",
        "afterCommit": "blocked",
        "afterUnknown": "requires-confirmation",
    }
    save_use_case(project, record)
    readiness = build_protected_readiness_snapshot(
        record.alias,
        status="ready",
        protected_status=protected_status,
        readiness_scope=readiness_scope,
        side_effect_class="write",
    )
    readiness["checkedAt"] = now_iso()
    save_document(layout.readiness_snapshot_path(project, record.alias), readiness)
    workflow_root = layout.workflow_use_case_dir(project, record.alias)
    workflow_root.mkdir(parents=True, exist_ok=True)
    for stage in ("spec", "plan", "tasks"):
        (workflow_root / f"{stage}.md").write_text(f"# {stage}\n", encoding="utf-8")
        if stage != "spec":
            (workflow_root / f"{stage}.yaml").write_text("{}\n", encoding="utf-8")
    return record.alias


def _blocker_codes(result: dict[str, object]) -> list[str]:
    blockers = result.get("blockers")
    if not isinstance(blockers, list):
        return []
    return [str(item.get("code")) for item in blockers if isinstance(item, dict)]


def _install_runtime_resolution_spy(
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, int]:
    calls = {"runtimeResolution": 0}

    def resolve_runtime(*_args: object, **_kwargs: object) -> ManagedRuntimeReadinessResult:
        calls["runtimeResolution"] += 1
        return ManagedRuntimeReadinessResult(
            status="ready",
            source="explicit",
            runtimeCommand=str(FAKE_CORE),
            runtimeVersion="0.1.0",
            contractVersion="verifysignal-public-cli-json/v1",
        )

    monkeypatch.setattr(run_command, "ensure_core_runtime", resolve_runtime)
    return calls
