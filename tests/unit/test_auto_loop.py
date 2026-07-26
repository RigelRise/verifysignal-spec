from __future__ import annotations

import unittest
from pathlib import Path

from verifysignal_spec.core.adapter import CoreAdapter
from verifysignal_spec.core.contracts import core_supports_crystallize, core_supports_discover, core_supports_probe
from verifysignal_spec.integrations.base import WORKFLOW_COMMANDS, render_workflow_skill_files
from verifysignal_spec.workflows.models import WORKFLOW_STAGES
from verifysignal_spec.workflows.stage_persistence import PERSISTABLE_STAGES


class _CapturingAdapter(CoreAdapter):
    """Capture the argv passed to Core without spawning a subprocess."""

    def __init__(self) -> None:
        super().__init__(executable="x")
        self.calls: list[tuple[list[str], dict | None]] = []

    def require_compatible(self):  # type: ignore[override]
        return None

    def _run(self, args, env=None):  # type: ignore[override]
        self.calls.append((args, env))
        return {"status": "passed", "data": {}}


def _version_response(operations: list[dict]) -> dict:
    return {"data": {"operations": operations}}


class AutoLoopAdapterTests(unittest.TestCase):
    def test_discover_builds_expected_argv(self) -> None:
        adapter = _CapturingAdapter()
        adapter.discover(url="http://127.0.0.1:3120", skill=Path("draft.browser.md"))
        args, _ = adapter.calls[-1]
        self.assertEqual(args, ["discover", "--url", "http://127.0.0.1:3120", "--skill", "draft.browser.md", "--json"])

    def test_discover_passes_headed_flag(self) -> None:
        adapter = _CapturingAdapter()
        adapter.discover(url="http://x", skill=Path("s.md"), headed=True)
        args, _ = adapter.calls[-1]
        self.assertIn("--headed", args)

    def test_probe_builds_expected_argv_without_session_or_credential_values(self) -> None:
        adapter = _CapturingAdapter()
        adapter.probe(
            run_request=Path("request.yaml"),
            main_skill=Path("main.browser.md"),
            skills=[Path("main.browser.md"), Path("login.browser.md")],
            headed=True,
            slow_mo_ms=250,
        )
        args, _ = adapter.calls[-1]
        self.assertEqual(
            args,
            [
                "probe",
                "request.yaml",
                "--skill",
                "main.browser.md",
                "--skill",
                "login.browser.md",
                "--headed",
                "--slow-mo",
                "250",
                "--json",
            ],
        )
        rendered = " ".join(args)
        self.assertNotIn("storage-state", rendered)
        self.assertNotIn("password", rendered.lower())

    def test_crystallize_builds_expected_argv(self) -> None:
        adapter = _CapturingAdapter()
        adapter.crystallize(run_dir=Path(".verifysignal/runs/login/fake-run-1"))
        args, _ = adapter.calls[-1]
        self.assertEqual(args, ["crystallize", ".verifysignal/runs/login/fake-run-1", "--json"])

    def test_crystallize_passes_out_dir(self) -> None:
        adapter = _CapturingAdapter()
        adapter.crystallize(run_dir=Path("run"), out=Path("fixtures/out"))
        args, _ = adapter.calls[-1]
        self.assertEqual(args, ["crystallize", "run", "--out", "fixtures/out", "--json"])

    def test_run_passes_record_and_replay_flags(self) -> None:
        adapter = _CapturingAdapter()
        adapter.run(
            run_request=Path("req.yaml"),
            main_skill=Path("main.browser.md"),
            skills=[Path("main.browser.md")],
            record=True,
            replay=Path("fixtures/login"),
        )
        args, _ = adapter.calls[-1]
        self.assertIn("--record", args)
        self.assertEqual(args[args.index("--replay") + 1], "fixtures/login")
        # additive flags land before the trailing --json sentinel
        self.assertEqual(args[-1], "--json")
        self.assertLess(args.index("--record"), args.index("--json"))
        self.assertLess(args.index("--replay"), args.index("--json"))

    def test_run_omits_record_and_replay_by_default(self) -> None:
        adapter = _CapturingAdapter()
        adapter.run(
            run_request=Path("req.yaml"),
            main_skill=Path("main.browser.md"),
            skills=[Path("main.browser.md")],
        )
        args, _ = adapter.calls[-1]
        self.assertNotIn("--record", args)
        self.assertNotIn("--replay", args)


