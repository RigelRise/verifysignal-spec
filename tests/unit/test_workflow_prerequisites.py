from __future__ import annotations

import pytest

from verifysignal_spec.workspace.repository import load_document
from verifysignal_spec.workflows.prerequisites import check_prerequisites
from verifysignal_spec.workflows.stage_persistence import persist_stage

from tests.fixtures.workflows.browser_first_understanding import browser_understanding_payload
from tests.fixtures.workflows.prerequisites import create_missing_understanding_workspace


def test_missing_understanding_blocks_specify(tmp_path) -> None:
    create_missing_understanding_workspace(tmp_path)
    result = check_prerequisites(tmp_path, "specify")
    assert result["status"] == "missing"
    assert result["canProceed"] is False
    assert result["requiresConfirmation"] is False
    assert ".verifysignal/workflows/understanding.md" in result["missingArtifacts"]
    assert ".verifysignal/product-context.yaml" in result["missingArtifacts"]
    assert result["nextCommand"] == "/verifysignal-understand"


def test_understand_and_list_do_not_require_repository_understanding(tmp_path) -> None:
    create_missing_understanding_workspace(tmp_path)
    assert check_prerequisites(tmp_path, "understand")["status"] == "ready"
    assert check_prerequisites(tmp_path, "list")["status"] == "ready"


def test_invalid_alias_uses_path_safe_alias_rules(tmp_path) -> None:
    create_missing_understanding_workspace(tmp_path)
    with pytest.raises(ValueError, match="Alias must be lowercase path-safe"):
        check_prerequisites(tmp_path, "clarify", alias="../bad")


def test_browser_first_understanding_is_current_without_git_metadata(tmp_path) -> None:
    result = persist_stage(
        tmp_path,
        "understand",
        scope="all",
        payload=browser_understanding_payload(),
    )
    assert result["status"] == "persisted"

    context = load_document(tmp_path / ".verifysignal/product-context.yaml", default={})
    assert context["understanding"]["generatedGitHash"] is None
    assert context["understanding"]["gitAvailable"] is False

    readiness = check_prerequisites(tmp_path, "specify")
    assert readiness["status"] == "ready"
    assert readiness["canProceed"] is True
