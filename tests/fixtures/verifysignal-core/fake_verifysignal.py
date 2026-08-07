#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def main() -> int:
    args = sys.argv[1:]
    mode = os.environ.get("FAKE_VERIFYSIGNAL_MODE", "ok").replace("_", "-")
    protected_operation = _protected_operation(args)
    protected = protected_operation is not None
    protected_fixture_modes = {
        "current-entitlement-error",
        "legacy-entitlement-error",
        "malformed-protected-response",
        "operation-mismatched-response",
    }
    if protected_operation in {"authoring-check", "run"} and mode in protected_fixture_modes:
        payload, exit_code = _protected_fixture_response(mode, protected_operation)
        print(json.dumps(payload))
        return exit_code
    if protected and mode in {"requires-entitlement", "rejects-entitlement", "expired-entitlement", "malformed-entitlement"}:
        receipt_path = os.environ.get("VERIFYSIGNAL_ENTITLEMENT_RECEIPT")
        error_code = None
        if not receipt_path:
            error_code = "entitlement.missing"
        elif mode == "rejects-entitlement":
            error_code = "entitlement.policy-denied"
        elif mode == "expired-entitlement":
            error_code = "entitlement.expired"
        elif mode == "malformed-entitlement":
            error_code = "entitlement.malformed"
        else:
            receipt_key_id = _receipt_key_id(receipt_path)
            if receipt_key_id and not _public_keys_include(receipt_key_id):
                error_code = "entitlement.key-unknown"
        if error_code:
            print(
                json.dumps(
                    {
                        "schema": "verifysignal.error/v1",
                        "schemaVersion": 1,
                        "operation": args[0] if args else "unknown",
                        "status": "blocked",
                        "data": {
                            "findings": [
                                {
                                    "severity": "blocking",
                                    "code": error_code,
                                    "message": "Entitlement receipt was rejected by Core.",
                                }
                            ]
                        },
                    }
                )
            )
            return 2
    if args[:2] == ["version", "--json"]:
        if mode == "incompatible":
            payload = {
                "schema": "verifysignal.version/v1",
                "schemaVersion": 1,
                "operation": "version",
                "status": "passed",
                "data": {"verifysignalVersion": "0.0.0", "contractVersion": "old", "operations": []},
            }
        else:
            operations = [
                {"name": "version", "schema": "verifysignal.version/v1", "schemaVersion": 1, "status": "stable"},
                {"name": "contracts", "schema": "verifysignal.contracts/v1", "schemaVersion": 1, "status": "stable"},
                {"name": "authoring-check", "schema": "verifysignal.authoring-check/v1", "schemaVersion": 1, "status": "stable"},
                {"name": "run", "schema": "verifysignal.run/v1", "schemaVersion": 1, "status": "stable"},
                {"name": "report.inspect", "schema": "verifysignal.report-inspection/v1", "schemaVersion": 1, "status": "stable"},
                {"name": "crystallize", "schema": "verifysignal.crystallize/v1", "schemaVersion": 1, "status": "experimental"},
            ]
            if mode == "missing-contracts-operation":
                operations = [operation for operation in operations if operation["name"] != "contracts"]
            if mode == "missing-report-inspect":
                operations = [operation for operation in operations if operation["name"] != "report.inspect"]
            if mode == "incompatible-run-schema":
                for operation in operations:
                    if operation["name"] == "run":
                        operation["schema"] = "verifysignal.run/v2"
                        operation["schemaVersion"] = 2
            if mode == "advertises-discover":
                operations.append({"name": "discover", "schema": "verifysignal.discover/v1", "schemaVersion": 1, "status": "experimental"})
            if mode == "advertises-probe":
                operations.append({"name": "probe", "schema": "verifysignal.probe/v1", "schemaVersion": 1, "status": "experimental"})
            if mode == "omits-crystallize":
                # A compatible Core that simply predates crystallization: every REQUIRED operation is
                # present, only the optional one is absent.
                operations = [operation for operation in operations if operation["name"] != "crystallize"]
            if mode == "advertises-run-modes" or os.environ.get("FAKE_VERIFYSIGNAL_ADVERTISE_RUN_MODES") == "1":
                # A Core that advertises run's record/replay MODES (the default fake predates the
                # advertisement, standing in for an older Core that cannot serve --record/--replay).
                # The env flag composes with any behavior mode (e.g. full-coverage + advertised modes).
                for operation in operations:
                    if operation["name"] == "run":
                        operation["modes"] = ["record", "replay"]
            payload = {
                "schema": "verifysignal.version/v1",
                "schemaVersion": 1,
                "operation": "version",
                "status": "passed",
                "data": {
                    "verifysignalVersion": "0.1.0",
                    "contractVersion": "verifysignal-public-cli-json/v1",
                    "operations": operations,
                },
            }
        print(json.dumps(payload))
        return 0
    if args[:2] == ["contracts", "--json"]:
        _increment_contract_counter()
        if mode == "contracts-non-json":
            print("not json")
            return 0
        if mode == "contracts-failed":
            print(
                json.dumps(
                    {
                        "schema": "verifysignal.error/v1",
                        "schemaVersion": 1,
                        "operation": "contracts",
                        "status": "blocked",
                        "data": {
                            "findings": [
                                {
                                    "severity": "blocking",
                                    "code": "contracts.unavailable",
                                    "message": "Core public contract is unavailable.",
                                }
                            ]
                        },
                    }
                )
            )
            return 2
        contract = _contracts_payload(mode)
        print(json.dumps(contract))
        return 0
    if args[:2] == ["authoring-check", "run-request"]:
        status = "blocked" if mode == "blocked" else "passed"
        findings = []
        if status == "blocked":
            findings.append(
                {
                    "severity": "blocking",
                    "code": "unresolved-placeholder-marker",
                    "artifact": args[2],
                    "path": "parameters.baseUrl",
                    "message": "Missing baseUrl.",
                    "suggestedFix": "Declare baseUrl as a runtime input.",
                }
            )
        print(
            json.dumps(
                {
                    "schema": "verifysignal.authoring-check/v1",
                    "schemaVersion": 1,
                    "operation": "authoring-check",
                    "status": status,
                    "data": {
                        "artifacts": [{"kind": "runRequest", "path": args[2], "exists": True}],
                        "summary": {"blockers": len(findings), "warnings": 0},
                        "findings": findings,
                        "requiredRuntimeInputs": [],
                        "credentialGroups": [],
                    },
                }
            )
        )
        return 0
    if args and args[0] == "probe":
        print(
            json.dumps(
                {
                    "schema": "verifysignal.probe/v1",
                    "schemaVersion": 1,
                    "operation": "probe",
                    "status": "passed",
                    "data": {
                        "args": args,
                        "fullFlowExecuted": False,
                        "boundary": {
                            "stepId": "publish",
                            "reached": True,
                            "executed": False,
                        },
                        "targets": [],
                        "deferred": {
                            "steps": ["publish"],
                            "assertions": [],
                            "runtimeOutputs": [],
                            "confirmations": [],
                        },
                    },
                }
            )
        )
        return 0
    if args and args[0] == "run":
        run_id = os.environ.get("FAKE_VERIFYSIGNAL_RUN_ID", "fake-run-1")
        headed = "--headed" in args
        record = "--record" in args
        replay = None
        if "--replay" in args:
            replay_index = args.index("--replay")
            if replay_index + 1 < len(args):
                replay = args[replay_index + 1]
        slow_mo = 0
        skill_args = [args[index + 1] for index, item in enumerate(args) if item == "--skill" and index + 1 < len(args)]
        executed_skill = skill_args[0] if skill_args else None
        gate_evidence = []
        if mode == "helper-only":
            executed_skill = "skill.discover-profile"
        elif mode in {"full-coverage", "full-coverage-side-effect-violation", "full-coverage-clean-side-effects"}:
            executed_skill = skill_args[0] if skill_args else "skill.validate-profile-view-unauth-flow"
            gate_evidence = [
                {"id": "profile-name", "source": "assertion", "gateId": "overview-data-card", "status": "passed", "target": "profileName"},
                {"id": "project-card", "source": "assertion", "gateId": "projects-tab-content", "status": "passed", "target": "projectCard"},
                {
                    "id": "profile-query",
                    "source": "network",
                    "gateId": "overview-profile-query",
                    "status": "passed",
                    "method": "POST",
                    "urlContains": "graphql",
                    "expectedStatus": 200,
                    "publicMatchKeys": ["urlContains"],
                },
            ]
        elif mode == "qa-report-step-coverage":
            executed_skill = skill_args[0] if skill_args else "skill.validate-profile-view-unauth-flow"
            _write_report(
                ".verifysignal/runs/login/fake-run-1/report.json",
                [
                    {"id": "assert-overview-data-card", "status": "passed", "gateId": "overview-data-card", "evidence": []},
                    {"id": "assert-projects-tab-content", "status": "passed", "gateId": "projects-tab-content", "evidence": []},
                    {"id": "assert-overview-profile-query", "status": "passed", "gateId": "overview-profile-query", "evidence": []},
                ],
            )
        elif mode in {"failed-with-partial", "aborted-activity-wait"}:
            gate_evidence = [{"id": "profile-name", "source": "assertion", "gateId": "overview-data-card", "status": "passed", "target": "profileName"}]
        side_effects: dict[str, object] | None = None
        runtime_outputs: list[dict[str, object]] = []
        result_classification: dict[str, object] | None = None
        if mode in {"post-commit-report", "runtime-output-report", "rerun-risk-report"}:
            side_effects = {
                "policy": {"class": "write", "mode": "enforce", "commitStepId": "submit-resource"},
                "commitStep": {"id": "submit-resource", "reached": True, "status": "passed"},
                "status": "likely-committed" if mode != "runtime-output-report" else "committed-confirmed",
            }
            runtime_outputs = [{"name": "createdResourceUrl", "source": "finalUrl", "status": "captured", "value": "/resources/fake"}]
            result_classification = {
                "executionStatus": "passed",
                "verificationStatus": "failed" if mode == "post-commit-report" else "passed",
                "sideEffectStatus": "unknown" if mode == "rerun-risk-report" else side_effects["status"],
                "failurePhase": "post-commit" if mode == "post-commit-report" else "post-verification",
                "rerunRisk": "blocked" if mode == "rerun-risk-report" else "requires-confirmation",
                "recommendedAction": "review-created-resource-before-rerun",
                "reasons": ["write-flow-safety-fixture"],
            }
            _write_report(
                ".verifysignal/runs/login/fake-run-1/report.json",
                gate_evidence,
                side_effects=side_effects,
                runtime_outputs=runtime_outputs,
                result_classification=result_classification,
            )
        elif mode == "full-coverage-side-effect-violation":
            side_effects = {
                "policy": {"class": "none", "mode": "observe", "allowed": [], "forbidden": []},
                "commitStep": {"reached": False},
                "status": "violated",
                "observations": [
                    {
                        "method": "POST",
                        "redactedUrl": "https://app.example.test/api/telemetry",
                        "timing": "unknown",
                        "responseStatus": 200,
                        "matchedAllowedRuleIds": [],
                        "matchedForbiddenRuleIds": [],
                        "status": "unexpected",
                    }
                ],
                "violations": [
                    {
                        "code": "side-effect-class-none-violation",
                        "severity": "warning",
                        "timing": "unknown",
                        "message": "A side effect was observed although the policy class is none.",
                        "remediation": "Review the request and update policy explicitly only when justified.",
                    }
                ],
            }
            result_classification = {
                "executionStatus": "passed",
                "verificationStatus": "passed",
                "sideEffectStatus": "violated",
                "failurePhase": "unknown",
                "rerunRisk": "blocked",
                "recommendedAction": "review-side-effect-violation-before-rerun",
                "reasons": ["side-effect-class-none-violation"],
            }
            _write_report(
                ".verifysignal/runs/login/fake-run-1/report.json",
                gate_evidence,
                side_effects=side_effects,
                runtime_outputs=runtime_outputs,
                result_classification=result_classification,
            )
        elif mode in {"full-coverage", "full-coverage-clean-side-effects"}:
            side_effects = {
                "policy": {"class": "none", "mode": "observe"},
                "commitStep": {"reached": False},
                "status": "not-observed",
                "observations": [],
                "violations": [],
            }
            result_classification = {
                "executionStatus": "passed",
                "verificationStatus": "passed",
                "sideEffectStatus": "not-observed",
                "failurePhase": "unknown",
                "rerunRisk": "safe",
                "recommendedAction": "none",
                "reasons": [],
            }
            _write_report(
                ".verifysignal/runs/login/fake-run-1/report.json",
                gate_evidence,
                side_effects=side_effects,
                runtime_outputs=runtime_outputs,
                result_classification=result_classification,
            )
        if "--slow-mo" in args:
            try:
                slow_mo = int(args[args.index("--slow-mo") + 1])
            except Exception:
                slow_mo = -1
        run_status = "failed" if mode in {"failed", "failed-with-partial", "aborted-activity-wait", "post-commit-report"} else "passed"
        print(
            json.dumps(
                {
                    "schema": "verifysignal.run/v1",
                    "schemaVersion": 1,
                    "operation": "run",
                    "status": run_status,
                    "data": {
                        "reportPath": ".verifysignal/runs/login/fake-run-1/report.json",
                        "evidencePath": ".verifysignal/runs/login/fake-run-1/evidence",
                        "summary": {
                            "runId": run_id,
                            "title": "Fake run",
                            "status": run_status,
                            "failedStepId": "scroll-to-activity" if mode == "aborted-activity-wait" else None,
                            "error": "Timeout waiting for .chakra-container .swiper-slide while activity skeletons were visible."
                            if mode == "aborted-activity-wait"
                            else None,
                        },
                        "args": args,
                        "headed": headed,
                        "slowMoMs": slow_mo,
                        "record": record,
                        "replay": replay,
                        "replayComparison": (
                            {"fixture": replay, "comparison": "matched", "tiers": {"identity": "matched", "structural": "matched", "semantic": "matched"}}
                            if replay
                            else None
                        ),
                        "executedSkill": executed_skill,
                        "gateEvidence": gate_evidence,
                        "sideEffects": side_effects,
                        "runtimeOutputs": runtime_outputs,
                        "resultClassification": result_classification,
                    },
                }
            )
        )
        return 0
    if args and args[0] == "crystallize":
        run_dir = args[1] if len(args) > 1 else ""
        out_dir = None
        if "--out" in args:
            out_index = args.index("--out")
            if out_index + 1 < len(args):
                out_dir = args[out_index + 1]
        manifest_dir = out_dir or ".verifysignal/fixtures/fake-run-1"
        print(
            json.dumps(
                {
                    "schema": "verifysignal.crystallize/v1",
                    "schemaVersion": 1,
                    "operation": "crystallize",
                    "status": "passed",
                    "data": {
                        "fixture": {
                            "manifestPath": f"{manifest_dir}/manifest.json",
                            "schema": "verifysignal-fixture/v1",
                            "schemaVersion": 1,
                            "sha256": "0" * 64,
                            "artifacts": [
                                {"name": "manifest.json", "sha256": "0" * 64},
                                {"name": "network.har", "sha256": "1" * 64},
                            ],
                        },
                        "flavor": "internal",
                        "source": {"runId": "fake-run-1", "status": "passed"},
                        "origin": {"runDir": run_dir},
                        "redactionSummary": {"redactedFields": 0, "policy": "public-redaction/v1"},
                        "determinism": {"status": "deterministic", "seed": "fake-seed"},
                        "golden": {
                            "comparison": "matched",
                            "tiers": {"identity": "matched", "structural": "matched", "semantic": "matched"},
                        },
                    },
                }
            )
        )
        return 0
    if args[:2] == ["report", "inspect"]:
        if mode == "report-main-skill":
            findings = [{
                "severity": "error",
                "artifact": ".verifysignal/run-requests/login.yaml",
                "path": "skills",
                "code": "main-skill-ordering",
                "message": "Helper skill executed before main skill.",
            }]
        elif mode == "aborted-activity-wait":
            findings = [{
                "severity": "error",
                "artifact": ".verifysignal/skills/validate-home-page-unauth-flow.browser.md",
                "path": "steps.scroll-to-activity",
                "code": "wait-timeout",
                "message": "Step scroll-to-activity timed out waiting for .chakra-container .swiper-slide while activity skeletons were visible.",
                "failedStepId": "scroll-to-activity",
                "gateId": "home-activity-slider",
            }]
        elif mode == "report-selector-and-side-effect":
            findings = [
                {
                    "severity": "error",
                    "artifact": ".verifysignal/skills/login.browser.md",
                    "path": "steps[1]",
                    "code": "browser-step-failed",
                    "message": "Strict mode violation: locator matched multiple elements.",
                },
                {
                    "severity": "warning",
                    "artifact": ".verifysignal/runs/login/fake-run-1/report.json",
                    "path": "sideEffects.violations[0]",
                    "code": "side-effect-class-none-violation",
                    "message": "A side effect was observed although the policy class is none.",
                },
            ]
        else:
            findings = [{
                "severity": "error",
                "artifact": ".verifysignal/skills/login.browser.md",
                "path": "steps[1]",
                "message": "Selector did not match.",
            }]
        print(
            json.dumps(
                {
                    "schema": "verifysignal.report-inspection/v1",
                    "schemaVersion": 1,
                    "operation": "report.inspect",
                    "status": "failed",
                    "data": {
                        "reportPath": args[2],
                        "summary": {"status": "failed", "failedStepId": "submit-login"},
                        "reproductionSteps": ["Navigate to /login", "Submit login"],
                        "observedFailure": "Dashboard did not appear.",
                        "expectedBehavior": "Dashboard appears.",
                        "findings": findings,
                    },
                }
            )
        )
        return 0
    if args and args[0] == "discover":
        url = args[args.index("--url") + 1] if "--url" in args and args.index("--url") + 1 < len(args) else None
        skill = args[args.index("--skill") + 1] if "--skill" in args and args.index("--skill") + 1 < len(args) else None
        print(
            json.dumps(
                {
                    "schema": "verifysignal.discover/v1",
                    "schemaVersion": 1,
                    "operation": "discover",
                    "status": "passed",
                    "data": {
                        "url": url,
                        "skill": skill,
                        "groundedTargets": [{"name": "hero", "css": "h1", "status": "grounded"}],
                        "verdicts": [{"target": "hero", "status": "grounded"}],
                    },
                }
            )
        )
        return 0
    print(json.dumps({"schema": "verifysignal.error/v1", "schemaVersion": 1, "operation": "unknown", "status": "error"}))
    return 1


