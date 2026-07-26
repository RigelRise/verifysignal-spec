from __future__ import annotations

from verifysignal_spec.integrations.claude import ClaudeIntegration
from verifysignal_spec.integrations.codex import CodexIntegration


def test_installed_codex_and_claude_templates_include_write_safety_contract_guidance(tmp_path) -> None:
    files = {item.path: item.content for item in CodexIntegration().render_files(tmp_path)}
    files.update({item.path: item.content for item in ClaudeIntegration().render_files(tmp_path)})
    combined = "\n".join(files.values())

    for phrase in [
        "sideEffectPolicy.allowed[]",
        "sideEffectPolicy.forbidden[]",
        "workflow supersede-write-outcome",
        "runtime-supported confirmation",
        "prepared/committed/discarded",
        "seed plus a run-attempt token",
        "Resolve `{{parameters.*}}` confirmation expected values before Core execution",
    ]:
        assert phrase in combined
    assert "hand-edit `.verifysignal/` `lastRun`" not in combined
    assert "verifysignal.probe/v1" in combined
    assert "verifysignal probe <run-request>" in combined
    assert "discover --storage-state" not in combined
    assert "developer-controlled `--storage-state`" not in combined
