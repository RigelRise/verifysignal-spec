from __future__ import annotations

import re
from pathlib import Path

# RATCHET (onboarding honesty). Repository URLs have drifted during both public renames, leaving
# documented installs and support links pointed at retired slugs. Docs are not type-checked or
# executed, so the post-rename patch freezes the exact canonical GitHub identity.
#
# This guard pins the post-rename path across every active repository surface. It does NOT (and
# cannot) prove the remote exists; the redirect and exact live URL remain manual cutover checks.

CANONICAL_REPO = "github.com/RigelRise/verifysignal"
STALE_REPO_PATTERN = re.compile(
    r"github\.com/RigelRise/(?:proofsignal[\w.-]*|verifysignal-spec)"
)
GITHUB_URL_PATTERN = re.compile(r"github\.com/[\w.-]+/[\w.-]+")

ROOT = Path(__file__).resolve().parents[2]
DOC_PATHS = [ROOT / "README.md", *sorted((ROOT / "docs").glob("*.md"))]
REPOSITORY_SURFACE_PATHS = [
    *DOC_PATHS,
    ROOT / "SECURITY.md",
    ROOT / "CODE_OF_CONDUCT.md",
    ROOT / "ROADMAP.md",
    ROOT / ".github" / "ISSUE_TEMPLATE" / "config.yml",
    ROOT / "scripts" / "install.sh",
    ROOT / "scripts" / "install.ps1",
]


def _surfaces_with_text() -> list[tuple[Path, str]]:
    return [
        (path, path.read_text(encoding="utf-8"))
        for path in REPOSITORY_SURFACE_PATHS
        if path.exists()
    ]


def test_docs_have_no_stale_proofsignal_repo_urls() -> None:
    offenders = [
        f"{path.relative_to(ROOT)}: {match.group(0)}"
        for path, text in _surfaces_with_text()
        for match in STALE_REPO_PATTERN.finditer(text)
    ]
    assert offenders == [], f"docs still advertise the pre-rebrand repository: {offenders}"


def test_every_advertised_github_repo_url_is_the_canonical_one() -> None:
    # Any advertised GitHub repo URL after the rename must identify the canonical repository.
    offenders = [
        f"{path.relative_to(ROOT)}: {match.group(0)}"
        for path, text in _surfaces_with_text()
        for match in GITHUB_URL_PATTERN.finditer(text)
        if match.group(0).startswith("github.com/RigelRise/")
        and match.group(0).removesuffix(".git") != CANONICAL_REPO
    ]
    assert offenders == [], f"docs advertise a non-canonical GitHub repo: {offenders}"


def test_install_docs_still_advertise_an_installable_command() -> None:
    # Guards the other direction: the URL fix must not quietly delete the documented install path.
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert f"git+https://{CANONICAL_REPO}.git" in readme
    assert re.search(r"\buv tool install verifysignal(?:\s|$)", readme)
    assert not re.search(r"\buv tool install verifysignal-spec\b", readme)
