"""Rewrites every coupled version surface, or refuses to rewrite any.

Surfaces:
  1. ``pyproject.toml``            — the version PyPI publishes
  2. ``src/verifysignal_spec/__init__.py`` — ``__version__`` (the pair is pinned by
     tests/unit/test_version_consistency.py)
  3. ``CHANGELOG.md``              — promote ``## Unreleased`` to a dated release section and
     append the house bump bullet (or insert a minimal dated section when there is none)

The pyproject rewrite is line-targeted on purpose — a TOML serializer round-trip could reformat
the ``[project.scripts]`` literal lines that test_public_cli_entrypoint_contract.py pins
byte-exactly. Each version needle is asserted to occur EXACTLY once before anything is written,
so a drifted surface aborts the run all-or-nothing."""

import re
import sys
from datetime import date
from pathlib import Path

_VERSION_SHAPE = re.compile(r"^\d+\.\d+\.\d+$")


def _stamp_changelog(path, to_version, today):
    header = f"## {to_version} - {today.isoformat()}"
    bullet = f"- Bumped VerifySignal Spec to `{to_version}`."
    text = path.read_text(encoding="utf-8")
    if "\n## Unreleased\n" in text:
        promoted = text.replace("\n## Unreleased\n", f"\n{header}\n", 1)
        head, sep, tail = promoted.partition(f"\n{header}\n")
        next_h2 = tail.find("\n## ")
        section = tail if next_h2 == -1 else tail[:next_h2]
        rest = "" if next_h2 == -1 else tail[next_h2:]
        section = section.rstrip("\n") + f"\n{bullet}\n"
        path.write_text(head + sep + section + rest, encoding="utf-8")
        return
    marker = "# Changelog\n"
    index = text.find(marker)
    if index == -1:
        raise ValueError("CHANGELOG.md does not start with '# Changelog'")
    insert_at = index + len(marker)
    path.write_text(
        text[:insert_at] + f"\n{header}\n\n{bullet}\n" + text[insert_at:], encoding="utf-8"
    )


def bump_surfaces(repo_root, to_version, today=None):
    repo_root = Path(repo_root)
    if not _VERSION_SHAPE.match(to_version):
        raise ValueError(f"target version is not MAJOR.MINOR.PATCH: {to_version}")

    pyproject = repo_root / "pyproject.toml"
    match = re.search(r'^version = "(\d+\.\d+\.\d+)"$', pyproject.read_text(encoding="utf-8"), re.M)
    if not match:
        raise ValueError("could not read version from pyproject.toml")
    previous = match.group(1)
    if previous == to_version:
        raise ValueError(f"already at {to_version}; nothing to bump")

    surfaces = [
        (pyproject, f'version = "{previous}"', f'version = "{to_version}"'),
        (
            repo_root / "src/verifysignal_spec/__init__.py",
            f'__version__ = "{previous}"',
            f'__version__ = "{to_version}"',
        ),
    ]
    # Validate every surface BEFORE writing any: all-or-nothing.
    for path, needle, _replacement in surfaces:
        occurrences = path.read_text(encoding="utf-8").count(needle)
        if occurrences != 1:
            raise ValueError(
                f"expected {needle!r} exactly once in {path}, found {occurrences} — "
                "surfaces drifted, refusing to bump"
            )
    for path, needle, replacement in surfaces:
        text = path.read_text(encoding="utf-8")
        path.write_text(text.replace(needle, replacement, 1), encoding="utf-8")

    _stamp_changelog(repo_root / "CHANGELOG.md", to_version, today or date.today())
    return previous


def main() -> int:
    args = sys.argv[1:]
    if "--to" not in args:
        print("Usage: python scripts/release/bump_version.py --to X.Y.Z", file=sys.stderr)
        return 2
    to_version = args[args.index("--to") + 1]
    previous = bump_surfaces(Path.cwd(), to_version)
    print(f"bumped verifysignal-spec {previous} -> {to_version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
