"""Validates the pull-request title against the shared conventional-commit convention.

Invoked by .github/workflows/pr-title.yml with the title passed via the PR_TITLE env var —
env indirection on purpose: the title is user-controlled text, and interpolating it directly
into a ``run:`` block would be a script-injection vector."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from classify_title import ALLOWED_TYPES, classify_title  # noqa: E402


def main() -> int:
    title = os.environ.get("PR_TITLE")
    result = classify_title(title)
    if not result["ok"]:
        print(f"PR title does not follow the release convention: {title!r}", file=sys.stderr)
        print("", file=sys.stderr)
        print(
            "Expected shape: type(scope)!: subject  — scope optional, `!` marks a breaking change.",
            file=sys.stderr,
        )
        print(f"Allowed types: {', '.join(ALLOWED_TYPES)}", file=sys.stderr)
        print(
            "Bump mapping: `!` -> major; feat -> minor; fix, perf -> patch; "
            "docs, test, ci, chore, refactor, build, style -> none.",
            file=sys.stderr,
        )
        return 1
    print(f"PR title ok: type={result['type']} bump={result['bump']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