def _protected_operation(args: list[str]) -> str | None:
    if args[:2] == ["authoring-check", "run-request"]:
        return "authoring-check"
    if args and args[0] == "run":
        return "run"
    if args and args[0] == "probe":
        return "probe"
    if args[:2] == ["report", "inspect"]:
        return "report.inspect"
    if args and args[0] == "crystallize":
        return "crystallize"
    return None


def _protected_fixture_response(mode: str, operation: str) -> tuple[dict[str, object], int]:
    if mode == "malformed-protected-response":
        return {
            "operation": operation,
            "status": "blocked",
            "error": "malformed-public-error",
        }, 2

    if mode == "operation-mismatched-response":
        mismatched_operation = "authoring-check" if operation == "run" else "run"
        return {
            "schema": _success_schema(operation),
            "schemaVersion": 1,
            "operation": mismatched_operation,
            "status": "passed",
            "data": {},
        }, 0

    payload: dict[str, object] = {
        "schema": "verifysignal.error/v1",
        "schemaVersion": 1,
        "operation": operation,
        "status": "error",
        "error": {
            "code": "entitlement.key-unknown",
            "message": "Protected operation rejected by the public fixture.",
        },
        # The deliberately different legacy code lets normalization tests prove
        # that the current top-level public code has precedence.
        "data": {
            "findings": [
                {
                    "severity": "blocking",
                    "code": "entitlement.expired",
                    "message": "Legacy public finding retained for compatibility.",
                }
            ]
        },
    }
    if mode == "current-entitlement-error":
        payload["execution"] = {
            "started": False,
            "phase": "pre-execution",
            "sideEffectMayExist": False,
        }
    return payload, 2


