from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
README = ROOT / "README.md"
INSTALLATION = ROOT / "docs" / "installation.md"
MIGRATION = ROOT / "docs" / "distribution-migration.md"


def test_final_legacy_release_announces_the_canonical_distribution() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    readme = README.read_text(encoding="utf-8")
    installation = INSTALLATION.read_text(encoding="utf-8")

    assert 'name = "verifysignal-spec"' in pyproject
    assert "[Distribution name migration](docs/distribution-migration.md)" in readme
    assert "[distribution name migration](distribution-migration.md)" in installation
    assert MIGRATION.exists()

    migration = MIGRATION.read_text(encoding="utf-8")
    assert "final release line under the `verifysignal-spec` distribution name" in migration
    assert "uv tool install verifysignal" in migration
    assert "will not be deleted or yanked" in migration


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

    uv_uninstall = "uv tool uninstall verifysignal-spec"
    uv_install = "uv tool install verifysignal"
    pip_uninstall = "python -m pip uninstall verifysignal-spec"
    pip_install = "python -m pip install verifysignal"

    for command in (uv_uninstall, uv_install, pip_uninstall, pip_install):
        assert command in migration

    assert migration.index(uv_uninstall) < migration.index(uv_install)
    assert migration.index(pip_uninstall) < migration.index(pip_install)
    assert "must not be installed side by side" in migration
    assert "does not remove `.verifysignal/`" in migration
