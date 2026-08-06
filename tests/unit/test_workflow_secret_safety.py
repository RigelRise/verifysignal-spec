from __future__ import annotations

import pytest

from verifysignal_spec.workspace import layout
from verifysignal_spec.workspace.repository import init_workspace
from verifysignal_spec.workspace.repository import load_document
from verifysignal_spec.workspace.validation import validate_use_case
from verifysignal_spec.workspace.validation import validate_no_secret_values
from verifysignal_spec.workflows.core_setup import run_core_setup
from verifysignal_spec.workflows.stage_persistence import persist_stage
from verifysignal_spec.workflows.repository import save_workflow_state
from verifysignal_spec.workspace.models import RunProfile
from verifysignal_spec.workflows.models import RepairRecommendation, RuntimeEvidence, UseCaseValidationResult
from tests.fixtures.workflows.real_run_guardrails import coherent_profile_skill, create_real_run_guardrail_workspace, run_request_payload


def test_workflow_state_rejects_secret_values(tmp_path) -> None:
    init_workspace(tmp_path)
    with pytest.raises(ValueError):
        save_workflow_state(tmp_path, "login", {"schemaVersion": "verifysignal-spec-workflow-state/v1", "password": "real-secret-value"})


def test_stage_persistence_rejects_secret_values(tmp_path) -> None:
    init_workspace(tmp_path)
    result = persist_stage(
        tmp_path,
        "specify",
        alias="login",
        payload={
            "alias": "login",
            "surface": "/login",
            "behavior": "Validate login.",
            "expectedOutcome": "Dashboard.",
            "customSourceReason": "Secret safety fixture.",
            "apiToken": "abc123abc123abc123abc123abc123abc123",
        },
    )
    assert result["status"] == "invalid"


def test_profile_and_gate_metadata_secret_safety(tmp_path) -> None:
    create_real_run_guardrail_workspace(tmp_path)
    result = persist_stage(
        tmp_path,
        "implement",
        alias="profile-view-unauth",
        payload={
            "runRequest": run_request_payload(),
            "skills": [coherent_profile_skill()],
            "profiles": [{"name": "visual-15s", "headed": True, "slowMoMs": 15000}],
        },
    )
    assert result["status"] == "persisted"

    from verifysignal_spec.workspace.repository import load_use_case

    record = load_use_case(tmp_path, "profile-view-unauth")
    assert validate_use_case(tmp_path, record) == []
    record.profiles.append(RunProfile(name="debug-secret", description="bad", headed=True, slowMoMs=-1))
    findings = validate_use_case(tmp_path, record)
    assert any(item["code"] == "invalid-profile-slowmo" for item in findings)


def test_runtime_evidence_and_repair_recommendations_do_not_persist_secret_payloads() -> None:
    evidence = RuntimeEvidence(
        evidenceId="assert-profile-name",
        source="assertion",
        gateId="overview-data-card",
        status="passed",
        specificity="rendered-result",
        artifactRef=".verifysignal/runs/profile-view-unauth/evidence/overview.png",
        redactionStatus="not-sensitive",
    )
    recommendation = RepairRecommendation(
        id="repair-selector-ambiguity",
        category="safe-artifact-repair",
        safeCategory="selector-ambiguity",
        summary="Profile link locator matched multiple elements.",
        action="Narrow selector to a stable, unique target.",
        affectedArtifacts=[".verifysignal/skills/validate-profile-view-unauth-flow.browser.md"],
        sourceFeedback=["strict-mode-violation"],
    )
    result = UseCaseValidationResult(
        alias="profile-view-unauth",
        status="incomplete",
        coreStatus="passed",
        coverageStatus="incomplete",
        repairRecommendations=[recommendation],
        reportPath=".verifysignal/runs/profile-view-unauth/report.json",
        evidenceDir=".verifysignal/runs/profile-view-unauth/evidence",
        exitCode=2,
    )

    assert validate_no_secret_values(evidence.to_dict()) == []
    assert validate_no_secret_values(recommendation.to_dict()) == []
    assert validate_no_secret_values(result.to_dict()) == []


