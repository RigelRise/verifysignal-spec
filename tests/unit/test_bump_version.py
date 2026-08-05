"""The surface rewriter must move every coupled version declaration together or refuse to move
any: `pyproject.toml` and `src/verifysignal_spec/__init__.py` (the pair that
tests/unit/test_version_consistency.py pins), plus the curated CHANGELOG (promote
`## Unreleased` to a dated release section and append the house bump bullet). The pyproject
rewrite is line-targeted on purpose — a TOML serializer round-trip could reformat the
`[project.scripts]` literal lines that test_public_cli_entrypoint_contract.py pins byte-exactly."""

import importlib.util
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

SCRIPT_LINES = [
    'verifysignal = "verifysignal_spec.cli:main"',
    'verifysignal-spec = "verifysignal_spec.cli:main"',
]


def _load_bump_version():
    location = ROOT / "scripts/release/bump_version.py"
    spec = importlib.util.spec_from_file_location("bump_version", location)
    if spec is None or spec.loader is None:
        raise AssertionError(f"missing script: {location}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fixture_repo(tmp_path: Path, changelog: str) -> Path:
    (tmp_path / "src/verifysignal_spec").mkdir(parents=True)
    (tmp_path / "pyproject.toml").write_text(
        "[project]\n"
        'name = "verifysignal"\n'
        'version = "0.21.6"\n'
        "\n"
        "[project.scripts]\n" + SCRIPT_LINES[0] + "\n" + SCRIPT_LINES[1] + "\n",
        encoding="utf-8",
    )
    (tmp_path / "src/verifysignal_spec/__init__.py").write_text(
        '"""VerifySignal CLI package."""\n\n__version__ = "0.21.6"\n',
        encoding="utf-8",
    )
    (tmp_path / "CHANGELOG.md").write_text(changelog, encoding="utf-8")
    return tmp_path


UNRELEASED_CHANGELOG = (
    "# Changelog\n"
    "\n"
    "## Unreleased\n"
    "\n"
    "### Embedded release-anchor acceptance\n"
    "\n"
    "- Added a clean-machine acceptance leg.\n"
    "\n"
    "## 0.21.6 - 2026-07-30\n"
    "\n"
    "- Older entry.\n"
)


def test_bump_moves_both_declarations_and_promotes_the_changelog(tmp_path):
    bump_version = _load_bump_version()
    root = _fixture_repo(tmp_path, UNRELEASED_CHANGELOG)
    previous = bump_version.bump_surfaces(root, "0.22.0", today=date(2026, 7, 30))
    assert previous == "0.21.6"

    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    assert 'version = "0.22.0"' in pyproject
    assert 'version = "0.21.6"' not in pyproject
    for line in SCRIPT_LINES:
        assert line in pyproject  # byte-identical entry points after the rewrite

    package = (root / "src/verifysignal_spec/__init__.py").read_text(encoding="utf-8")
    assert '__version__ = "0.22.0"' in package

    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "## Unreleased" not in changelog
    assert "## 0.22.0 - 2026-07-30" in changelog
    promoted = changelog.split("## 0.22.0 - 2026-07-30", 1)[1].split("\n## ", 1)[0]
    assert "- Added a clean-machine acceptance leg." in promoted
    assert "- Bumped VerifySignal to `0.22.0`." in promoted
    assert "## 0.21.6 - 2026-07-30" in changelog


def test_bump_inserts_a_minimal_section_when_unreleased_is_absent(tmp_path):
    bump_version = _load_bump_version()
    root = _fixture_repo(tmp_path, "# Changelog\n\n## 0.21.6 - 2026-07-30\n\n- Older entry.\n")
    bump_version.bump_surfaces(root, "0.21.7", today=date(2026, 7, 31))
    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    section = changelog.split("## 0.21.7 - 2026-07-31", 1)[1].split("\n## ", 1)[0]
    assert "- Bumped VerifySignal to `0.21.7`." in section


def test_bump_refuses_when_a_declaration_is_not_found_exactly_once(tmp_path):
    bump_version = _load_bump_version()
    root = _fixture_repo(tmp_path, UNRELEASED_CHANGELOG)
    (root / "src/verifysignal_spec/__init__.py").write_text("no version here\n", encoding="utf-8")
    with pytest.raises(ValueError, match="exactly once"):
        bump_version.bump_surfaces(root, "0.22.0", today=date(2026, 7, 30))
    # All-or-nothing: the failed run must not have touched pyproject either.
    assert 'version = "0.21.6"' in (root / "pyproject.toml").read_text(encoding="utf-8")


def test_bump_refuses_a_malformed_target_version(tmp_path):
    bump_version = _load_bump_version()
    with pytest.raises(ValueError, match=r"MAJOR\.MINOR\.PATCH"):
        bump_version.bump_surfaces(_fixture_repo(tmp_path, UNRELEASED_CHANGELOG), "0.22")


def test_bump_refuses_a_noop_target(tmp_path):
    bump_version = _load_bump_version()
    with pytest.raises(ValueError, match="already at"):
        bump_version.bump_surfaces(_fixture_repo(tmp_path, UNRELEASED_CHANGELOG), "0.21.6")
