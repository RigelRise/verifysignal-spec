from __future__ import annotations

import json
import os

from helpers import FAKE_CORE, CliTestCase, assert_secret_canary_absent
from tests.fixtures.workflows.main_skill_run_coverage import (
    ALIAS,
    create_main_skill_coverage_workspace,
)
from verifysignal_spec.commands.validate import run as validate_run
from verifysignal_spec.core.adapter import CoreAdapter
from verifysignal_spec.runtime.distribution import normalize_platform
from tests.fixtures.managed_runtime import build_managed_runtime_distribution, serve_fake_entitlement_backend


class RuntimeSecretSafetyTests(CliTestCase):
    def tearDown(self) -> None:
        os.environ.pop("VERIFYSIGNAL_RUNTIME_CACHE_DIR", None)
        os.environ.pop("VERIFYSIGNAL_EMAIL_UNLOCK_TOKEN", None)
        os.environ.pop("VERIFYSIGNAL_API_BASE_URL", None)
        os.environ.pop("VERIFYSIGNAL_CORE_VERSION", None)
        super().tearDown()

    def test_raw_token_and_signed_url_do_not_enter_project_state_or_guidance(self) -> None:
        os.environ.pop("VERIFYSIGNAL_CORE_CMD", None)
        os.environ["VERIFYSIGNAL_RUNTIME_CACHE_DIR"] = str(self.project / "user-cache")
        os.environ["VERIFYSIGNAL_EMAIL_UNLOCK_TOKEN"] = "vs_valid"
        os.environ["VERIFYSIGNAL_CORE_VERSION"] = "0.5.1"
        platform = normalize_platform() or "darwin-arm64"
        distribution = build_managed_runtime_distribution(self.project / "distribution", platform=platform)

        with serve_fake_entitlement_backend(distribution) as (api_base_url, _state):
            os.environ["VERIFYSIGNAL_API_BASE_URL"] = api_base_url
            code, out, err = self.cli(["init", str(self.project), "--integration", "codex", "--json"])

        assert code == 0, err
        payload = json.loads(out)
        assert payload["runtime"]["status"] == "ready"
        project_text = "\n".join(path.read_text(encoding="utf-8") for path in (self.project / ".verifysignal").rglob("*") if path.is_file())
        guide_text = (self.project / ".agents" / "VERIFYSIGNAL_ONBOARDING.md").read_text(encoding="utf-8")
        assert "vs_valid" not in out + project_text + guide_text
        assert "X-Amz-Signature" not in out + project_text + guide_text


def test_normalized_core_outcome_keeps_only_the_public_safe_allowlist() -> None:
    from verifysignal_spec.core.outcomes import normalize_core_outcome

    canary = "VS_SECRET_CANARY_028_DO_NOT_PERSIST"
    outcome = normalize_core_outcome(
        "authoring-check",
        {
            "schema": "verifysignal.error/v1",
            "schemaVersion": 1,
            "operation": "authoring-check",
            "status": "error",
            "error": {
                "code": "entitlement.key-unknown",
                "message": f"receipt={canary}",
            },
            "execution": {
                "started": False,
                "phase": "pre-execution",
                "sideEffectMayExist": False,
            },
            "receipt": canary,
            "signature": canary,
            "verificationKey": canary,
            "environment": {"AUTH_TOKEN": canary},
            "data": {
                "findings": [
                    {
                        "code": "entitlement.expired",
                        "message": canary,
                    }
                ],
                "credential": canary,
            },
        },
    ).to_dict()

    serialized = json.dumps(outcome, sort_keys=True)
    assert outcome["errorCode"] == "entitlement.key-unknown"
    assert outcome["blockerCode"] == "entitlement.unverifiable"
    assert canary not in serialized
    for forbidden_key in (
        "receipt",
        "signature",
        "verificationKey",
        "environment",
        "credential",
        "message",
        "data",
    ):
        assert forbidden_key not in outcome


def test_protected_readiness_does_not_output_or_persist_raw_core_secrets(
    tmp_path,
    monkeypatch,
) -> None:
    canary = "VS_SECRET_CANARY_028_DO_NOT_PERSIST"
    create_main_skill_coverage_workspace(tmp_path)

    def authoring_error_with_canary(_self, *_args, **_kwargs):
        return {
            "schema": "verifysignal.error/v1",
            "schemaVersion": 1,
            "operation": "authoring-check",
            "status": "error",
            "error": {
                "code": "entitlement.key-unknown",
                "message": f"raw receipt {canary}",
            },
            "execution": {
                "started": False,
                "phase": "pre-execution",
                "sideEffectMayExist": False,
            },
            "data": {
                "findings": [
                    {
                        "severity": "blocking",
                        "code": "entitlement.expired",
                        "message": canary,
                    }
                ]
            },
            "receipt": canary,
            "verificationKey": canary,
            "environment": {"AUTH_TOKEN": canary},
        }

    monkeypatch.setattr(CoreAdapter, "authoring_check", authoring_error_with_canary)

    result = validate_run(
        tmp_path,
        ALIAS,
        runtime_readiness=True,
        core_cmd=str(FAKE_CORE),
    )

    assert result["status"] == "blocked"
    assert [item["code"] for item in result["blockers"]] == [
        "entitlement.unverifiable"
    ]
    assert_secret_canary_absent(tmp_path, canary, json.dumps(result, sort_keys=True))
