from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
README = ROOT / "README.md"
INSTALLATION = ROOT / "docs" / "installation.md"
MIGRATION = ROOT / "docs" / "distribution-migration.md"


def test_canonical_release_keeps_the_final_legacy_release_migration_notice() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    readme = README.read_text(encoding="utf-8")
    installation = INSTALLATION.read_text(encoding="utf-8")

    assert 'name = "verifysignal"' in pyproject
    assert "[Distribution name migration](docs/distribution-migration.md)" in readme
    assert "[distribution name migration](distribution-migration.md)" in installation
    assert MIGRATION.exists()

    migration = MIGRATION.read_text(encoding="utf-8")
    assert "final release line under the `verifysignal-spec` distribution name" in migration
    assert "uv tool install verifysignal" in migration
    assert "will not be deleted or yanked" in migration


def test_migration_versions_follow_the_current_release_line() -> None:
    readme = README.read_text(encoding="utf-8")
    installation = INSTALLATION.read_text(encoding="utf-8")
    migration = MIGRATION.read_text(encoding="utf-8")

    for text in (readme, installation, migration):
        assert "0.25.x" in text
        assert "0.22.x" not in text

    assert "`verifysignal` 0.26.0 or newer" in migration
    assert "0.23.0" not in migration


def test_migration_notice_freezes_technical_compatibility_identifiers() -> None:
    migration = MIGRATION.read_text(encoding="utf-8")

    for preserved_identity in (
        "`verifysignal_spec`",
        "`verifysignal-spec` executable alias",
        "`verifysignal-spec-*/v1`",
        "`.verifysignal/`",
        "`VERIFYSIGNAL_SPEC_*`",
        "`spec` workflow role",
        "`/verifysignal-specify`",
    ):
        assert preserved_identity in migration


def test_migration_notice_replaces_the_old_distribution_before_installing_the_new_one() -> None:
    migration = MIGRATION.read_text(encoding="utf-8")
    replacement = migration.split("## Moving an existing installation", 1)[1]

    uv_uninstall = "uv tool uninstall verifysignal-spec"
    uv_install = "uv tool install verifysignal"
    pip_uninstall = "python -m pip uninstall verifysignal-spec"
    pip_install = "python -m pip install verifysignal"

    for command in (uv_uninstall, uv_install, pip_uninstall, pip_install):
        assert command in replacement

    assert replacement.index(uv_uninstall) < replacement.index(uv_install)
    assert replacement.index(pip_uninstall) < replacement.index(pip_install)
    assert "must not be installed side by side" in replacement
    assert "does not remove `.verifysignal/`" in replacement


def test_first_canonical_release_uses_canonical_pypi_and_pre_rename_oidc_identity() -> None:
    release_workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )
    version_workflow = (
        ROOT / ".github" / "workflows" / "version-bump.yml"
    ).read_text(encoding="utf-8")

    assert "repo=verifysignal-spec, workflow=release.yml, environment=pypi" in release_workflow
    assert "url: https://pypi.org/project/verifysignal/" in release_workflow
    assert 'git commit -m "chore(release): bump verifysignal to ${NEXT}"' in version_workflow
