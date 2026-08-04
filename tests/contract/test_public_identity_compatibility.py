from __future__ import annotations

import re
from pathlib import Path

from verifysignal_spec.repos import SIBLING_IDENTITY
from verifysignal_spec.workspace.layout import WORKSPACE_DIR


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "verifysignal_spec"
SCHEMA_PATTERN = re.compile(r"verifysignal-spec-[a-z0-9-]+/v[0-9]+")

EXPECTED_SCHEMA_IDS = frozenset(
    {
        "verifysignal-spec-artifact-capability-policy/v1",
        "verifysignal-spec-artifact-capability-stamp/v1",
        "verifysignal-spec-authoring-coherence/v1",
        "verifysignal-spec-check/v1",
        "verifysignal-spec-cli-error/v1",
        "verifysignal-spec-core-reset/v1",
        "verifysignal-spec-core-setup/v1",
        "verifysignal-spec-core-update/v1",
        "verifysignal-spec-credential-preparation/v1",
        "verifysignal-spec-credential-readiness-hint/v1",
        "verifysignal-spec-first-run-recommendation/v1",
        "verifysignal-spec-golden-path-workspace-state/v1",
        "verifysignal-spec-guided-first-run/v1",
        "verifysignal-spec-integrations/v1",
        "verifysignal-spec-list/v1",
        "verifysignal-spec-managed-runtime-readiness/v1",
        "verifysignal-spec-metadata-summary/v1",
        "verifysignal-spec-named-outputs/v1",
        "verifysignal-spec-onboarding-guidance/v1",
        "verifysignal-spec-policy-set-result/v1",
        "verifysignal-spec-product-context/v1",
        "verifysignal-spec-readiness-snapshot/v1",
        "verifysignal-spec-refresh-impact/v1",
        "verifysignal-spec-registry/v1",
        "verifysignal-spec-rerun-approval-result/v1",
        "verifysignal-spec-side-effect-lifecycle/v1",
        "verifysignal-spec-stage-payload-contract/v1",
        "verifysignal-spec-stage-payload-contracts/v1",
        "verifysignal-spec-supersede-review-result/v1",
        "verifysignal-spec-supersede-review/v1",
        "verifysignal-spec-understanding-freshness-state/v1",
        "verifysignal-spec-understanding-onboarding-result/v1",
        "verifysignal-spec-use-case/v1",
        "verifysignal-spec-validation-readiness/v1",
        "verifysignal-spec-workflow-artifact-plan/v1",
        "verifysignal-spec-workflow-capability/v1",
        "verifysignal-spec-workflow-info/v1",
        "verifysignal-spec-workflow-list/v1",
        "verifysignal-spec-workflow-migration-result/v1",
        "verifysignal-spec-workflow-prerequisite-check/v1",
        "verifysignal-spec-workflow-run/v1",
        "verifysignal-spec-workflow-show/v1",
        "verifysignal-spec-workflow-stage-persistence-result/v1",
        "verifysignal-spec-workflow-state/v1",
        "verifysignal-spec-workflow-status/v1",
        "verifysignal-spec-workflow-tasks/v1",
        "verifysignal-spec-workspace/v1",
    }
)


def _source_text() -> str:
    paths = sorted(
        path
        for path in SRC.rglob("*")
        if path.is_file() and path.suffix in {".py", ".md", ".yaml"}
    )
    return "\n".join(path.read_text(encoding="utf-8") for path in paths)


def test_all_versioned_spec_schema_identifiers_are_frozen() -> None:
    assert frozenset(SCHEMA_PATTERN.findall(_source_text())) == EXPECTED_SCHEMA_IDS
    assert len(EXPECTED_SCHEMA_IDS) == 47


def test_workspace_environment_role_and_specify_command_remain_compatible() -> None:
    source = _source_text()

    assert WORKSPACE_DIR == ".verifysignal"
    assert "VERIFYSIGNAL_SPEC_DIR" in source
    assert '"spec": Identity' in source
    assert "verifysignal-specify" in source


def test_old_and_canonical_interface_manifests_are_sibling_aliases() -> None:
    assert SIBLING_IDENTITY["spec"].names == ("verifysignal", "verifysignal-spec")


def test_legacy_agent_skill_directories_remain_packaged() -> None:
    skill_root = SRC / "templates" / "agent-skills"
    expected = {
        "verifysignal-spec-author",
        "verifysignal-spec-plan",
        "verifysignal-spec-refine",
        "verifysignal-spec-repair",
        "verifysignal-spec-validate",
    }

    for integration in ("claude", "codex"):
        actual = {
            path.name
            for path in (skill_root / integration).iterdir()
            if path.is_dir() and path.name.startswith("verifysignal-spec-")
        }
        assert actual == expected
