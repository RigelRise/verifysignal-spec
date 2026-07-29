from __future__ import annotations

import json
import os
from pathlib import Path

from helpers import CliTestCase
from tests.fixtures.managed_runtime import (
    build_managed_runtime_distribution,
    serve_fake_entitlement_backend,
)
from tests.helpers import FAKE_CORE
from verifysignal_spec.runtime.distribution import normalize_platform
from verifysignal_spec.runtime.resolver import ensure_core_runtime
from verifysignal_spec.workspace.repository import (
    get_core_resolution_mode,
    init_workspace,
    load_document,
    save_document,
    save_core_configuration,
)


class CoreUpdateTests(CliTestCase):
    def setUp(self) -> None:
        super().setUp()
        os.environ["VERIFYSIGNAL_RUNTIME_CACHE_DIR"] = str(self.project / "managed-cache")
        os.environ["VERIFYSIGNAL_EMAIL_UNLOCK_TOKEN"] = "vs_valid"

    def tearDown(self) -> None:
        for key in [
            "VERIFYSIGNAL_RUNTIME_CACHE_DIR",
            "VERIFYSIGNAL_EMAIL_UNLOCK_TOKEN",
            "VERIFYSIGNAL_API_BASE_URL",
            "VERIFYSIGNAL_CORE_CMD",
            "VERIFYSIGNAL_CORE_VERSION",
        ]:
            os.environ.pop(key, None)
        super().tearDown()

    def test_reset_removes_local_resolution_and_enters_managed_only_mode(self) -> None:
        init_workspace(self.project)
        save_core_configuration(
            self.project,
            "npm --prefix ../local-core-checkout run verifysignal:dev --",
            source="ancestor-sibling",
            version="9.9.9",
        )

        code, out, err = self.cli(["core", "reset", "--project", str(self.project), "--json"])

        assert code == 0, err
        payload = json.loads(out)
        assert payload["schemaVersion"] == "verifysignal-spec-core-reset/v1"
        assert payload["status"] == "reset"
        assert payload["coreResolutionMode"] == "managed-only"
        workspace = load_document(self.project / ".verifysignal/workspace.yaml")
        assert workspace["coreResolutionMode"] == "managed-only"
        assert "coreCommand" not in workspace
        assert "coreCommandSource" not in workspace
        assert "coreVersion" not in workspace

    def test_workspace_without_resolution_metadata_keeps_legacy_resolution(self) -> None:
        init_workspace(self.project)
        workspace_path = self.project / ".verifysignal/workspace.yaml"
        workspace = load_document(workspace_path)
        workspace["coreCommand"] = str(FAKE_CORE)
        workspace.pop("coreResolutionMode", None)
        save_document(workspace_path, workspace)
        os.environ.pop("VERIFYSIGNAL_EMAIL_UNLOCK_TOKEN", None)

        readiness = ensure_core_runtime(self.project, context="version")

        assert get_core_resolution_mode(self.project) == "legacy-auto"
        assert readiness.status == "ready"
        assert readiness.source == "workspace"

    def test_managed_only_keeps_explicit_one_shot_override_without_persisting_it(self) -> None:
        init_workspace(self.project)
        code, _out, err = self.cli(
            ["core", "reset", "--project", str(self.project), "--json"]
        )
        assert code == 0, err
        os.environ.pop("VERIFYSIGNAL_EMAIL_UNLOCK_TOKEN", None)

        readiness = ensure_core_runtime(
            self.project,
            explicit_core_cmd=str(FAKE_CORE),
            context="version",
        )

        assert readiness.status == "ready"
        assert readiness.source == "explicit"
        workspace = load_document(self.project / ".verifysignal/workspace.yaml")
        assert workspace["coreResolutionMode"] == "managed-only"
        assert "coreCommand" not in workspace

    def test_update_ignores_every_local_source_and_ambient_version_pin(self) -> None:
        platform = normalize_platform() or "darwin-arm64"
        distribution = build_managed_runtime_distribution(
            self.project / "distribution",
            platform=platform,
            core_version="0.6.1",
        )
        init_workspace(self.project)
        save_core_configuration(
            self.project,
            "missing-workspace-core",
            source="ancestor-sibling",
            version="9.9.9",
        )
        os.environ["VERIFYSIGNAL_CORE_CMD"] = "missing-env-core"
        os.environ["VERIFYSIGNAL_CORE_VERSION"] = "0.0.1"

        with serve_fake_entitlement_backend(distribution) as (api_base_url, state):
            os.environ["VERIFYSIGNAL_API_BASE_URL"] = api_base_url
            code, out, err = self.cli(["core", "update", "--project", str(self.project), "--json"])

        assert code == 0, err
        payload = json.loads(out)
        assert payload["schemaVersion"] == "verifysignal-spec-core-update/v1"
        assert payload["status"] == "ready"
        assert payload["runtime"]["source"] == "managed-download"
        assert payload["runtime"]["runtimeVersion"] == "0.6.1"
        assert all(
            attempt["source"] not in {"workspace", "env", "path", "ancestor-sibling"}
            for attempt in payload["runtime"]["attempts"]
        )
        assert any("/runtimes/latest" in request["path"] for request in state.requests)
        workspace = load_document(self.project / ".verifysignal/workspace.yaml")
        assert workspace["coreResolutionMode"] == "managed-only"
        assert workspace["managedCoreVersion"] == "0.6.1"
        assert "coreCommand" not in workspace

    def test_update_reuses_only_the_exact_latest_verified_cache(self) -> None:
        platform = normalize_platform() or "darwin-arm64"
        distribution = build_managed_runtime_distribution(
            self.project / "distribution",
            platform=platform,
            core_version="0.6.1",
        )

        with serve_fake_entitlement_backend(distribution) as (api_base_url, _state):
            os.environ["VERIFYSIGNAL_API_BASE_URL"] = api_base_url
            first_code, first_out, first_err = self.cli(
                ["core", "update", "--project", str(self.project), "--json"]
            )
            assert first_code == 0, first_err
            assert json.loads(first_out)["runtime"]["source"] == "managed-download"

            second_code, second_out, second_err = self.cli(
                ["core", "update", "--project", str(self.project), "--json"]
            )

        assert second_code == 0, second_err
        second = json.loads(second_out)
        assert second["runtime"]["source"] == "managed-cache"
        assert second["runtime"]["cache"]["coreVersion"] == "0.6.1"

    def test_core_version_uses_active_managed_runtime_after_reset(self) -> None:
        platform = normalize_platform() or "darwin-arm64"
        distribution = build_managed_runtime_distribution(
            self.project / "distribution",
            platform=platform,
            core_version="0.6.1",
        )
        with serve_fake_entitlement_backend(distribution) as (api_base_url, _state):
            os.environ["VERIFYSIGNAL_API_BASE_URL"] = api_base_url
            code, _out, err = self.cli(
                ["core", "update", "--project", str(self.project), "--json"]
            )
        assert code == 0, err
        os.environ["VERIFYSIGNAL_CORE_CMD"] = "missing-local-core"

        code, out, err = self.cli(["core", "version", "--project", str(self.project), "--json"])

        assert code == 0, err
        payload = json.loads(out)
        assert payload["schema"] == "verifysignal.version/v1"
        assert payload["data"]["verifysignalVersion"] == "0.1.0"

    def test_failed_update_keeps_only_previous_verified_managed_fallback(self) -> None:
        platform = normalize_platform() or "darwin-arm64"
        distribution = build_managed_runtime_distribution(
            self.project / "distribution",
            platform=platform,
            core_version="0.6.1",
        )
        with serve_fake_entitlement_backend(distribution) as (api_base_url, _state):
            os.environ["VERIFYSIGNAL_API_BASE_URL"] = api_base_url
            code, _out, err = self.cli(
                ["core", "update", "--project", str(self.project), "--json"]
            )
        assert code == 0, err
        save_core_configuration(
            self.project,
            "missing-development-core",
            source="workspace",
            version="9.9.9",
        )

        with serve_fake_entitlement_backend(distribution) as (api_base_url, state):
            state.latest_status = "unavailable"
            os.environ["VERIFYSIGNAL_API_BASE_URL"] = api_base_url
            code, out, _err = self.cli(
                ["core", "update", "--project", str(self.project), "--json"]
            )

        assert code == 2
        payload = json.loads(out)
        assert payload["status"] == "blocked"
        assert payload["fallback"] == {
            "status": "active",
            "source": "managed-cache",
            "coreVersion": "0.6.1",
            "verified": True,
        }
        workspace = load_document(self.project / ".verifysignal/workspace.yaml")
        assert workspace["coreResolutionMode"] == "managed-only"
        assert workspace["managedCoreVersion"] == "0.6.1"
        assert "coreCommand" not in workspace
