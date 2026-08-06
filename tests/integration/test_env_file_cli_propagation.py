from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from verifysignal_spec.cli import main
from verifysignal_spec.commands import probe, run, validate
from verifysignal_spec.workspace.models import ArtifactReference, UseCaseRecord
from verifysignal_spec.workspace.repository import init_workspace, save_use_case
from tests.fixtures.workflows.entitlement_preflight_recovery import save_protected_ready_snapshot
from verifysignal_spec.workflows.engine import create_workflow_run
from verifysignal_spec.workflows.transitions import transition_workflow


def _record(alias: str = "credential-flow") -> UseCaseRecord:
    return UseCaseRecord(
        alias=alias,
        title="Credential flow",
        description="Fixture.",
        runRequest=ArtifactReference(
            path=f".verifysignal/run-requests/{alias}.yaml",
            kind="run-request",
        ),
        mainSkill=ArtifactReference(
            path=f".verifysignal/skills/{alias}.browser.md",
            kind="skill",
        ),
        credentialRefs={
            "user": {
                "source": "environment",
                "keys": {"email": "TEST_USER_EMAIL"},
            }
        },
    )


@pytest.mark.parametrize("command", ["validate", "probe", "run"])
def test_explicit_env_file_blocks_undeclared_keys_before_core_invocation(
    tmp_path,
    monkeypatch,
    capsys,
    command: str,
) -> None:
    init_workspace(tmp_path)
    record = _record()
    save_use_case(tmp_path, record)
    run_request = tmp_path / record.runRequest.path
    skill = tmp_path / record.mainSkill.path
    run_request.parent.mkdir(parents=True, exist_ok=True)
    skill.parent.mkdir(parents=True, exist_ok=True)
    run_request.write_text(
        json.dumps(
            {
                "schemaVersion": "qa-run-request/v1",
                "credentialRefs": record.credentialRefs,
            }
        ),
        encoding="utf-8",
    )
    skill.write_text("# fixture\n", encoding="utf-8")
    if command == "run":
        record.status = "ready"
        save_use_case(tmp_path, record)
        save_protected_ready_snapshot(tmp_path, record.alias)
        create_workflow_run(
            tmp_path,
            "Validate a credential flow.",
            alias=record.alias,
            integration="codex",
        )
        for stage in ("specify", "clarify", "plan", "tasks", "implement", "validate"):
            transition_workflow(
                tmp_path,
                record.alias,
                stage=stage,
                outcome="completed",
                handoff_summary="Environment-file fixture setup.",
            )
    env_file = tmp_path / ".env.verifysignal.test.local"
    env_file.write_text("UNDECLARED=secret-canary\n", encoding="utf-8")
    env_file.chmod(0o600)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("Core resolution must not run for an invalid env file")

    monkeypatch.setattr(run, "ensure_core_runtime", forbidden)
    monkeypatch.setattr(probe, "ensure_core_runtime", forbidden)
    monkeypatch.setattr(validate, "ensure_core_runtime", forbidden)
    monkeypatch.setattr(
        validate,
        "structural_validation",
        lambda *_args, **_kwargs: SimpleNamespace(status="passed"),
    )

    if command == "validate":
        argv = [
            "validate",
            record.alias,
            "--project",
            str(tmp_path),
            "--runtime-readiness",
            "--env-file",
            str(env_file),
            "--json",
        ]
    elif command == "probe":
        argv = [
            "probe",
            str(run_request),
            "--skill",
            str(skill),
            "--project",
            str(tmp_path),
            "--env-file",
            str(env_file),
            "--json",
        ]
    else:
        argv = [
            "run",
            record.alias,
            "--project",
            str(tmp_path),
            "--env-file",
            str(env_file),
            "--json",
        ]

    code = main(argv)
    output = capsys.readouterr()
    payload = json.loads(output.out)

    assert code != 0
    assert payload["status"] == "blocked"
    assert payload["blockers"][0]["code"] == "credentials.env-file-undeclared-key"
    assert "secret-canary" not in output.out
    assert "secret-canary" not in output.err
