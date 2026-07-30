"""Single source of truth for the conventional-commit PR-title convention. The pr-title check
and the bump decider both import THIS module, so what the check accepts and what the release
automation classifies can never drift apart.

Mapping: ``!`` before the colon -> major; feat -> minor; fix, perf -> patch; everything else ->
none. Merge commits mean the PR title never enters git history — the title carried by the
closed-PR event is the only machine-readable release signal, which is why its grammar is
enforced (see .github/workflows/pr-title.yml) instead of trusted."""

import re

ALLOWED_TYPES = [
    "feat",
    "fix",
    "docs",
    "test",
    "ci",
    "chore",
    "refactor",
    "perf",
    "build",
    "style",
]

BUMP_BY_TYPE = {"feat": "minor", "fix": "patch", "perf": "patch"}

_TITLE_PATTERN = re.compile(
    r"^(" + "|".join(ALLOWED_TYPES) + r")(\([a-z0-9][a-z0-9._/-]*\))?(!)?: \S.*$"
)


def classify_title(title):
    match = _TITLE_PATTERN.match(title or "")
    if not match:
        return {"ok": False, "type": None, "bump": None}
    type_, _scope, breaking = match.groups()
    bump = "major" if breaking else BUMP_BY_TYPE.get(type_, "none")
    return {"ok": True, "type": type_, "bump": bump}
