from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

from helpers import CliTestCase, FAKE_CORE
from verifysignal_spec.core.adapter import CoreAdapter, readiness, resolve_persistable_core_command
from verifysignal_spec.core.errors import CoreIncompatibleError, CoreMissingError
from verifysignal_spec.runtime.distribution import save_verification_keys


class CoreAdapterTests(CliTestCase):
    def test_compatible_version_contract(self) -> None:
        result = CoreAdapter(executable=str(FAKE_CORE), cwd=self.project).check_compatibility()
        self.assertTrue(result.compatible)
        self.assertEqual(result.contractVersion, "verifysignal-public-cli-json/v1")

    def test_incompatible_contract_blocks(self) -> None:
        os.environ["FAKE_VERIFYSIGNAL_MODE"] = "incompatible"
        with self.assertRaises(CoreIncompatibleError):
            CoreAdapter(executable=str(FAKE_CORE), cwd=self.project).require_compatible()

    def test_missing_core_readiness_is_reported(self) -> None:
        result = readiness(executable="definitely-not-verifysignal", cwd=self.project)
        self.assertFalse(result["available"])
        self.assertFalse(result["compatible"])

    def test_unconfigured_adapter_never_falls_back_to_public_spec_cli(self) -> None:
        os.environ.pop("VERIFYSIGNAL_CORE_CMD", None)

        with self.assertRaisesRegex(
            CoreMissingError,
            "Core command is not configured",
        ):
            CoreAdapter(cwd=self.project).version()

    def test_directory_core_command_maps_to_npm_repo(self) -> None:
        core_repo = self.project / "verifysignal"
        core_repo.mkdir()
        (core_repo / "package.json").write_text("{}", encoding="utf-8")
        command = CoreAdapter(executable=str(core_repo), cwd=self.project)._base_command()
        self.assertEqual(command[:4], ["npm", "--silent", "--prefix", str(core_repo.resolve())])

    def test_persistable_core_command_resolves_directories(self) -> None:
        core_repo = self.project / "verifysignal"
        core_repo.mkdir()
        (core_repo / "package.json").write_text("{}", encoding="utf-8")

        command = resolve_persistable_core_command(str(core_repo), cwd=self.project)

        self.assertNotEqual(command, str(core_repo))
        self.assertIn("verifysignal:dev", command)

    def test_command_string_is_supported(self) -> None:
        command = CoreAdapter(executable=f"{FAKE_CORE} version-wrapper", cwd=self.project)._base_command()
        self.assertEqual(command[0], str(FAKE_CORE))
        self.assertEqual(command[1], "version-wrapper")

    def test_probe_preserves_skill_order_and_threads_only_public_options(self) -> None:
        adapter = CoreAdapter(executable=str(FAKE_CORE), cwd=self.project)
        captured: list[list[str]] = []
        adapter.require_compatible = lambda: None  # type: ignore[method-assign]
        adapter._run = lambda args, env=None: captured.append(args) or {"status": "passed"}  # type: ignore[method-assign]

        adapter.probe(
            Path("request.yaml"),
            Path("main.browser.md"),
            [Path("main.browser.md"), Path("login.browser.md")],
            headed=True,
            slow_mo_ms=125,
        )

        self.assertEqual(
            captured,
            [
                [
                    "probe",
                    "request.yaml",
                    "--skill",
                    "main.browser.md",
                    "--skill",
                    "login.browser.md",
                    "--headed",
                    "--slow-mo",
                    "125",
                    "--json",
                ]
            ],
        )

    def test_packaged_runtime_uses_packaged_trust_instead_of_cached_environment_keys(self) -> None:
        save_verification_keys(
            {
                "schema": "verifysignal.entitlement-keys/v1",
                "schemaVersion": 1,
                "keys": [
                    {
                        "keyId": "verifysignal-local-entitlement",
                        "algorithm": "ed25519",
                        "publicKeyPem": "public-only-test-material",
                        "status": "active",
                    }
                ],
            }
        )
        compatibility = CoreAdapter(executable=str(FAKE_CORE), cwd=self.project).check_compatibility()
        assert compatibility.raw is not None
        compatibility.raw["data"]["runtime"] = {
            "executable": "verifysignal-core",
            "packageId": "verifysignal-core-0.6.0-test",
            "platform": "test",
        }
        adapter = CoreAdapter(executable=str(FAKE_CORE), cwd=self.project)
        captured: list[dict[str, str]] = []
        adapter.require_compatible = lambda: compatibility  # type: ignore[method-assign]
        adapter._run = lambda args, env=None: captured.append(env or {}) or {"status": "passed"}  # type: ignore[method-assign]

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("VERIFYSIGNAL_ENTITLEMENT_PUBLIC_KEYS_JSON", None)
            adapter.authoring_check(
                Path("request.yaml"),
                Path("main.browser.md"),
                [Path("main.browser.md")],
                runtime_readiness=True,
                entitlement_receipt=Path("receipt.json"),
            )

        self.assertEqual(captured[0]["VERIFYSIGNAL_ENTITLEMENT_RECEIPT"], "receipt.json")
        self.assertNotIn("VERIFYSIGNAL_ENTITLEMENT_PUBLIC_KEYS_JSON", captured[0])

    def test_source_runtime_keeps_cached_environment_key_handoff(self) -> None:
        save_verification_keys(
            {
                "schema": "verifysignal.entitlement-keys/v1",
                "schemaVersion": 1,
                "keys": [
                    {
                        "keyId": "verifysignal-local-entitlement",
                        "algorithm": "ed25519",
                        "publicKeyPem": "public-only-test-material",
                        "status": "active",
                    }
                ],
            }
        )
        compatibility = CoreAdapter(executable=str(FAKE_CORE), cwd=self.project).check_compatibility()
        adapter = CoreAdapter(executable=str(FAKE_CORE), cwd=self.project)
        captured: list[dict[str, str]] = []
        adapter.require_compatible = lambda: compatibility  # type: ignore[method-assign]
        adapter._run = lambda args, env=None: captured.append(env or {}) or {"status": "passed"}  # type: ignore[method-assign]

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("VERIFYSIGNAL_ENTITLEMENT_PUBLIC_KEYS_JSON", None)
            adapter.authoring_check(
                Path("request.yaml"),
                Path("main.browser.md"),
                [Path("main.browser.md")],
                runtime_readiness=True,
                entitlement_receipt=Path("receipt.json"),
            )

        self.assertIn("VERIFYSIGNAL_ENTITLEMENT_PUBLIC_KEYS_JSON", captured[0])