def test_target_environment_handoff_allows_non_secret_url_and_rejects_secret_like_values() -> None:
    safe = {
        "workflow": {
            "stageHandoffDecisions": [
                {
                    "key": "browserTargetEnvironment",
                    "valueSummary": "https://app.example.test",
                    "sourceStage": "clarify",
                    "status": "active",
                }
            ]
        }
    }
    unsafe = {
        "workflow": {
            "stageHandoffDecisions": [
                {
                    "key": "browserTargetEnvironment",
                    "valueSummary": "Bearer abc123abc123abc123abc123",
                    "sourceStage": "clarify",
                    "status": "active",
                }
            ]
        }
    }

    assert validate_no_secret_values(safe) == []
    assert validate_no_secret_values(unsafe)


def test_target_locator_rejects_credential_bearing_urls_and_token_queries() -> None:
    assert validate_no_secret_values({"target": "https://user:pass@example.com/app"})
    assert validate_no_secret_values({"target": "https://example.com/app?token=abc123abc123abc123"})
    assert validate_no_secret_values({"target": "https://example.com/app?api_key=abc123abc123abc123"})
    assert validate_no_secret_values({"target": "https://example.com/app#access_token=abc123abc123abc123"})


@pytest.mark.parametrize(
    "payload",
    [
        {"values": ["Bearer abc123abc123abc123abc123"]},
        {"values": [["Bearer abc123abc123abc123abc123"]]},
    ],
    ids=["direct-list-scalar", "nested-list-scalar"],
)
def test_secret_scanner_rejects_secret_scalars_inside_lists(
    payload: dict[str, object],
) -> None:
    assert validate_no_secret_values(payload)


@pytest.mark.parametrize(
    "locator",
    [
        "postgres://dbuser:dbpassword@example.test/app",
        "wss://example.test/socket?token=abc123abc123abc123",
    ],
    ids=["postgres-userinfo", "wss-query-token"],
)
def test_target_locator_rejects_credentials_in_non_http_uris(locator: str) -> None:
    assert validate_no_secret_values({"target": locator})


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("path", "https://user:pass@example.com/artifact"),
        (
            "reportPath",
            "https://example.com/report?token=abc123abc123abc123",
        ),
        (
            "evidenceDir",
            "https://example.com/evidence#access_token=abc123abc123abc123",
        ),
    ],
)
def test_artifact_path_exemptions_do_not_allow_secret_bearing_urls(
    field: str,
    value: str,
) -> None:
    assert validate_no_secret_values({field: value})


@pytest.mark.parametrize(
    "locator",
    [
        "//user:pass@example.com/app",
        "/callback?token=abc123abc123abc123",
        "user:pass@example.com",
    ],
)
def test_secret_scanner_rejects_credential_bearing_uri_references(
    locator: str,
) -> None:
    assert validate_no_secret_values({"reportPath": locator})


@pytest.mark.parametrize(
    "prose",
    [
        "Open https://user:pass@example.com/app for details.",
        "Retry /callback?token=abc123abc123abc123 after login.",
    ],
    ids=["absolute-userinfo", "relative-token-query"],
)
def test_secret_scanner_rejects_secret_locator_embedded_in_prose(
    prose: str,
) -> None:
    assert validate_no_secret_values({"summary": prose})


@pytest.mark.parametrize(
    "locator",
    [
        "mailto:qa@example.com?token=abc123abc123abc123",
        "Email mailto:qa@example.com?token=abc123abc123abc123 for help",
        "<https://user:pass@example.com/app>",
        "<https://example.com?token=abc123abc123abc123>",
        "https://example.test/login?redirect=https%3A%2F%2Fuser%3Apass%40private.test%2Fapp",
        "https://example.test/login?next=//user:pass@private.test/app",
        "Retry callback?token=abc123abc123abc123 after login",
        "The URL is ?token=abc123abc123abc123 here",
    ],
    ids=[
        "mailto-token-query",
        "mailto-token-query-in-prose",
        "markdown-autolink-userinfo",
        "markdown-autolink-token-query",
        "encoded-nested-userinfo-url",
        "protocol-relative-nested-userinfo-url",
        "bare-relative-token-query-in-prose",
        "query-only-token-in-prose",
    ],
)
def test_secret_scanner_rejects_additional_embedded_secret_uri_forms(
    locator: str,
) -> None:
    assert validate_no_secret_values({"reportPath": locator})


