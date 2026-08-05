from __future__ import annotations

import json
import contextlib
import io
import os
import shutil

from verifysignal_spec.commands.validate import run as validate_run
from verifysignal_spec.workspace.models import ArtifactReference, RuntimeInputRequirement, UseCaseRecord
from verifysignal_spec.workspace.repository import init_workspace, save_use_case
from verifysignal_spec.workflows.core_setup import run_core_setup
from verifysignal_spec.workflows.readiness import validation_readiness
from tests.fixtures.workflows.entitlement_preflight_recovery import create_legacy_field_absent_workspace
from tests.fixtures.workflows.main_skill_run_coverage import create_main_skill_coverage_workspace


def test_unreachable_target_blocks_readiness_without_rewriting_artifacts(tmp_path, monkeypatch) -> None:
    from tests.helpers import FAKE_CORE

    monkeypatch.setenv("VERIFYSIGNAL_CORE_CMD", str(FAKE_CORE))
    create_main_skill_coverage_workspace(tmp_path)
    run_request_path = tmp_path / ".verifysignal/run-requests/profile-view-unauth.yaml"
    run_request = json.loads(run_request_path.read_text(encoding="utf-8"))
    run_request["parameters"]["baseUrl"] = "https://"
    run_request_path.write_text(json.dumps(run_request), encoding="utf-8")

    result = validate_run(tmp_path, "profile-view-unauth", runtime_readiness=True, core_cmd=str(FAKE_CORE))

    assert result["status"] == "blocked"
    assert result["runtimeReadiness"]["targetReachabilityStatus"] == "unreachable"
    assert "runtime.target-unreachable" in result["runtimeReadiness"]["findingIds"]
    assert run_request_path.read_text(encoding="utf-8") == json.dumps(run_request)


def test_runtime_readiness_says_full_browser_flow_has_not_executed(tmp_path, monkeypatch) -> None:
    from tests.helpers import FAKE_CORE

    monkeypatch.setenv("VERIFYSIGNAL_CORE_CMD", str(FAKE_CORE))
    create_main_skill_coverage_workspace(tmp_path)

    result = validate_run(tmp_path, "profile-view-unauth", runtime_readiness=True, core_cmd=str(FAKE_CORE))

    assert result["fullBrowserFlowExecuted"] is False
    assert result["runtimeReadiness"]["fullBrowserFlowExecuted"] is False
    assert "full browser flow has not executed" in result["readinessSummary"]


