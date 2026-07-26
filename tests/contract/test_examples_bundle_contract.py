"""The committed examples ship with evidence, so they must stay faithful to the
runtime's report schema instead of rotting into fiction. Every
``examples/<alias>/report.json`` is a passing ``qa-report/v1`` document whose
steps map to gates, and the write example carries a declared side-effect policy.
These are illustrative samples (see ``examples/README.md``)."""

import json
from pathlib import Path

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


def _reports():
    return sorted(EXAMPLES.glob("*/report.json"))


def test_examples_ship_reports():
    assert _reports(), "expected at least one examples/<alias>/report.json"


def test_example_reports_match_qa_report_v1():
    for report_path in _reports():
        data = json.loads(report_path.read_text(encoding="utf-8"))
        assert data["schemaVersion"] == "qa-report/v1", report_path
        assert data["status"] == "passed", report_path
        assert data["steps"], f"{report_path} has no steps"
        assert all(step.get("gateId") for step in data["steps"]), report_path


def test_write_example_declares_a_side_effect_policy():
    report_path = EXAMPLES / "checkout-write" / "report.json"
    data = json.loads(report_path.read_text(encoding="utf-8"))
    side_effects = data["sideEffects"]
    assert side_effects["policy"]["class"] == "write"
    assert side_effects["policy"]["mode"] == "enforce"
    assert side_effects["status"] == "committed-confirmed"
    assert side_effects["violations"] == []
