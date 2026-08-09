"""Conversation-language resolution for generated agent guidance.

The declared language changes only how the agent converses; generated project
artifacts stay English. Detection is best-effort by design: any failure — odd
env values, C/POSIX locales, a locale module that raises — resolves to None,
never an error, because `init` must not block on it.
"""

from __future__ import annotations

import argparse
import locale
import os
import re
from dataclasses import dataclass

_PRIMARY_SUBTAG = re.compile(r"^[a-zA-Z]{2,3}$")
_EXTRA_SUBTAG = re.compile(r"^[a-zA-Z0-9]{1,8}$")
_NON_LANGUAGES = {"c", "posix"}
_ENV_VARS = ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG")


@dataclass(frozen=True, slots=True)
class ConversationLanguage:
    code: str
    source: str  # "flag" | "detected"


def normalize_language_tag(value: str) -> str | None:
    """`PT_br` -> `pt-BR`; anything that is not a plausible BCP-47-ish tag -> None."""
    subtags = value.strip().replace("_", "-").split("-")
    primary = subtags[0].lower()
    if not _PRIMARY_SUBTAG.fullmatch(primary) or primary in _NON_LANGUAGES:
        return None
    rest = []
    for subtag in subtags[1:]:
        if not _EXTRA_SUBTAG.fullmatch(subtag):
            return None
        rest.append(subtag.upper() if len(subtag) == 2 else subtag.lower())
    return "-".join([primary, *rest])


def language_flag(value: str) -> str:
    normalized = normalize_language_tag(value)
    if normalized is None:
        raise argparse.ArgumentTypeError(
            f"implausible language code: {value!r} (expected a short tag such as pt, pt-BR, ru, et)"
        )
    return normalized


def detect_system_language() -> str | None:
    """Primary language subtag of the system locale (`ru_RU.UTF-8` -> `ru`), or None."""
    try:
        for var in _ENV_VARS:
            raw = os.environ.get(var) or ""
            # LANGUAGE is a colon-separated preference list; the others hold one value.
            for entry in raw.split(":") if var == "LANGUAGE" else [raw]:
                code = _primary_language(entry)
                if code:
                    return code
        for category in [locale.LC_MESSAGES] if hasattr(locale, "LC_MESSAGES") else []:
            code = _primary_language((locale.getlocale(category) or (None,))[0] or "")
            if code:
                return code
        return _primary_language((locale.getlocale() or (None,))[0] or "")
    except Exception:
        return None


def _primary_language(entry: str) -> str | None:
    bare = entry.split("@", 1)[0].split(".", 1)[0].strip()
    if not bare:
        return None
    normalized = normalize_language_tag(bare)
    if normalized is None:
        return None
    return normalized.split("-", 1)[0]
