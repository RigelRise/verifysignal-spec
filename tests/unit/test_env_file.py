from __future__ import annotations

import os

import pytest

from verifysignal_spec.runtime.env_file import (
    EnvironmentFileError,
    build_child_environment_values,
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