@pytest.mark.parametrize(
    ("payload", "expected_path"),
    [
        ({"password": "<actual-secret>"}, "password"),
        (
            {"reportPath": "<https://user:hunter2@example.com>"},
            "reportPath",
        ),
        (
            {"reportPath": "${PUBLIC} Bearer abcdefghijklmnop"},
            "reportPath",
        ),
        (
            {"reportPath": "https://user:hunter2@["},
            "reportPath",
        ),
    ],
    ids=[
        "angle-bracket-secret-field",
        "angle-bracket-userinfo-url",
        "placeholder-prefix-with-bearer",
        "malformed-userinfo-url",
    ],
)
def test_secret_scanner_rejects_placeholder_shaped_and_malformed_secret_values(
    payload: dict[str, object],
    expected_path: str,
) -> None:
    findings = validate_no_secret_values(payload)

    assert any(
        finding["severity"] == "blocking"
        and finding["code"] == "secret-looking-value"
        and finding["path"] == expected_path
        for finding in findings
    )


@pytest.mark.parametrize(
    "locator",
    [
        "C:reports@2026.json",
        "D:user:notes@example.txt",
        "https://example.test/posts?author=thiago",
        "https://example.test/docs?authority=public",
        "/search?authors=alice",
        "https://example.test/docs#author-bio",
    ],
    ids=[
        "windows-drive-relative-at-sign",
        "windows-drive-relative-colon-at-sign",
        "author-query",
        "authority-query",
        "authors-query",
        "author-fragment",
    ],
)
def test_secret_scanner_preserves_public_uri_and_windows_path_boundaries(
    locator: str,
) -> None:
    assert validate_no_secret_values({"reportPath": locator}) == []


@pytest.mark.parametrize(
    "payload",
    [
        {"tokenPolicy": {"value": "short-real-secret"}},
        {"passwordInput": {"value": "short-real-secret"}},
        {"targets": {"apiTokenField": {"value": "short-real-secret"}}},
        {"summary": "Basic dTpw"},
        {"summary": "A1b2C3d4E5f6G7h8I9j0-K1l2M3n4O5p6Q7r8"},
        {"reportPath": "https://example.test/?credential=actual-secret-value"},
        {"reportPath": f"https://example.test/?X-Amz-Signature={'a' * 64}"},
        {"reportPath": "https://example.test/?credentials[password]=hunter2"},
        {"reportPath": "https://example.test/?token[]=abc123"},
        {"reportPath": "C:notes See https://user:pass@example.com"},
        {"reportPath": "D:note https://example.test?token=actual-secret"},
        {
            "reportPath": (
                "https://example.test/?next="
                "Contact%20user%3Apass%40private.test%20now"
            )
        },
        {
            "reportPath": (
                "https://example.test/?next="
                "https%253A%252F%252Fuser%253Apass%2540private.test%252Fapp"
            )
        },
    ],
    ids=[
        "invalid-public-token-policy-shape",
        "invalid-root-password-input-shape",
        "invalid-selector-shape",
        "short-basic-credential",
        "base64url-high-entropy",
        "credential-query",
        "signed-url-query",
        "structured-credential-query",
        "array-token-query",
        "windows-prefix-embedded-userinfo",
        "windows-prefix-embedded-token-query",
        "encoded-nested-prose-userinfo",
        "double-encoded-nested-userinfo",
    ],
)
def test_secret_scanner_rejects_adversarial_secret_boundaries(
    payload: dict[str, object],
) -> None:
    assert validate_no_secret_values(payload)


def _assert_blocking_secret_safety_finding(
    findings: list[dict[str, str]],
    *,
    path: str | None = None,
) -> None:
    assert any(
        finding.get("severity") == "blocking"
        and finding.get("code", "").startswith("secret-")
        and (path is None or finding.get("path") == path)
        for finding in findings
    )


def _nested_list(value: object, *, depth: int) -> object:
    nested = value
    for _ in range(depth):
        nested = [nested]
    return nested


@pytest.mark.parametrize(
    "query",
    [
        "id_token=short-live-id-token",
        "X-Amz-Credential=AKIAREALVALUE",
        "X-Amz-Security-Token=short-session-secret",
    ],
    ids=["oauth-id-token", "aws-credential", "aws-security-token"],
)
def test_secret_scanner_residual_rejects_compound_secret_query_keys(
    query: str,
) -> None:
    findings = validate_no_secret_values(
        {"reportPath": f"https://example.test/callback?{query}"}
    )

    _assert_blocking_secret_safety_finding(findings, path="reportPath")