class CoreSupportsDiscoverTests(unittest.TestCase):
    def test_true_when_discover_advertised(self) -> None:
        response = _version_response(
            [
                {"name": "run", "schema": "verifysignal.run/v1"},
                {"name": "discover", "schema": "verifysignal.discover/v1", "status": "experimental"},
            ]
        )
        self.assertTrue(core_supports_discover(response))

    def test_false_when_absent(self) -> None:
        response = _version_response([{"name": "run", "schema": "verifysignal.run/v1"}])
        self.assertFalse(core_supports_discover(response))

    def test_false_on_wrong_schema(self) -> None:
        response = _version_response([{"name": "discover", "schema": "verifysignal.discover/v2"}])
        self.assertFalse(core_supports_discover(response))

    def test_false_on_malformed(self) -> None:
        self.assertFalse(core_supports_discover({}))
        self.assertFalse(core_supports_discover({"data": {"operations": "nope"}}))


class CoreSupportsProbeTests(unittest.TestCase):
    def test_true_only_for_exact_probe_v1_metadata(self) -> None:
        response = _version_response(
            [
                {
                    "name": "probe",
                    "schema": "verifysignal.probe/v1",
                    "schemaVersion": 1,
                    "status": "experimental",
                }
            ]
        )
        self.assertTrue(core_supports_probe(response))

    def test_false_when_absent_or_schema_version_differs(self) -> None:
        self.assertFalse(core_supports_probe(_version_response([])))
        self.assertFalse(
            core_supports_probe(
                _version_response(
                    [
                        {
                            "name": "probe",
                            "schema": "verifysignal.probe/v1",
                            "schemaVersion": 2,
                        }
                    ]
                )
            )
        )
        self.assertFalse(
            core_supports_probe(
                _version_response(
                    [
                        {
                            "name": "probe",
                            "schema": "verifysignal.probe/v2",
                            "schemaVersion": 1,
                        }
                    ]
                )
            )
        )


class CoreSupportsCrystallizeTests(unittest.TestCase):
    def test_true_when_crystallize_advertised(self) -> None:
        response = _version_response(
            [
                {"name": "run", "schema": "verifysignal.run/v1"},
                {"name": "crystallize", "schema": "verifysignal.crystallize/v1", "status": "experimental"},
            ]
        )
        self.assertTrue(core_supports_crystallize(response))

    def test_false_when_absent(self) -> None:
        response = _version_response([{"name": "run", "schema": "verifysignal.run/v1"}])
        self.assertFalse(core_supports_crystallize(response))

    def test_false_on_wrong_schema(self) -> None:
        response = _version_response([{"name": "crystallize", "schema": "verifysignal.crystallize/v2"}])
        self.assertFalse(core_supports_crystallize(response))

    def test_false_on_malformed(self) -> None:
        self.assertFalse(core_supports_crystallize({}))
        self.assertFalse(core_supports_crystallize({"data": {"operations": "nope"}}))


class AutoCommandRegistrationTests(unittest.TestCase):
    def test_auto_installed_for_both_agents_as_bare_verifysignal(self) -> None:
        for agent, root in (("Claude", ".claude/skills"), ("Codex", ".agents/skills")):
            paths = [rendered.path for rendered in render_workflow_skill_files(root, agent)]
            self.assertIn(f"{root}/verifysignal/SKILL.md", paths)
            self.assertNotIn(f"{root}/verifysignal-auto/SKILL.md", paths)

    def test_auto_is_a_command_not_a_persistable_stage(self) -> None:
        command_stages = [spec.stage for spec in WORKFLOW_COMMANDS]
        self.assertIn("auto", command_stages)
        self.assertNotIn("auto", WORKFLOW_STAGES)
        self.assertNotIn("auto", PERSISTABLE_STAGES)

    def test_auto_template_uses_probe_for_writes_and_never_invents_storage_state_flags(self) -> None:
        rendered = "\n".join(
            item.content
            for item in render_workflow_skill_files(".agents/skills", "Codex")
            if item.path.endswith("/verifysignal/SKILL.md")
        )
        self.assertIn("verifysignal.probe/v1", rendered)
        self.assertIn("verifysignal probe <run-request>", rendered)
        self.assertIn("boundary.executed", rendered)
        self.assertIn("explicit developer confirmation", rendered)
        self.assertIn("authenticated read-only flow without probe", rendered)
        self.assertIn("recommend upgrading", rendered)
        self.assertIn("Do not substitute `discover`", rendered)
        self.assertNotIn("discover --storage-state", rendered)
        self.assertNotIn("developer-controlled `--storage-state`", rendered)


if __name__ == "__main__":
    unittest.main()