def test_write_runtime_readiness_blocks_when_core_lacks_side_effect_guardrails(tmp_path, monkeypatch) -> None:
    from tests.helpers import FAKE_CORE

    monkeypatch.setenv("VERIFYSIGNAL_CORE_CMD", str(FAKE_CORE))
    monkeypatch.setenv("FAKE_VERIFYSIGNAL_MODE", "contracts-missing-side-effect-guardrails")
    init_workspace(tmp_path, core_cmd=str(FAKE_CORE))
    (tmp_path / ".verifysignal/run-requests").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".verifysignal/skills").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".verifysignal/run-requests/create-resource.yaml").write_text(
        json.dumps(
            {
                "schemaVersion": "qa-run-request/v1",
                "request": {"id": "request.create-resource", "name": "Create Resource"},
                "target": "browser",
                "validationScope": "feature-level",
                "skills": [{"id": "skill.create-resource", "version": "1.0.0"}],
                "parameters": {"baseUrl": "https://example.test"},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / ".verifysignal/skills/create-resource.browser.md").write_text(
        """# Create Resource

```yaml
schemaVersion: qa-skill/v1
skill:
  id: skill.create-resource
  version: 1.0.0
  kind: browser
  name: Create Resource
  description: Create resource.
browser:
  steps:
    - id: open
      action: navigate
      value: "{{parameters.baseUrl}}"
  assertions: []
```
""",
        encoding="utf-8",
    )
    save_use_case(
        tmp_path,
        UseCaseRecord(
            alias="create-resource",
            title="Create Resource",
            description="Create resource.",
            runRequest=ArtifactReference(path=".verifysignal/run-requests/create-resource.yaml", kind="run-request", id="request.create-resource", version="1.0.0"),
            mainSkill=ArtifactReference(path=".verifysignal/skills/create-resource.browser.md", kind="skill", id="skill.create-resource", version="1.0.0"),
            skills=[ArtifactReference(path=".verifysignal/skills/create-resource.browser.md", kind="skill", id="skill.create-resource", version="1.0.0")],
            runtimeInputs=[RuntimeInputRequirement(name="baseUrl", source="default", value="https://example.test")],
            sideEffects={
                "class": "write",
                "commitStepId": "submit-resource",
                "allowed": [{"id": "create-resource", "kind": "network", "methods": ["POST"], "urlContains": "/resources"}],
            },
            rerunPolicy={"afterNoCommit": "allowed", "afterCommit": "blocked"},
        ),
    )

    result = validate_run(tmp_path, "create-resource", runtime_readiness=True, core_cmd=str(FAKE_CORE))

    assert result["status"] == "blocked"
    assert "runtime.side-effect-core-contract-missing" in result["runtimeReadiness"]["findingIds"]


def test_validate_missing_core_blocker_routes_to_setup(tmp_path) -> None:
    create_main_skill_coverage_workspace(
        tmp_path,
        core_cmd="missing-verifysignal-core-runtime",
    )

    result = validate_run(tmp_path, "profile-view-unauth", runtime_readiness=True)

    blocker = next(item for item in result["blockers"] if item["code"] == "core.missing")
    assert result["status"] == "blocked"
    assert blocker["category"] == "environment"
    assert blocker["repairable"] is False
    assert blocker["recoveryCommand"] == "verifysignal core setup --json"


def test_core_setup_success_clears_previous_missing_core_readiness(tmp_path) -> None:
    from tests.helpers import FAKE_CORE

    create_main_skill_coverage_workspace(
        tmp_path,
        core_cmd="missing-verifysignal-core-runtime",
    )

    missing = validation_readiness(tmp_path, alias="profile-view-unauth")
    assert any(item["code"] == "core.missing" for item in missing["blockers"])

    setup = run_core_setup(tmp_path, explicit_core_cmd=str(FAKE_CORE))
    assert setup.status == "ready"

    ready = validation_readiness(tmp_path, alias="profile-view-unauth")
    assert ready["coreReadiness"]["status"] == "available"
    assert not any(item["code"] == "core.missing" for item in ready["blockers"])


def test_validation_readiness_uses_managed_runtime_discovery_not_spec_cli_on_path(tmp_path, monkeypatch) -> None:
    from tests.helpers import FAKE_CORE

    workspace_root = tmp_path / "workspace"
    project = workspace_root / "Demo" / "web-app"
    project.mkdir(parents=True)
    create_main_skill_coverage_workspace(project)
    create_legacy_field_absent_workspace(project)
    shutil.copy2(FAKE_CORE, workspace_root / "verifysignal")
    os.chmod(workspace_root / "verifysignal", 0o755)

    spec_cli_bin = tmp_path / "spec-cli-bin"
    spec_cli_bin.mkdir()
    spec_cli = spec_cli_bin / "verifysignal"
    spec_cli.write_text(
        "#!/usr/bin/env sh\n"
        "echo \"verifysignal: error: argument command: invalid choice: 'version'\" >&2\n"
        "exit 2\n",
        encoding="utf-8",
    )
    os.chmod(spec_cli, 0o755)
    monkeypatch.delenv("VERIFYSIGNAL_CORE_CMD", raising=False)
    monkeypatch.delenv("VERIFYSIGNAL_EMAIL", raising=False)
    monkeypatch.delenv("VERIFYSIGNAL_EMAIL_UNLOCK_TOKEN", raising=False)
    monkeypatch.delenv("VERIFYSIGNAL_ENTITLEMENT_RECEIPT", raising=False)
    monkeypatch.delenv("VERIFYSIGNAL_ENTITLEMENT_PUBLIC_KEYS_JSON", raising=False)
    monkeypatch.delenv("FAKE_VERIFYSIGNAL_MODE", raising=False)
    monkeypatch.setenv("VERIFYSIGNAL_RUNTIME_CACHE_DIR", str(tmp_path / "runtime-cache"))
    monkeypatch.setenv("VERIFYSIGNAL_ENTITLEMENT_RECEIPT_PATH", str(tmp_path / "runtime-cache" / "missing-receipt.json"))
    monkeypatch.setenv("PATH", str(spec_cli_bin) + os.pathsep + os.environ.get("PATH", ""))

    result = validation_readiness(project, alias="profile-view-unauth")

    assert result["status"] == "ready"
    assert result["coreReadiness"]["status"] == "available"
    assert result["coreReadiness"]["coreCommand"] == str(workspace_root / "verifysignal")
    assert not result["blockers"]


def test_run_missing_core_stderr_points_to_setup(tmp_path) -> None:
    create_main_skill_coverage_workspace(
        tmp_path,
        core_cmd="missing-verifysignal-core-run",
    )

    code, _out, err = _cli([
        "run",
        "profile-view-unauth",
        "--project",
        str(tmp_path),
        "--json",
        "--non-interactive",
    ])

    assert code == 3
    assert "verifysignal core setup --json" in err


def _cli(args: list[str]) -> tuple[int, str, str]:
    from verifysignal_spec.cli import main

    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = main(args)
    return code, stdout.getvalue(), stderr.getvalue()