def _success_schema(operation: str) -> str:
    return {
        "authoring-check": "verifysignal.authoring-check/v1",
        "run": "verifysignal.run/v1",
    }[operation]


def _receipt_key_id(receipt_path: str | None) -> str | None:
    if not receipt_path:
        return None
    try:
        data = json.loads(open(receipt_path, encoding="utf-8").read())
    except Exception:
        return None
    if isinstance(data, dict) and isinstance(data.get("signature"), dict):
        return data["signature"].get("keyId")
    if isinstance(data, dict) and isinstance(data.get("receipt"), str):
        try:
            envelope = json.loads(data["receipt"])
        except Exception:
            return None
        signature = envelope.get("signature") if isinstance(envelope, dict) else {}
        return signature.get("keyId") if isinstance(signature, dict) else None
    return None


def _write_report(
    path: str,
    steps: list[dict[str, object]],
    *,
    side_effects: dict[str, object] | None = None,
    runtime_outputs: list[dict[str, object]] | None = None,
    result_classification: dict[str, object] | None = None,
) -> None:
    report_path = Path(path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "schemaVersion": "qa-report/v1",
        "runId": "fake-run-1",
        "status": "passed",
        "summary": {"status": "passed", "failedStepId": None},
        "failedStep": None,
        "steps": steps,
        "preconditions": [],
        "evidenceLinks": [],
    }
    if side_effects is not None:
        report["sideEffects"] = side_effects
    if runtime_outputs is not None:
        report["runtimeOutputs"] = runtime_outputs
    if result_classification is not None:
        report["resultClassification"] = result_classification
    report_path.write_text(
        json.dumps(report),
        encoding="utf-8",
    )


