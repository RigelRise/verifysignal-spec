"""First-ever pin of release.yml — the tag-triggered OIDC publish path, plus the guard that a
tag must name the version the tree declares. The docstring of test_version_consistency.py has
always said "the release workflow tags off this value"; without the guard, a mislabeled tag
(v0.22.0 pushed onto a 0.21.6 tree) would publish a wheel whose PyPI version lies about its
contents. The guard makes that a build failure instead of a shipped artifact."""

from pathlib import Path

RELEASE_WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/release.yml"


def _text():
    return RELEASE_WORKFLOW.read_text(encoding="utf-8")


def test_release_is_tag_triggered_oidc_trusted_publishing():
    workflow = _text()
    assert '- "v*"' in workflow
    assert workflow.count("pypa/gh-action-pypi-publish@release/v1") == 1
    assert "id-token: write" in workflow
    assert "name: pypi" in workflow


def test_the_tag_must_name_the_version_the_tree_declares():
    workflow = _text()
    assert workflow.count("GITHUB_REF_NAME") == 1
    assert "refusing to build a mislabeled artifact" in workflow
