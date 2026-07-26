from __future__ import annotations

from pathlib import Path

from verifysignal_spec.workflows.stage_contracts import stage_contracts_payload


ROOT = Path(__file__).resolve().parents[2]


def test_public_workflow_contract_advertises_browser_first_understanding_v1() -> None:
    contracts = stage_contracts_payload()

    assert "understand" in contracts["stages"]
    understand = contracts["byStage"]["understand"]
    assert understand["requiredFields"] == ["coverageInventory"]
    for field in [
        "understandingMode",
        "productSummary",
        "targetEnvironment",
        "explorationScope",
        "productSignals",
        "repositorySummary",
        "localStartInstructions",
        "gaps",
    ]:
        assert field in understand["optionalFields"]

    browser = contracts["browserFirstUnderstanding"]
    assert browser["capability"] == "browser-first-understanding/v1"
    assert browser["modes"] == ["repository", "browser-first", "hybrid"]
    assert browser["defaults"]["maxPagesOrStates"] == 20
    assert browser["defaults"]["maxDepth"] == 3
    assert browser["defaults"]["candidateRange"] == {"minimum": 3, "maximum": 5}
    assert browser["defaults"]["softTimeBudgetMinutes"] == 15
    assert browser["mapping"]["readSafeOnly"] is True
    assert browser["authentication"]["default"] == "assisted-headed"
    assert browser["browserLifecycle"]["close"] == "after-user-acknowledgement"
    assert browser["proofHandoff"]["potentiallyMutating"] == "explicit-confirmation-plus-public-probe"
    assert browser["proofHandoff"]["probeSchema"] == "verifysignal.probe/v1"
    assert "rawDom" in browser["forbiddenPersistence"]
    assert browser["providerBoundary"] == "playwright-mcp-or-equivalent-host-browser"


def test_repository_contract_remains_supported_by_mode_specific_requirements() -> None:
    browser = stage_contracts_payload()["browserFirstUnderstanding"]

    assert browser["modeRequirements"]["repository"] == [
        "repositorySummary",
        "localStartInstructions",
        "coverageInventory",
        "generatedGitHash or gitUnavailableReason",
    ]
    assert "targetEnvironment" in browser["modeRequirements"]["browser-first"]
    assert "productSignals" in browser["modeRequirements"]["hybrid"]


def test_mutating_proof_requires_exact_public_probe_and_blocks_legacy_fallback() -> None:
    command = (
        ROOT
        / "src/verifysignal_spec/templates/agent-commands/verifysignal.understand.md"
    ).read_text(encoding="utf-8")
    flattened = " ".join(command.split())

    assert "exact public `verifysignal.probe/v1` support" in flattened
    assert "verifysignal core version --json" in flattened
    assert "`data.operations`" in flattened
    assert "verifysignal probe <run-request> --skill <main-skill> --json" in flattened
    assert "probe must not commit" in flattened
    assert "public Core capability is missing" in flattened
    assert "preserve the candidate and report the exact partial/blocked prerequisite" in flattened
    assert "Do not claim proof" in flattened
