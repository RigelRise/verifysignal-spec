"""The package version must be declared consistently across the two sources of
truth (``pyproject.toml`` and ``verifysignal_spec.__version__``). The release
workflow tags off this value, so drift here would ship a mislabeled artifact.
See the version-impact guardrail in AGENTS.md."""

import tomllib
from pathlib import Path

from verifysignal_spec import __version__

PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"


def test_pyproject_version_matches_package_dunder():
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    assert data["project"]["version"] == __version__