def _contracts_payload(mode: str) -> dict[str, object]:
    operations = [
        {"name": "version", "schema": "verifysignal.version/v1", "schemaVersion": 1, "status": "stable"},
        {"name": "contracts", "schema": "verifysignal.contracts/v1", "schemaVersion": 1, "status": "stable"},
        {"name": "authoring-check", "schema": "verifysignal.authoring-check/v1", "schemaVersion": 1, "status": "stable"},
        {"name": "run", "schema": "verifysignal.run/v1", "schemaVersion": 1, "status": "stable"},
        {"name": "report.inspect", "schema": "verifysignal.report-inspection/v1", "schemaVersion": 1, "status": "stable"},
        {"name": "crystallize", "schema": "verifysignal.crystallize/v1", "schemaVersion": 1, "status": "experimental"},
    ]
    browser_actions = [
        {"name": "navigate", "status": "stable", "requiredFields": ["value"]},
        {"name": "click", "status": "stable", "requiredFields": ["target"]},
        {"name": "fill", "status": "stable", "requiredFields": ["target", "value"]},
        {"name": "select", "status": "stable", "requiredFields": ["target", "value"]},
        {"name": "waitForText", "status": "stable", "requiredFields": ["target", "value"]},
        {"name": "checkText", "status": "stable", "requiredFields": ["target", "value"]},
        {"name": "checkLocation", "status": "stable", "requiredFields": ["value"]},
        {"name": "captureScreenshot", "status": "stable", "requiredFields": []},
        {"name": "scrollIntoView", "status": "stable", "requiredFields": ["target"]},
        {"name": "awaitNetwork", "status": "stable", "requiredFields": ["match"]},
        {"name": "repeatUntil", "status": "stable", "requiredFields": ["until", "do"]},
    ]
    if mode == "contract-drift":
        browser_actions = [item for item in browser_actions if item["name"] != "repeatUntil"]
        browser_actions.append({"name": "press", "status": "stable", "requiredFields": ["target", "value"]})
    if mode == "experimental-contract":
        browser_actions.append({"name": "dragAndDrop", "status": "experimental", "requiredFields": ["target", "value"]})
    data: dict[str, object] = {
        "operations": operations,
        "runRequest": {
            "status": "stable",
            "schemaVersion": "qa-run-request/v1",
            "fields": [
                {"name": "schemaVersion", "status": "stable", "required": True},
                {"name": "request", "status": "stable", "required": True},
                {"name": "target", "status": "stable", "required": True},
                {"name": "credentialRefs", "status": "stable", "required": False},
                {"name": "skills", "status": "stable", "required": True},
            ],
        },
        "skill": {
            "status": "stable",
            "schemaVersion": "verifysignal-browser-skill/v1",
            "fields": [
                {"name": "browser.targets", "status": "stable", "required": True},
                {"name": "browser.steps", "status": "stable", "required": True},
                {"name": "browser.assertions", "status": "stable", "required": False},
            ],
        },
        "browserWorkflow": {
            "actions": browser_actions,
            "assertions": [
                {"name": "text", "status": "stable", "requiredFields": ["target", "expected"]},
                {"name": "location", "status": "stable", "requiredFields": ["expected"]},
                {"name": "visible", "status": "stable", "requiredFields": ["target"]},
                {"name": "hidden", "status": "stable", "requiredFields": ["target"]},
                {"name": "screenshot-required", "status": "stable", "requiredFields": []},
                {"name": "image-diff", "status": "experimental", "requiredFields": ["target"]},
            ],
            "targetSignals": [
                {"name": "testId", "status": "stable"},
                {"name": "label", "status": "stable"},
                {"name": "text", "status": "stable"},
                {"name": "css", "status": "stable"},
                {"name": "semanticLocator", "status": "stable"},
                {"name": "all", "status": "stable", "composition": ["testId", "css"]},
            ],
            "networkMatchKeys": [
                {"name": "urlContains", "status": "stable"},
                {"name": "method", "status": "stable"},
                {"name": "status", "status": "stable"},
                {"name": "requestBodyContains", "status": "stable"},
                {"name": "responseBodyContains", "status": "stable"},
                {"name": "privateHeaderContains", "status": "experimental"},
            ],
            "metadataKeys": [{"name": "operationName", "status": "stable"}, {"name": "expectedStatus", "status": "stable"}],
            "warnings": _browser_authoring_warnings(),
            "gateEvidenceRules": {
                "gateId": "UI assertions, network waits, and screenshots must declare gateId to count toward planned gate coverage.",
                "renderedResult": "Required page-view gates need a specific target plus expected text/state/count.",
                "network": "awaitNetwork match uses stable public match keys and expected status.",
            },
        },
        "credentials": {
            "sources": [{"name": "environment", "status": "stable"}, {"name": "prompt-cache", "status": "experimental"}],
            "referenceShape": "credentialRefs.<group>.keys.<field>",
        },
        "placeholders": {
            "credentialSyntax": "{{credentials.<group>.<field>}}",
            "supportedNamespaces": [{"name": "parameters", "status": "stable"}, {"name": "credentials", "status": "stable"}],
        },
        "reportCoverage": {
            "schemaVersion": "qa-report/v1",
            "gateIdFields": ["gateId"],
            "stepCollections": ["steps", "preconditions"],
            "evidenceCollections": ["evidence"],
            "statusField": "status",
            "passedStatus": "passed",
        },
        "publicRedactionPolicy": {
            "publicErrorShape": {
                "forbiddenFields": ["rawValue", "rawRequestBody", "rawResponseBody", "receipt", "receiptPayload", "privateKey", "signedUrl", "absolutePath", "rawPayload"],
            },
            "safeEvidenceReferences": {
                "forbiddenFields": ["rawPayload", "absolutePath", "signedUrl", "storageState", "sessionCookies", "tracePayload", "screenshotPayload"],
            },
        },
        "runtimeTrustHandoff": {
            "entitlementReceiptEnv": "VERIFYSIGNAL_ENTITLEMENT_RECEIPT",
            "verificationKeysEnv": "VERIFYSIGNAL_ENTITLEMENT_PUBLIC_KEYS_JSON",
        },
        "sideEffectGuardrails": _side_effect_guardrails_section(),
        "crystallizationPolicy": {
            "status": "experimental",
            "operation": "crystallize",
            "schema": "verifysignal.crystallize/v1",
            "schemaVersion": 1,
            "flavors": ["internal", "shareable"],
            "fixtureSchema": {"name": "verifysignal-fixture/v1", "schemaVersion": 1},
            "goldenTiers": ["identity", "structural", "semantic"],
            "runFlags": [
                {"name": "--record", "status": "experimental"},
                {"name": "--replay", "status": "experimental", "requiredFields": ["fixture"]},
            ],
            "replaySource": {"status": "experimental", "referenceShape": "replaySource.fixture"},
        },
    }
    if mode == "multi-skill-supported":
        data["skillExecution"] = {
            "status": "stable",
            "roles": [
                {"name": "main", "status": "stable"},
                {"name": "precondition", "status": "stable"},
            ],
            "ordering": "declared-list-order",
            "evidenceSemantics": "gateId-attributed-per-participant",
        }
    if mode == "partial-skill-support":
        data["skillExecution"] = {
            "status": "partial",
            "roles": [
                {"name": "precondition", "status": "stable"},
            ],
            "ordering": "preconditions-before-main",
            "evidenceSemantics": "preconditions-do-not-satisfy-required-gates",
        }
    if mode == "contracts-missing-browser":
        data.pop("browserWorkflow")
    if mode == "contracts-malformed-browser":
        data["browserWorkflow"] = []
    if mode in {"current-contract", "canonical-legacy-conflict", "missing-canonical-metadata"}:
        data["runRequest"] = {
            "status": "supported",
            "schemaVersion": 1,
            "fields": [
                {"path": "schemaVersion", "status": "supported", "required": True, "allowedValues": ["qa-run-request/v1"]},
                {"path": "request.id", "status": "supported", "required": True},
                {"path": "request.name", "status": "supported", "required": True},
                {"path": "target.url", "status": "supported", "required": True},
                {"path": "credentialRefs", "status": "supported", "required": False},
                {"path": "skills.main", "status": "supported", "required": True},
            ],
        }
        data["skill"] = {
            "status": "supported",
            "schemaVersion": 1,
            "fields": [
                {"path": "schemaVersion", "status": "supported", "required": True, "allowedValues": ["qa-skill/v1"]},
                {"path": "skill.id", "status": "supported", "required": True},
                {"path": "browser.targets", "status": "supported", "required": True},
                {"path": "browser.steps", "status": "supported", "required": True},
                {"path": "browser.assertions", "status": "supported", "required": False},
            ],
        }
        current_actions = [
            {"name": "navigate", "status": "supported", "requiredFields": ["value"]},
            {"name": "click", "status": "supported", "requiredFields": ["target"]},
            {"name": "fill", "status": "supported", "requiredFields": ["target", "value"]},
            {
                "name": "awaitNetwork",
                "status": "supported",
                "requiredFields": ["match"],
                "match": {
                    "keys": [
                        {"name": "urlContains", "status": "supported"},
                        {"name": "method", "status": "supported"},
                        {"name": "status", "status": "supported"},
                        {"name": "requestBodyContains", "status": "supported"},
                        {"name": "responseBodyContains", "status": "supported"},
                    ]
                },
            },
        ]
        if mode == "missing-canonical-metadata":
            current_actions = [
                {"name": "navigate", "status": "supported", "requiredFields": ["value"]},
                {"name": "awaitNetwork", "status": "supported", "requiredFields": ["match"]},
            ]
        data["browserWorkflow"] = {
            "actions": current_actions,
            "assertions": [
                {"name": "text", "status": "supported", "requiredFields": ["target", "expected"]},
                {"name": "visible", "status": "supported", "requiredFields": ["target"]},
            ],
            "targetSignals": ["testId", "label", "text", "css", "semanticLocator"],
            "targets": {"composition": {"supportedSignals": ["testId", "css"]}},
            "metadataKeys": [{"name": "operationName", "status": "supported"}, {"name": "expectedStatus", "status": "supported"}],
            "warnings": _browser_authoring_warnings(),
            "gateEvidenceRules": {
                "gateId": "UI assertions, network waits, and screenshots must declare gateId to count toward planned gate coverage.",
                "renderedResult": "Required page-view gates need a specific target plus expected text/state/count.",
                "network": "awaitNetwork match uses stable public match keys and expected status.",
            },
        }
        data["credentials"] = {
            "credentialRefs": {
                "supportedSources": [{"name": "environment", "status": "supported"}, {"name": "prompt-cache", "status": "experimental"}],
                "referenceShape": "credentialRefs.<group>.keys.<field>",
                "placeholderSyntax": "{{credentials.<group>.<field>}}",
            }
        }
        data["sideEffectGuardrails"] = _side_effect_guardrails_section()
    if mode == "contracts-missing-side-effect-guardrails":
        data.pop("sideEffectGuardrails", None)
    if mode == "legacy-fallback":
        pass
    if mode == "canonical-legacy-conflict":
        browser = data["browserWorkflow"]
        if isinstance(browser, dict):
            browser["networkMatchKeys"] = [{"name": "legacyOnly", "status": "stable"}]
            browser["targetSignals"] = [
                {"name": "testId", "status": "stable"},
                {"name": "all", "status": "stable", "composition": ["aria"]},
            ]
        credentials = data["credentials"]
        if isinstance(credentials, dict):
            credentials["sources"] = [{"name": "vault", "status": "stable"}]
    return {
        "schema": "verifysignal.contracts/v1",
        "schemaVersion": 1,
        "operation": "contracts",
        "status": "passed",
        "data": {"sections": data},
    }


