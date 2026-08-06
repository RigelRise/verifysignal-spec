from __future__ import annotations

from collections.abc import Callable

import pytest

from verifysignal_spec.workspace import layout


PathValidator = Callable[[str], str]


@pytest.mark.parametrize(
    "validator",
    [
        layout.ensure_path_safe_alias,
        layout.ensure_path_safe_id,
        layout.ensure_path_safe_run_id,
    ],
)
@pytest.mark.parametrize(
    "value",
    [
        "con",
        "nul.snapshot",
        "com1.backup",
        "lpt9.txt",
        "portable.",
        "portable ",
        "portable\n",
        "portable\t",
    ],
)
def test_path_component_validators_reject_windows_unsafe_names(
    validator: PathValidator,
    value: str,
) -> None:
    with pytest.raises(ValueError):
        validator(value)


@pytest.mark.parametrize(
    ("validator", "value"),
    [
        (layout.ensure_path_safe_alias, "localized-home.v2"),
        (layout.ensure_path_safe_id, "review.local_1-2"),
        (layout.ensure_path_safe_run_id, "Run-2026T142635Z"),
        (layout.ensure_path_safe_alias, "console"),
        (layout.ensure_path_safe_alias, "com10"),
        (layout.ensure_path_safe_alias, "lpt0"),
    ],
)
def test_path_component_validators_preserve_portable_names(
    validator: PathValidator,
    value: str,
) -> None:
    assert validator(value) == value


@pytest.mark.parametrize(
    "value",
    [
        "CON",
        "NuL.snapshot",
        "cOm1.backup",
        "LpT9.txt",
    ],
)
def test_run_ids_reject_windows_devices_case_insensitively(value: str) -> None:
    with pytest.raises(ValueError):
        layout.ensure_path_safe_run_id(value)
