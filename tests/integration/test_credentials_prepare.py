from __future__ import annotations

import json
import os
import stat
import subprocess

from helpers import CliTestCase
from verifysignal_spec.workspace.models import RuntimeInputRequirement, UseCaseRecord
from verifysignal_spec.workspace.repository import init_workspace, save_use_case


class CredentialPreparationTests(CliTestCase):
    def setUp(self) -> None:
        super().setUp()
        subprocess.run(
            ["git", "init", "-q", str(self.project)],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        init_workspace(self.project)
        save_use_case(
            self.project,
            UseCaseRecord(
                alias="create-project",
                title="Create project",
                description="Create a project in the test application.",
                credentialRefs={
                    "test-user": {
                        "source": "environment",
                        "keys": {
                            "email": "TEST_USER_EMAIL",
                            "password": "TEST_USER_PASSWORD",
                        },
                    }
                },
                sessionRef={
                    "source": "environment",
                    "key": "TEST_STORAGE_STATE",
                },
                runtimeInputs=[
                    RuntimeInputRequirement(
                        name="baseUrl",
                        source="environment",
                        envVar="TEST_TARGET_URL",
                    )
                ],
            ),
        )

    def test_prepare_creates_exact_git_ignored_0600_template_without_values(self) -> None:
        code, out, err = self.cli(
            [
                "credentials",
                "prepare",
                "create-project",
                "--project",
                str(self.project),
                "--env-file",
                ".env.verifysignal.test.local",
                "--json",
            ]
        )

        assert code == 0, err
        payload = json.loads(out)
        assert payload["schemaVersion"] == (
            "verifysignal-spec-credential-preparation/v1"
        )
        assert payload["status"] == "prepared"
        assert payload["declaredKeys"] == [
            "TEST_STORAGE_STATE",
            "TEST_TARGET_URL",
            "TEST_USER_EMAIL",
            "TEST_USER_PASSWORD",
        ]
        env_file = self.project / ".env.verifysignal.test.local"
        assert stat.S_IMODE(env_file.stat().st_mode) == 0o600
        assert env_file.read_text(encoding="utf-8").splitlines() == [
            "TEST_STORAGE_STATE=",
            "TEST_TARGET_URL=",
            "TEST_USER_EMAIL=",
            "TEST_USER_PASSWORD=",
        ]
        exclude = (self.project / ".git/info/exclude").read_text(encoding="utf-8")
        assert exclude.splitlines().count(".env.verifysignal.test.local") == 1
        ignored = subprocess.run(
            ["git", "check-ignore", "-q", "--no-index", ".env.verifysignal.test.local"],
            cwd=self.project,
            check=False,
        )
        assert ignored.returncode == 0

    def test_prepare_preserves_existing_values_and_never_outputs_them(self) -> None:
        secret = "credential-canary-never-print"
        env_file = self.project / ".env.verifysignal.test.local"
        env_file.write_text(f"TEST_USER_EMAIL={secret}\n", encoding="utf-8")
        env_file.chmod(0o600)

        code, out, err = self.cli(
            [
                "credentials",
                "prepare",
                "create-project",
                "--project",
                str(self.project),
                "--env-file",
                str(env_file),
                "--json",
            ]
        )

        assert code == 0, err
        assert secret not in out
        assert secret not in err
        assert secret in env_file.read_text(encoding="utf-8")
        payload = json.loads(out)
        assert payload["preservedKeys"] == ["TEST_USER_EMAIL"]

    def test_prepare_blocks_before_env_file_write_when_project_is_not_git(self) -> None:
        non_git = self.project.parent / f"{self.project.name}-not-git"
        init_workspace(non_git)
        save_use_case(
            non_git,
            UseCaseRecord(
                alias="needs-secret",
                title="Needs secret",
                description="Fixture.",
                credentialRefs={
                    "user": {
                        "source": "environment",
                        "keys": {"password": "TEST_PASSWORD"},
                    }
                },
            ),
        )

        code, out, _err = self.cli(
            [
                "credentials",
                "prepare",
                "needs-secret",
                "--project",
                str(non_git),
                "--env-file",
                ".env.verifysignal.test.local",
                "--json",
            ]
        )

        assert code != 0
        payload = json.loads(out)
        assert payload["status"] == "blocked"
        assert payload["blockers"][0]["code"] == "credentials.git-exclusion-unavailable"
        assert not (non_git / ".env.verifysignal.test.local").exists()
