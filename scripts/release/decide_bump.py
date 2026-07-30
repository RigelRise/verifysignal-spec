"""Decides the next version cumulatively from everything merged since the last v* tag.

Cumulative-since-tag (not per-event) on purpose: the version-bump workflow serializes under a
concurrency group that keeps at most ONE pending run, so a third rapid merge cancels the
second's pending run — per-event semantics would drop that bump; recomputing the whole range
cannot. The reconcile guard makes every run idempotent: if the in-repo version is already ahead
of the last tag (a partial failure, or a hand-bump in a PR under the old convention), the right
move is to tag what exists, never to bump again on top of it.

Decisions: no-baseline | reconcile | none | bump | unparseable. Unparseable titles fail the run
LOUDLY by default (a silent "none" would swallow releases); the workflow_dispatch fallback_bump
input classifies stragglers for one run."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from classify_title import classify_title  # noqa: E402

_ORDER = {"none": 0, "patch": 1, "minor": 2, "major": 3}
_VERSION_SHAPE = re.compile(r"^\d+\.\d+\.\d+$")
_MERGE_SUBJECT = re.compile(r"^Merge pull request #(\d+) ")


def max_bump(bumps):
    result = "none"
    for bump in bumps:
        if _ORDER[bump] > _ORDER[result]:
            result = bump
    return result


def apply_bump(version, bump):
    major, minor, patch = (int(part) for part in version.split("."))
    if bump == "major":
        return f"{major + 1}.0.0"
    if bump == "minor":
        return f"{major}.{minor + 1}.0"
    if bump == "patch":
        return f"{major}.{minor}.{patch + 1}"
    return version


def extract_pr_number(subject):
    match = _MERGE_SUBJECT.match(subject)
    return int(match.group(1)) if match else None


def decide(*, current_version, tag_version, subjects, title_by_pr, fallback_bump=None):
    if tag_version is None:
        return {"decision": "no-baseline", "current": current_version}
    if tag_version != current_version:
        return {"decision": "reconcile", "current": current_version, "tag": f"v{current_version}"}
    bumps = []
    for subject in subjects:
        pr = extract_pr_number(subject)
        title = subject if pr is None else title_by_pr(pr)
        result = classify_title(title)
        if not result["ok"]:
            if fallback_bump and fallback_bump != "none":
                bumps.append(fallback_bump)
                continue
            return {"decision": "unparseable", "current": current_version, "offender": title}
        bumps.append(result["bump"])
    bump = max_bump(bumps)
    if bump == "none":
        return {"decision": "none", "current": current_version}
    return {
        "decision": "bump",
        "bump": bump,
        "current": current_version,
        "next": apply_bump(current_version, bump),
    }


def read_current_version(repo_root):
    source = (Path(repo_root) / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version = "(\d+\.\d+\.\d+)"$', source, re.M)
    if not match:
        raise ValueError("could not read version from pyproject.toml")
    return match.group(1)


def _git(args, repo_root):
    return subprocess.run(
        ["git", *args], cwd=repo_root, capture_output=True, text=True, check=True
    ).stdout.strip()


def _last_reachable_tag(repo_root):
    tags = _git(["tag", "--merged", "HEAD", "--list", "v*", "--sort=-version:refname"], repo_root)
    first = next((line for line in tags.splitlines() if line), None)
    return first[1:] if first else None


def _first_parent_subjects(repo_root, since_tag):
    log = _git(["log", "--first-parent", "--format=%s", f"v{since_tag}..HEAD"], repo_root)
    return [line for line in log.splitlines() if line]


def _title_from_github(pr):
    return subprocess.run(
        ["gh", "pr", "view", str(pr), "--json", "title", "-q", ".title"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def _emit(result):
    print(json.dumps(result))
    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        with open(output_path, "a", encoding="utf-8") as handle:
            for key, value in result.items():
                handle.write(f"{key}={value}\n")


def main() -> int:
    args = sys.argv[1:]
    repo_root = Path.cwd()

    explicit = (os.environ.get("EXPLICIT_VERSION") or "").strip()
    if explicit:
        if not _VERSION_SHAPE.match(explicit):
            print(f"EXPLICIT_VERSION is not MAJOR.MINOR.PATCH: {explicit}", file=sys.stderr)
            return 1
        _emit(
            {
                "decision": "bump",
                "bump": "explicit",
                "current": read_current_version(repo_root),
                "next": explicit,
            }
        )
        return 0

    if "--titles-json" in args:
        injected = json.loads(
            Path(args[args.index("--titles-json") + 1]).read_text(encoding="utf-8")
        )
        result = decide(
            current_version=injected["currentVersion"],
            tag_version=injected.get("tagVersion"),
            subjects=injected["subjects"],
            title_by_pr=lambda pr: injected["titleByPr"][str(pr)],
            fallback_bump=injected.get("fallbackBump"),
        )
    else:
        current_version = read_current_version(repo_root)
        tag_version = _last_reachable_tag(repo_root)
        result = decide(
            current_version=current_version,
            tag_version=tag_version,
            subjects=[] if tag_version is None else _first_parent_subjects(repo_root, tag_version),
            title_by_pr=_title_from_github,
            fallback_bump=os.environ.get("FALLBACK_BUMP"),
        )

    _emit(result)
    if result["decision"] == "unparseable":
        print(
            f"Unparseable title in range: {result['offender']!r}\n"
            "Re-dispatch version-bump with fallback_bump set to classify it for one run.",
            file=sys.stderr,
        )
        return 1
    if result["decision"] == "no-baseline":
        print(
            "No v* tag reachable from HEAD — dispatch version-bump with explicit_version to bootstrap.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
