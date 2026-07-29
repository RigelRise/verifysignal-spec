from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from verifysignal_spec.runtime.env_file import (
    EnvironmentFileError,
    build_child_environment_values,
    git_exposure_warnings,
    parse_environment_text,
)


def test_strict_environment_parser_accepts_only_literal_declared_assignments() -> None:
    parsed = parse_environment_text(
        """
        # test credentials
        export TEST_USER='qa@example.test'
        TEST_PASSWORD="literal-value"
        TARGET_URL=http://127.0.0.1:4200
        """,
        allowed_keys={"TEST_USER", "TEST_PASSWORD", "TARGET_URL"},
    )

    assert parsed == {
        "TEST_USER": "qa@example.test",
        "TEST_PASSWORD": "literal-value",
        "TARGET_URL": "http://127.0.0.1:4200",
    }


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("UNDECLARED=value", "credentials.env-file-undeclared-key"),
        ("TEST_USER=one\nTEST_USER=two", "credentials.env-file-duplicate-key"),
        ("TEST_USER=$(id)", "credentials.env-file-executable-syntax"),
        ("TEST_USER=${OTHER}", "credentials.env-file-interpolation"),
        ("TEST_USER=`id`", "credentials.env-file-executable-syntax"),
        ("TEST-USER=value", "credentials.env-file-invalid-assignment"),
        ("TEST_USER='unterminated", "credentials.env-file-invalid-assignment"),
    ],
)
def test_strict_environment_parser_blocks_unsafe_or_undeclared_input(
    text: str,
    code: str,
) -> None:
    with pytest.raises(EnvironmentFileError) as exc:
        parse_environment_text(text, allowed_keys={"TEST_USER"})

    assert exc.value.code == code


def test_explicit_values_override_ambient_only_in_the_child_mapping(monkeypatch) -> None:
    monkeypatch.setenv("TEST_USER", "ambient")
    before = dict(os.environ)

    child = build_child_environment_values(
        {"TEST_USER": "explicit"},
        declared_keys={"TEST_USER"},
    )

    assert child == {"TEST_USER": "explicit"}
    assert os.environ["TEST_USER"] == "ambient"
    assert dict(os.environ) == before


def _git_project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    project.mkdir()
    subprocess.run(["git", "init", "-q", str(project)], check=True)
    return project


def test_unignored_environment_file_warns_without_blocking(tmp_path) -> None:
    project = _git_project(tmp_path)
    target = project / ".env.verifysignal.test.local"
    target.write_text("TEST_USER=qa@example.test\n")

    warnings = git_exposure_warnings(project, target)

    assert [item["code"] for item in warnings] == ["credentials.env-file-not-git-ignored"]
    assert warnings[0]["severity"] == "warning"
    assert "qa@example.test" not in warnings[0]["message"]


def test_ignored_environment_file_does_not_warn(tmp_path) -> None:
    project = _git_project(tmp_path)
    target = project / ".env.verifysignal.test.local"
    target.write_text("TEST_USER=qa@example.test\n")
    (project / ".gitignore").write_text(".env.verifysignal.test.local\n")

    assert git_exposure_warnings(project, target) == []


def test_tracked_environment_file_warns_even_when_a_rule_would_ignore_it(tmp_path) -> None:
    project = _git_project(tmp_path)
    target = project / ".env.verifysignal.test.local"
    target.write_text("TEST_USER=qa@example.test\n")
    subprocess.run(["git", "-C", str(project), "add", "-f", target.name], check=True)
    (project / ".gitignore").write_text(".env.verifysignal.test.local\n")

    warnings = git_exposure_warnings(project, target)

    assert [item["code"] for item in warnings] == ["credentials.env-file-tracked-by-git"]


def test_environment_file_outside_the_project_is_not_a_git_concern(tmp_path) -> None:
    project = _git_project(tmp_path)
    outside = tmp_path / "elsewhere.env"
    outside.write_text("TEST_USER=qa@example.test\n")

    assert git_exposure_warnings(project, outside) == []


def test_non_git_project_does_not_warn(tmp_path) -> None:
    project = tmp_path / "plain"
    project.mkdir()
    target = project / ".env.verifysignal.test.local"
    target.write_text("TEST_USER=qa@example.test\n")

    assert git_exposure_warnings(project, target) == []
