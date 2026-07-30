"""RATCHET (bump workflow wiring). The anti-loop/anti-race design lives in workflow TEXT, so it
is pinned as text:

- the trigger is the closed-PR event, never push — a push carries no PR title (merge commits),
  and the closed-PR trigger is what makes the bump's own push structurally unable to re-enter
  the workflow. That is why NO ``[skip ci]`` marker may appear anywhere in the file: on a
  tag-triggered release repo that marker would suppress the tag event and silently kill the
  PyPI publish while every job stays green.
- pushes authenticate with the PAT (VERIFYSIGNAL_CROSSREPO_TOKEN) because GITHUB_TOKEN pushes
  trigger no workflows — the tag push IS the PyPI hand-off, and the bump commit must be
  validated by ci.
- publishing belongs to release.yml alone: the bump workflow may never name the publish action.
- the concurrency group serializes racing merges WITHOUT cancel-in-progress; the decider is
  cumulative-since-tag, so a queued run recomputes and nothing is dropped."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUMP_WORKFLOW = ROOT / ".github/workflows/version-bump.yml"
TITLE_WORKFLOW = ROOT / ".github/workflows/pr-title.yml"


def _bump_text():
    return BUMP_WORKFLOW.read_text(encoding="utf-8")


def test_triggers_on_closed_prs_with_bootstrap_inputs():
    workflow = _bump_text()
    assert "types: [closed]" in workflow
    assert "branches: [main]" in workflow
    assert "github.event.pull_request.merged == true" in workflow
    assert "explicit_version" in workflow
    assert "fallback_bump" in workflow


def test_serializes_without_cancelling_and_checks_out_credential_free_history():
    workflow = _bump_text()
    assert "group: version-bump" in workflow
    assert "cancel-in-progress: false" in workflow
    assert "cancel-in-progress: true" not in workflow
    assert "fetch-depth: 0" in workflow
    assert "persist-credentials: false" in workflow


def test_runs_decide_bump_and_the_pytest_gate_exactly_once_each():
    workflow = _bump_text()
    assert workflow.count("python scripts/release/decide_bump.py") == 1
    assert workflow.count("python scripts/release/bump_version.py") == 1
    assert workflow.count("python -m pytest tests/unit tests/contract -q") == 1


def test_pushes_with_the_pat_and_can_never_skip_ci_or_publish():
    workflow = _bump_text()
    assert workflow.count("VERIFYSIGNAL_CROSSREPO_TOKEN") == 1
    assert workflow.count("git push") == 3
    assert "[skip ci]" not in workflow
    assert "pypa/gh-action-pypi-publish" not in workflow


def test_title_check_reruns_on_edits_and_passes_the_title_through_env():
    workflow = TITLE_WORKFLOW.read_text(encoding="utf-8")
    assert "types: [opened, edited, reopened, synchronize]" in workflow
    assert "PR_TITLE: ${{ github.event.pull_request.title }}" in workflow
    assert "run: python scripts/release/check_pr_title.py" in workflow
    # Exactly ONE expression expansion in the whole file: the env indirection above. The title
    # is user-controlled text; a second ``${{ }}`` is a new interpolation site that must
    # justify itself against the injection hazard.
    assert workflow.count("${{") == 1
    assert "secrets." not in workflow