def _browser_authoring_warnings() -> list[dict[str, object]]:
    return [
        {
            "code": "degenerate-text-target",
            "severity": "warning",
            "runtimeReadinessSeverity": "blocking",
            "message": "A text assertion must not search for the same text inside a text-only target.",
            "remediation": "Use a stable parent target and keep expected text in the step or assertion.",
            "appliesTo": ["waitForText", "checkText", "assertions.text"],
        },
        {
            "code": "unstable-generated-css-target",
            "severity": "warning",
            "runtimeReadinessSeverity": "blocking",
            "message": "Generated or positional CSS targets are unstable.",
            "remediation": "Use a stable semantic locator.",
            "appliesTo": ["targets"],
        },
    ]


def _side_effect_guardrails_section() -> dict[str, object]:
    statuses = [
        "not-applicable",
        "not-started",
        "not-observed",
        "possible",
        "likely-committed",
        "committed-confirmed",
        "violated",
        "unknown",
    ]
    phases = ["pre-commit", "during-commit", "post-commit", "post-verification", "unknown"]
    risks = ["safe", "safe-with-new-inputs", "requires-confirmation", "blocked"]
    return {
        "status": "supported",
        "policyClasses": ["none", "authenticated-read", "write", "external-notification", "unknown"],
        "policyModes": ["observe", "warn", "enforce"],
        "confirmationSignalTypes": ["finalUrl", "runtimeOutput", "allowedNetworkObservation"],
        "confirmationSignals": {
            "supportedTypes": ["finalUrl", "runtimeOutput", "allowedNetworkObservation"],
            "unsupportedTypes": ["dom"],
            "unsupportedSignalError": "unsupported-confirmation-signal",
        },
        "runtimeOutputSources": ["finalUrl", "location", "dom", "network"],
        "runtimeOutputStatuses": ["captured", "redacted", "missing", "invalid"],
        "sideEffectStatuses": statuses,
        "failurePhases": phases,
        "rerunRisks": risks,
        "resultClassification": {
            "executionStatuses": ["passed", "failed", "blocked", "error"],
            "verificationStatuses": ["passed", "failed", "not-run", "unknown"],
            "sideEffectStatuses": statuses,
            "failurePhases": phases,
            "rerunRisks": risks,
        },
        "reportFields": ["sideEffects.policy", "sideEffects.observations[]", "sideEffects.violations[]", "runtimeOutputs[]", "resultClassification"],
    }


def _increment_contract_counter() -> None:
    path = os.environ.get("FAKE_VERIFYSIGNAL_CONTRACT_COUNTER")
    if not path:
        return
    counter_path = Path(path)
    counter_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        value = int(counter_path.read_text(encoding="utf-8").strip() or "0")
    except Exception:
        value = 0
    counter_path.write_text(str(value + 1), encoding="utf-8")


def _public_keys_include(key_id: str) -> bool:
    raw = os.environ.get("VERIFYSIGNAL_ENTITLEMENT_PUBLIC_KEYS_JSON")
    if not raw:
        return False
    try:
        data = json.loads(raw)
    except Exception:
        return False
    keys = data.get("keys") if isinstance(data, dict) else data
    if not isinstance(keys, list):
        return False
    return any(isinstance(item, dict) and item.get("keyId") == key_id for item in keys)


if __name__ == "__main__":
    raise SystemExit(main())