def test_secret_scanner_residual_windows_prefix_does_not_hide_scheme_less_userinfo() -> None:
    assert validate_no_secret_values({"reportPath": "C:reports@2026.json"}) == []

    findings = validate_no_secret_values(
        {"reportPath": "C:notes Contact user:pass@private.test"}
    )

    _assert_blocking_secret_safety_finding(findings, path="reportPath")


def test_secret_scanner_residual_rejects_short_bearer_credentials() -> None:
    assert (
        validate_no_secret_values(
            {"summary": "Bearer authentication is configured."}
        )
        == []
    )

    findings = validate_no_secret_values(
        {"summary": "Authorization header: Bearer abc123"}
    )

    _assert_blocking_secret_safety_finding(findings, path="summary")


@pytest.mark.parametrize(
    "value",
    [
        "a1b2c3d4e5f6g7h8i9j0-k1l2m3n4o5p6q7r8",
        "sk-live-prod-a1B2c3D4e5F6g7H8i9J0k1L2m3N4",
    ],
    ids=["two-character-classes", "multiple-hyphens"],
)
def test_secret_scanner_residual_rejects_hyphenated_opaque_tokens(
    value: str,
) -> None:
    findings = validate_no_secret_values({"summary": value})

    _assert_blocking_secret_safety_finding(findings, path="summary")


@pytest.mark.parametrize(
    "unsafe_policy",
    [
        {"refresh": "short-real-secret"},
        {"maxExchanges": "short-real-secret"},
    ],
    ids=["invalid-refresh-enum", "invalid-numeric-field-type"],
)
def test_secret_scanner_residual_token_policy_requires_documented_value_shape(
    unsafe_policy: dict[str, object],
) -> None:
    documented_policy = {
        "tokenPolicy": {
            "exchangeCount": 0,
            "hourlyExchangeCount": 0,
            "maxExchanges": 1,
            "maxExchangesPerHour": 1,
            "refresh": "silent-credential",
            "ttlDays": 30,
        }
    }
    assert validate_no_secret_values(documented_policy) == []

    findings = validate_no_secret_values({"tokenPolicy": unsafe_policy})

    _assert_blocking_secret_safety_finding(findings)


@pytest.mark.parametrize(
    "unsafe_selector",
    [
        {"nth": "short-real-secret"},
        {"domainSemantics": "short-real-secret"},
    ],
    ids=["invalid-nth-type", "missing-primary-signal"],
)
def test_secret_scanner_residual_selector_requires_documented_value_shape(
    unsafe_selector: dict[str, object],
) -> None:
    documented_selector = {
        "targets": {"apiTokenField": {"testId": "api-token-field"}}
    }
    assert validate_no_secret_values(documented_selector) == []

    findings = validate_no_secret_values(
        {"targets": {"apiTokenField": unsafe_selector}}
    )

    _assert_blocking_secret_safety_finding(findings)


def _assert_deep_finite_secret_scanning_control() -> None:
    safe = _nested_list("public metadata", depth=64)
    unsafe = _nested_list({"apiToken": "short-live-key"}, depth=64)

    assert validate_no_secret_values(safe) == []
    _assert_blocking_secret_safety_finding(validate_no_secret_values(unsafe))


def test_secret_scanner_residual_returns_blocker_for_cyclic_payload() -> None:
    _assert_deep_finite_secret_scanning_control()
    payload: dict[str, object] = {}
    payload["self"] = payload

    findings = validate_no_secret_values(payload)

    _assert_blocking_secret_safety_finding(findings)


def test_secret_scanner_residual_returns_blocker_for_depth_overflow() -> None:
    _assert_deep_finite_secret_scanning_control()
    payload = _nested_list("public metadata", depth=1_200)

    findings = validate_no_secret_values(payload)

    _assert_blocking_secret_safety_finding(findings)


