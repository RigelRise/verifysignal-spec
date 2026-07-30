"""The version-bump automation derives semver from merged-PR titles: the pr-title check and
the bump decider share ONE classifier (they can never drift), and the decider recomputes
cumulatively from the last v* tag so a cancelled or raced run can never drop a bump. These
tests pin the decision table — the mapping, the version math, the reconcile guard for
hand-bumped versions, and the loud failure on unparseable titles."""

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load(name: str, relative_path: str):
    location = ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, location)
    if spec is None or spec.loader is None:
        raise AssertionError(f"missing script: {location}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("title", "bump"),
    [
        ("feat(cli): add the core update command", "minor"),
        ("feat: unscoped capability", "minor"),
        ("fix(runtime): keep the managed MCP cache path", "patch"),
        ("perf: faster fixture loading", "patch"),
        ("feat(cli)!: drop the v1 run envelope", "major"),
        ("refactor!: split the distribution module", "major"),
        ("docs: describe the embedded anchor", "none"),
        ("test: reproduce the race", "none"),
        ("ci: add the acceptance leg", "none"),
        ("chore(deps): bump cryptography from 42 to 43", "none"),
        ("chore(release): bump verifysignal-spec to 0.22.0", "none"),
        ("refactor(repos): extract the resolver", "none"),
        ("build: pin the toolchain", "none"),
        ("style: import order", "none"),
    ],
)
def test_classifier_maps_conventional_titles(title, bump):
    classify = _load("classify_title", "scripts/release/classify_title.py")
    result = classify.classify_title(title)
    assert result["ok"] is True
    assert result["bump"] == bump


@pytest.mark.parametrize(
    "title",
    [
        "Make the resolver tests independent of the ambient environment",
        "Feat: capitalized",
        "feat(CLI): capitalized scope",
        "feat:no space",
        "feature: unknown type",
        "",
    ],
)
def test_classifier_rejects_nonconforming_titles(title):
    classify = _load("classify_title", "scripts/release/classify_title.py")
    result = classify.classify_title(title)
    assert result["ok"] is False
    assert result["bump"] is None


def test_apply_bump_semver_math():
    decide_bump = _load("decide_bump", "scripts/release/decide_bump.py")
    assert decide_bump.apply_bump("0.21.6", "patch") == "0.21.7"
    assert decide_bump.apply_bump("0.21.6", "minor") == "0.22.0"
    assert decide_bump.apply_bump("0.21.6", "major") == "1.0.0"
    assert decide_bump.apply_bump("0.21.6", "none") == "0.21.6"


def test_decide_takes_the_max_bump_across_the_range():
    decide_bump = _load("decide_bump", "scripts/release/decide_bump.py")
    titles = {
        14: "feat(authoring): accept waitForLocation in the offline fallback",
        15: "fix(ci): harden the embedded-anchor leg",
    }
    result = decide_bump.decide(
        current_version="0.21.6",
        tag_version="0.21.6",
        subjects=[
            "Merge pull request #15 from RigelRise/feat/embedded-anchor-acceptance",
            "Merge pull request #14 from RigelRise/feat/wait-for-location-fallback",
            "docs(changelog): date the 0.21.6 release",
        ],
        title_by_pr=lambda pr: titles[pr],
    )
    assert result["decision"] == "bump"
    assert result["bump"] == "minor"
    assert result["next"] == "0.22.0"


def test_decide_classifies_direct_push_subjects_by_their_own_text():
    decide_bump = _load("decide_bump", "scripts/release/decide_bump.py")

    def no_lookup(pr):
        raise AssertionError("no PR lookup should happen for direct pushes")

    result = decide_bump.decide(
        current_version="0.21.6",
        tag_version="0.21.6",
        subjects=["test: reproduce the race", "fix: close the race"],
        title_by_pr=no_lookup,
    )
    assert result["decision"] == "bump"
    assert result["bump"] == "patch"
    assert result["next"] == "0.21.7"


def test_decide_returns_none_for_a_nonreleasable_range():
    decide_bump = _load("decide_bump", "scripts/release/decide_bump.py")
    result = decide_bump.decide(
        current_version="0.21.6",
        tag_version="0.21.6",
        subjects=["docs: notes", "ci: wiring", "chore(release): bump verifysignal-spec to 0.21.6"],
        title_by_pr=lambda pr: "docs: irrelevant",
    )
    assert result["decision"] == "none"


def test_decide_reconciles_instead_of_double_bumping():
    decide_bump = _load("decide_bump", "scripts/release/decide_bump.py")
    result = decide_bump.decide(
        current_version="0.22.0",
        tag_version="0.21.6",
        subjects=["Merge pull request #99 from RigelRise/anything"],
        title_by_pr=lambda pr: "feat: would be minor",
    )
    assert result["decision"] == "reconcile"
    assert result["tag"] == "v0.22.0"


def test_decide_refuses_a_range_with_no_baseline_tag():
    decide_bump = _load("decide_bump", "scripts/release/decide_bump.py")
    result = decide_bump.decide(
        current_version="0.21.6",
        tag_version=None,
        subjects=[],
        title_by_pr=lambda pr: "",
    )
    assert result["decision"] == "no-baseline"


def test_decide_fails_loudly_on_unparseable_titles_and_honors_the_fallback():
    decide_bump = _load("decide_bump", "scripts/release/decide_bump.py")
    kwargs = dict(
        current_version="0.21.6",
        tag_version="0.21.6",
        subjects=["Merge pull request #12 from RigelRise/fix/env-independent-resolver-tests"],
        title_by_pr=lambda pr: "Make the resolver tests independent of the ambient environment",
    )
    assert decide_bump.decide(**kwargs)["decision"] == "unparseable"
    fallback = decide_bump.decide(**kwargs, fallback_bump="patch")
    assert fallback["decision"] == "bump"
    assert fallback["bump"] == "patch"
    assert fallback["next"] == "0.21.7"
