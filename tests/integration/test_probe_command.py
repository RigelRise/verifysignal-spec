from __future__ import annotations

import os
from pathlib import Path

import pytest

from helpers import CliTestCase

from verifysignal_spec.commands import probe as probe_command
from verifysignal_spec.core.adapter import CoreAdapter
from verifysignal_spec.core.contracts import core_supports_probe
from verifysignal_spec.core.executable_contract import project_core_contract
from verifysignal_spec.workflows.browser_authoring import browser_authoring_contract
from verifysignal_spec.workflows.readiness import executable_contract_blockers


class ProbeCommandTests(CliTestCase):
    def _artifacts(self) -> tuple[Path, Path]:
        run_request = self.project / "request.yaml"
        skill = self.project / "project.browser.md"
        run_request.write_text(
            """schemaVersion: qa-run-request/v1
request:
  id: request.project
  name: Project
target: browser
validationScope: feature-level
sideEffectPolicy:
  class: write
  mode: enforce
  commitStepId: publish
""",
            encoding="utf-8",
        )
        skill.write_text("# project\n", encoding="utf-8")
        return run_request, skill

    def test_probe_routes_through_capability_gated_runtime_and_returns_boundary(self) -> None:
        run_request, skill = self._artifacts()
        os.environ["FAKE_VERIFYSIGNAL_MODE"] = "advertises-probe"
        try:
            result = probe_command.run(
                self.project,
                run_request,
                [skill],
                core_cmd=str(os.environ["VERIFYSIGNAL_CORE_CMD"]),
            )
        finally:
            os.environ.pop("FAKE_VERIFYSIGNAL_MODE", None)

        self.assertEqual(result["operation"], "probe")
        self.assertEqual(result["status"], "passed")
        self.assertTrue(result["data"]["boundary"]["reached"])
        self.assertFalse(result["data"]["boundary"]["executed"])
        self.assertFalse(result["data"]["fullFlowExecuted"])

    def test_probe_blocks_accurately_when_core_is_compatible_but_lacks_probe(self) -> None:
        run_request, skill = self._artifacts()
        result = probe_command.run(
            self.project,
            run_request,
            [skill],
            core_cmd=str(os.environ["VERIFYSIGNAL_CORE_CMD"]),
        )

        self.assertEqual(result["status"], "blocked")
        blockers = result["managedRuntimeReadiness"]["blockers"]
        self.assertTrue(any(item["code"] == "core.probe-unsupported" for item in blockers))

    def test_probe_cli_threads_artifacts_and_runtime_options(self) -> None:
        run_request, skill = self._artifacts()
        os.environ["FAKE_VERIFYSIGNAL_MODE"] = "advertises-probe"
        try:
            code, out, err = self.cli(
                [
                    "probe",
                    str(run_request),
                    "--skill",
                    str(skill),
                    "--project",
                    str(self.project),
                    "--core-cmd",
                    str(os.environ["VERIFYSIGNAL_CORE_CMD"]),
                    "--headed",
                    "--slow-mo",
                    "125",
                    "--json",
                ]
            )
        finally:
            os.environ.pop("FAKE_VERIFYSIGNAL_MODE", None)

        self.assertEqual(code, 0, err)
        self.assertIn('"operation": "probe"', out)
        self.assertIn('"executed": false', out)


REAL_CORE_REPOSITORY = Path(
    os.environ.get(
        "VERIFYSIGNAL_REAL_CORE_REPOSITORY",
        str(Path(__file__).resolve().parents[3] / "verifysignal"),
    )
).expanduser()


@pytest.mark.skipif(
    not (REAL_CORE_REPOSITORY / "package.json").exists(),
    reason="Sibling VerifySignal Core repository is not available.",
)
def test_sibling_core_advertises_probe_only_through_the_public_version_contract() -> None:
    response = CoreAdapter(executable=str(REAL_CORE_REPOSITORY)).version()

    assert response["data"]["verifysignalVersion"] == "0.6.1"
    assert core_supports_probe(response)


@pytest.mark.skipif(
    not (REAL_CORE_REPOSITORY / "package.json").exists(),
    reason="Sibling VerifySignal Core repository is not available.",
)
def test_sibling_core_exposes_required_browser_authoring_guardrails_via_public_contract() -> None:
    adapter = CoreAdapter(executable=str(REAL_CORE_REPOSITORY))
    version = adapter.version()["data"]["verifysignalVersion"]
    projection = project_core_contract(
        adapter.contracts(),
        runtime_identity=str(REAL_CORE_REPOSITORY),
        core_version=version,
    )

    authoring = browser_authoring_contract(core_contract=projection)
    warnings = {
        item["code"]: item
        for item in authoring["authoringWarnings"]
    }

    assert warnings["degenerate-text-target"]["runtimeReadinessSeverity"] == "blocking"
    assert warnings["unstable-generated-css-target"]["runtimeReadinessSeverity"] == "blocking"
    assert executable_contract_blockers(
        REAL_CORE_REPOSITORY,
        str(REAL_CORE_REPOSITORY),
        core_contract=projection,
    ) == []