@pytest.mark.parametrize(
    "payload",
    [
        {"summary": "Basic authentication is supported."},
        {"summary": "Bearer authentication is configured."},
        {
            "tokenPolicy": {
                "maxExchanges": 3,
                "maxExchangesPerHour": 3,
                "ttlDays": 30,
            }
        },
    ],
    ids=["basic-prose", "bearer-prose", "public-token-policy-shape"],
)
def test_secret_scanner_preserves_documented_public_boundaries(
    payload: dict[str, object],
) -> None:
    assert validate_no_secret_values(payload) == []


@pytest.mark.parametrize(
    "payload",
    [
        {"targets": {"currentPasswordInput": {"testId": "current-password-input"}}},
        {"targets": {"apiTokenField": {"testId": "api-token-field"}}},
        {"controls": {"resetPasswordButton": {"role": "button"}}},
    ],
    ids=[
        "password-input-target",
        "api-token-field-target",
        "reset-password-control",
    ],
)
def test_selector_alias_containers_do_not_propagate_secret_context(
    payload: dict[str, object],
) -> None:
    assert validate_no_secret_values(payload) == []


@pytest.mark.parametrize(
    "path",
    [
        "/callback?view=summary",
        r"C:\Users\example\report.json",
        "mailto:qa@example.com",
    ],
)
def test_secret_scanner_preserves_non_secret_relative_and_platform_paths(
    path: str,
) -> None:
    assert validate_no_secret_values({"reportPath": path}) == []


def test_target_locator_allows_safe_staging_and_local_urls() -> None:
    assert validate_no_secret_values({"target": "https://app.example.test"}) == []
    assert validate_no_secret_values({"target": "https://app.example.test/profile/jordan-rivera/overview"}) == []
    assert validate_no_secret_values({"target": "http://localhost:5002"}) == []


def test_artifact_fingerprints_allow_public_sha256_digests_only() -> None:
    safe = {
        "artifactFingerprints": {
            ".verifysignal/run-requests/add-collaboration-project.yaml": "a" * 64,
            ".verifysignal/skills/add-flow.browser.md": "sha256:" + "b" * 64,
        }
    }
    unsafe = {
        "artifactFingerprints": {
            ".verifysignal/run-requests/add-collaboration-project.yaml": "Bearer abcdefghijklmnopqrstuvwxyz123456"
        }
    }

    assert validate_no_secret_values(safe) == []
    findings = validate_no_secret_values(unsafe)
    assert findings
    assert findings[0]["code"] == "secret-looking-value"


def test_golden_path_example_docs_do_not_include_secret_values() -> None:
    from pathlib import Path

    content = Path("docs/golden-path.md").read_text(encoding="utf-8")

    assert "real-password" not in content.lower()
    assert "bearer " not in content.lower()
    assert "api_key=" not in content.lower()
    assert validate_no_secret_values({"goldenPathDocs": content}) == []


def test_understanding_public_metadata_values_are_not_secret_looking() -> None:
    safe = {
        "git": {"hash": "eb58ef8111e8e6bfd090303ef417ef0a6c7609a6", "branch": "feature/multi-actor"},
        "generatedGitHash": "eb58ef8111e8e6bfd090303ef417ef0a6c7609a6",
        "path": "app/(public)/page.tsx",
        "route": "/project/[path]",
        "candidateAlias": "project-multi-actor-add-people",
        "sourceInventoryItems": ["route-project"],
    }

    assert validate_no_secret_values(safe) == []


def test_secret_named_fields_still_reject_real_secret_values() -> None:
    unsafe = {"apiToken": "abc123abc123abc123abc123abc123abc123"}

    assert validate_no_secret_values(unsafe)


@pytest.mark.parametrize(
    ("payload", "expected_path"),
    [
        ({"apiKey": {"value": "short-live-key"}}, "apiKey.value"),
        (
            {"authorization": [{"value": "short-live-authorization"}]},
            "authorization[0].value",
        ),
    ],
    ids=["mapping", "nested-list"],
)
def test_secret_named_containers_keep_secret_field_context(
    payload: dict[str, object],
    expected_path: str,
) -> None:
    findings = validate_no_secret_values(payload)

    assert findings
    assert any(finding["path"] == expected_path for finding in findings)


