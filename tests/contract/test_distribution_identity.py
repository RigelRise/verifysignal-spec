from __future__ import annotations

import re
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _project() -> dict[str, object]:
    document = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return document["project"]


def test_canonical_distribution_preserves_both_cli_entrypoints_and_import_package() -> None:
    project = _project()

    assert project["name"] == "verifysignal"
    assert project["scripts"] == {
        "verifysignal": "verifysignal_spec.cli:main",
        "verifysignal-spec": "verifysignal_spec.cli:main",
    }
    assert (ROOT / "src" / "verifysignal_spec" / "__init__.py").is_file()


def test_first_canonical_release_keeps_the_live_pre_rename_repository_urls() -> None:
    urls = _project()["urls"]

    assert isinstance(urls, dict)
    assert urls
    assert all("github.com/RigelRise/verifysignal-spec" in value for value in urls.values())


def test_primary_install_guidance_and_badges_use_the_canonical_distribution() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    installation = (ROOT / "docs" / "installation.md").read_text(encoding="utf-8")

    for text in (readme, installation):
        assert re.search(r"\buv tool install verifysignal(?:\s|$)", text)
        assert not re.search(r"\buv tool install verifysignal-spec\b", text)

    assert "https://pypi.org/project/verifysignal/" in readme
    assert "img.shields.io/pypi/v/verifysignal?" in readme
    assert "img.shields.io/pypi/pyversions/verifysignal" in readme


def test_active_public_prose_uses_verify_signal_and_runtime_names() -> None:
    public_paths = (
        "docs/golden-path.md",
        "docs/browser-first-understanding.md",
        "docs/managed-runtime-entitlement-handoff.md",
        "src/verifysignal_spec/integrations/base.py",
        "src/verifysignal_spec/integrations/claude.py",
        "src/verifysignal_spec/integrations/codex.py",
        "src/verifysignal_spec/templates/agent-commands/verifysignal.list.md",
        "src/verifysignal_spec/templates/agent-commands/verifysignal.repair.md",
        "src/verifysignal_spec/templates/agent-commands/verifysignal.run.md",
        "src/verifysignal_spec/templates/agent-commands/verifysignal.validate.md",
        "src/verifysignal_spec/templates/agent-skills/claude/CLAUDE.md",
        "src/verifysignal_spec/templates/agent-skills/codex/AGENTS.md",
    )

    offenders = [
        path
        for path in public_paths
        if "VerifySignal Spec" in (ROOT / path).read_text(encoding="utf-8")
    ]
    assert offenders == []

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "VerifySignal Runtime" in readme
    assert "VerifySignal Core" not in readme


def test_source_does_not_reintroduce_the_retired_public_spec_product_name() -> None:
    source_root = ROOT / "src" / "verifysignal_spec"
    offenders = [
        str(path.relative_to(ROOT))
        for path in sorted(source_root.rglob("*"))
        if path.is_file()
        and path.suffix in {".py", ".md", ".yaml"}
        and "VerifySignal Spec" in path.read_text(encoding="utf-8")
    ]

    assert offenders == []
