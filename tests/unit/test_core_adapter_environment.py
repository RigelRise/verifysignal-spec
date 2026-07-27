from __future__ import annotations

from pathlib import Path

from verifysignal_spec.core.adapter import CoreAdapter


def test_declared_environment_values_are_forwarded_to_each_protected_child(
    tmp_path,
    monkeypatch,
) -> None:
    adapter = CoreAdapter(executable="unused", cwd=tmp_path)
    monkeypatch.setattr(adapter, "require_compatible", lambda: None)
    captured: list[dict[str, str]] = []

    def fake_run(_args, env=None):
        captured.append(dict(env or {}))
        return {"status": "passed"}

    monkeypatch.setattr(adapter, "_run", fake_run)
    values = {"TEST_USER_EMAIL": "qa@example.test"}
    request = Path("request.yaml")
    skill = Path("skill.browser.md")

    adapter.authoring_check(request, skill, [skill], env=values)
    adapter.probe(request, skill, [skill], env=values)
    adapter.run(request, skill, [skill], env=values)

    assert [item["TEST_USER_EMAIL"] for item in captured] == [
        "qa@example.test",
        "qa@example.test",
        "qa@example.test",
    ]
