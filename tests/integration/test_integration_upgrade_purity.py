from __future__ import annotations

from verifysignal_spec.commands import integration
from verifysignal_spec.workspace.repository import init_workspace


def test_upgrade_regenerates_integrations_without_resolving_or_setting_up_core(
    tmp_path, monkeypatch
) -> None:
    init_workspace(tmp_path)
    integration.install(tmp_path, "codex", force=True)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("integration upgrade must not resolve or set up Core")

    monkeypatch.setattr(integration, "ensure_core_runtime", forbidden)
    monkeypatch.setattr(integration, "run_core_setup", forbidden)

    result = integration.upgrade(tmp_path, "codex", force=True)

    upgraded = result["upgraded"][0]
    assert upgraded["runtime"]["status"] == "not-checked"
    assert upgraded["coreSetup"]["status"] == "not-checked"
