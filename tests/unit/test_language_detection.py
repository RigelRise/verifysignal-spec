from __future__ import annotations

import argparse
import os
from unittest.mock import patch

import pytest

from verifysignal_spec.language import (
    detect_system_language,
    language_flag,
    normalize_language_tag,
)

LOCALE_VARS = ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG")


def _locale_env(**values: str) -> dict[str, str]:
    env = {var: "" for var in LOCALE_VARS}
    env.update(values)
    return env


def _detect(**values: str) -> str | None:
    # Locale-module fallbacks are stubbed out so results never depend on the host machine.
    with patch.dict(os.environ, _locale_env(**values)), patch(
        "verifysignal_spec.language.locale.getlocale", return_value=(None, None)
    ):
        return detect_system_language()


def test_env_precedence_language_before_lc_all() -> None:
    assert _detect(LANGUAGE="pt_BR:pt:en", LC_ALL="ru_RU.UTF-8") == "pt"
    assert _detect(LC_ALL="ru_RU.UTF-8", LC_MESSAGES="et_EE") == "ru"
    assert _detect(LC_MESSAGES="et_EE", LANG="ru_RU") == "et"
    assert _detect(LANG="et_EE") == "et"


def test_language_colon_list_skips_implausible_entries() -> None:
    assert _detect(LANGUAGE="C:pt_BR") == "pt"


def test_encoding_and_modifier_suffixes_are_stripped() -> None:
    assert _detect(LANG="ru_RU.UTF-8") == "ru"
    assert _detect(LANG="et_EE.UTF-8@euro") == "et"


def test_c_posix_and_garbage_resolve_to_none() -> None:
    for value in ("C", "POSIX", "C.UTF-8", "", "not a locale!!", "1234"):
        assert _detect(LANG=value) is None, value


def test_detection_returns_primary_subtag_only() -> None:
    assert _detect(LANG="pt_BR.UTF-8") == "pt"


def test_detection_never_raises_when_locale_module_fails() -> None:
    with patch.dict(os.environ, _locale_env()), patch(
        "verifysignal_spec.language.locale.getlocale", side_effect=RuntimeError("boom")
    ):
        assert detect_system_language() is None


def test_normalize_language_tag() -> None:
    assert normalize_language_tag("pt") == "pt"
    assert normalize_language_tag("PT_br") == "pt-BR"
    assert normalize_language_tag("ru") == "ru"
    assert normalize_language_tag("eng") == "eng"
    for junk in ("c", "posix", "x!!", "", "1234"):
        assert normalize_language_tag(junk) is None, junk


def test_language_flag_normalizes_or_rejects() -> None:
    assert language_flag("PT_br") == "pt-BR"
    assert language_flag("ru") == "ru"
    with pytest.raises(argparse.ArgumentTypeError):
        language_flag("not a language")