@pytest.mark.parametrize(
    ("payload", "expected_path"),
    [
        ({"apiToken": {"value": "short-real-secret"}}, "apiToken.value"),
        (
            {"databasePassword": {"details": {"value": "short-real-secret"}}},
            "databasePassword.details.value",
        ),
    ],
    ids=["compound-api-token", "compound-password"],
)
def test_compound_secret_named_containers_keep_secret_field_context(
    payload: dict[str, object],
    expected_path: str,
) -> None:
    findings = validate_no_secret_values(payload)

    assert any(finding["path"] == expected_path for finding in findings)


@pytest.mark.parametrize(
    "value",
    [
        "Bearer abc123abc123abc123abc123",
        "0123456789abcdefghijklmnopqrstuvwxyzABCD",
    ],
    ids=["bearer", "high-entropy"],
)
def test_public_path_field_exemptions_do_not_allow_secret_content(value: str) -> None:
    findings = validate_no_secret_values({"reportPath": value})

    assert findings
    assert findings[0]["path"] == "reportPath"


@pytest.mark.parametrize(
    "secret_payload",
    [
        {"apiKey": {"value": "short-live-key"}},
        {"reportPath": "Bearer abc123abc123abc123abc123"},
    ],
    ids=["secret-named-container", "exempt-field-secret-content"],
)
def test_workflow_state_rejects_nested_secret_before_any_state_write(
    tmp_path,
    secret_payload: dict[str, object],
) -> None:
    init_workspace(tmp_path)
    state_path = layout.workflow_state_path(tmp_path, "login")

    with pytest.raises(ValueError):
        save_workflow_state(
            tmp_path,
            "login",
            {
                "schemaVersion": "verifysignal-spec-workflow-state/v1",
                **secret_payload,
            },
        )

    assert not state_path.exists()


def test_credential_refs_allow_env_key_names_but_reject_values() -> None:
    safe = {
        "credentialRefs": {
            "e2eUser": {
                "source": "environment",
                "keys": {
                    "email": "E2E_USER_EMAIL",
                    "password": "E2E_USER_PASSWORD",
                },
            }
        }
    }
    unsafe = {
        "credentialRefs": {
            "e2eUser": {
                "source": "environment",
                "keys": {
                    "email": "qa@example.com",
                    "password": "actual-secret-password-value",
                },
            }
        }
    }

    assert validate_no_secret_values(safe) == []
    assert validate_no_secret_values(unsafe)


def test_core_setup_does_not_read_env_files(tmp_path, monkeypatch) -> None:
    from tests.helpers import FAKE_CORE

    init_workspace(tmp_path)
    (tmp_path / ".env.local").write_text(f"VERIFYSIGNAL_CORE_CMD={FAKE_CORE}\n", encoding="utf-8")
    monkeypatch.delenv("VERIFYSIGNAL_CORE_CMD", raising=False)
    monkeypatch.setenv("PATH", "")

    result = run_core_setup(tmp_path)

    payload = result.to_dict()
    assert payload["status"] == "missing"
    assert str(FAKE_CORE) not in str(payload)
    workspace = load_document(tmp_path / ".verifysignal/workspace.yaml")
    assert "coreCommand" not in workspace


def test_core_setup_does_not_persist_or_echo_credential_looking_command(tmp_path) -> None:
    from tests.helpers import FAKE_CORE

    init_workspace(tmp_path)
    secret_command = f"{FAKE_CORE} --api-token super-secret-token-value"

    result = run_core_setup(tmp_path, explicit_core_cmd=secret_command)

    serialized = str(result.to_dict())
    assert result.status == "error"
    assert "super-secret-token-value" not in serialized
    assert "[redacted]" in serialized
    workspace = load_document(tmp_path / ".verifysignal/workspace.yaml")
    assert "coreCommand" not in workspace


def test_verification_key_readiness_status_contains_only_public_metadata() -> None:
    from verifysignal_spec.runtime.models import RuntimeVerificationKeyStatus

    status = RuntimeVerificationKeyStatus(
        status="ready",
        source="fetched",
        matchedKeyId="ps-entitlement-local",
        sourceApiBaseUrl="http://localhost:3000/api",
        issuer="https://verifysignal.io",
        message="Public verification keys are ready.",
    )

    payload = status.to_dict()
    assert validate_no_secret_values(payload) == []
    assert "receiptPayload" not in payload
    assert "privateKeyPem" not in payload
    assert "unlockToken" not in payload
