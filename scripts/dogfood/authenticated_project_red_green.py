#!/usr/bin/env python3
"""Cross-repository red/green dogfood for an authenticated write workflow.

The target is intentionally identity-neutral. It reproduces the structural
shape of the reported failure while exercising only public Spec and Core
interfaces:

* split email/password authentication;
* protected-route redirection;
* a required title and asynchronous linked-media lookup;
* a publish boundary with a traceable generated resource;
* zero commits during probe and exactly one commit during normal run.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import yaml

SPEC_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(SPEC_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(SPEC_REPO_ROOT))
if str(SPEC_REPO_ROOT / "tests") not in sys.path:
    sys.path.insert(0, str(SPEC_REPO_ROOT / "tests"))

from tests.fixtures.managed_runtime import (  # noqa: E402
    build_managed_runtime_distribution_from_artifact,
    serve_fake_entitlement_backend,
)
from verifysignal_spec.runtime.distribution import normalize_platform  # noqa: E402


SCHEMA = "verifysignal.cross-repo-dogfood/v1"
SCENARIO = "authenticated-project-creation"
ALIAS = "authenticated-project-creation-dogfood"
CLI_BOOTSTRAP = (
    "import sys; "
    "from verifysignal_spec.cli import main; "
    "sys.exit(main())"
)


class DogfoodFailure(RuntimeError):
    def __init__(self, code: str, message: str | None = None) -> None:
        super().__init__(message or code)
        self.code = code


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the identity-neutral authenticated-project structural dogfood."
    )
    parser.add_argument(
        "--core-repo",
        required=True,
        help="Path to the sibling VerifySignal Core source repository.",
    )
    parser.add_argument(
        "--entitlement-ready",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    spec_repo = Path(__file__).resolve().parents[2]
    core_repo = Path(args.core_repo).expanduser().resolve()
    ensure_source_layout(core_repo)

    if not args.entitlement_ready:
        build_core(core_repo)
        helper = core_repo / "scripts/examples/with-example-entitlement.mjs"
        child = subprocess.run(
            [
                "node",
                str(helper),
                sys.executable,
                str(Path(__file__).resolve()),
                "--core-repo",
                str(core_repo),
                "--entitlement-ready",
            ],
            cwd=spec_repo,
            check=False,
        )
        return child.returncode

    return execute(spec_repo, core_repo)


def execute(spec_repo: Path, core_repo: Path) -> int:
    summary: dict[str, Any] = {
        "schema": SCHEMA,
        "scenario": SCENARIO,
        "status": "red",
        "specRevision": revision(spec_repo),
        "coreRevision": revision(core_repo),
        "gates": {},
        "state": {},
    }
    server: subprocess.Popen[str] | None = None
    resources = contextlib.ExitStack()

    with tempfile.TemporaryDirectory(
        prefix="verifysignal-authenticated-project-spec-dogfood-"
    ) as temporary:
        temporary_root = Path(temporary)
        workspace = temporary_root / "workspace"
        payload_root = temporary_root / "payloads"
        workspace.mkdir(parents=True)
        payload_root.mkdir(parents=True)
        subprocess.run(
            ["git", "init", "-q", str(workspace)],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        port = available_port()
        base_url = f"http://127.0.0.1:{port}"
        runtime_env = dict(os.environ)
        runtime_env.pop("VS_DOGFOOD_EMAIL", None)
        runtime_env.pop("VS_DOGFOOD_PASSWORD", None)
        platform = normalize_platform()
        require(bool(platform), "managed-platform-unsupported")
        core_version = str(
            json.loads((core_repo / "package.json").read_text(encoding="utf-8"))[
                "version"
            ]
        )
        packaged_core = (
            core_repo
            / "dist/runtime"
            / f"verifysignal-core-{core_version}-{platform}.tar.gz"
        )
        require(packaged_core.exists(), "managed-package-missing")
        distribution = build_managed_runtime_distribution_from_artifact(
            temporary_root / "managed-distribution",
            artifact_source=packaged_core,
            platform=str(platform),
            core_version=core_version,
        )
        api_base_url, _backend_state = resources.enter_context(
            serve_fake_entitlement_backend(distribution)
        )
        runtime_env.update(
            {
                "VERIFYSIGNAL_API_BASE_URL": api_base_url,
                "VERIFYSIGNAL_EMAIL_UNLOCK_TOKEN": "vs_valid",
                "VERIFYSIGNAL_RUNTIME_CACHE_DIR": str(
                    temporary_root / "managed-cache"
                ),
                "VERIFYSIGNAL_ALLOW_TEST_RELEASE_KEYS": "1",
            }
        )
        server_env = {
            **runtime_env,
            "VS_DOGFOOD_EMAIL": "tester@example.test",
            "VS_DOGFOOD_PASSWORD": "reference-password",
        }

        try:
            server = start_target(core_repo, port, server_env)
            wait_for_http(f"{base_url}/", server)

            source_request = (
                core_repo
                / "examples/run-requests/authenticated-project-creation-dogfood.yaml"
            )
            source_skill = (
                core_repo
                / "examples/skills/authenticated-project-creation-dogfood.browser.md"
            )
            request_document = yaml.safe_load(source_request.read_text(encoding="utf-8"))
            request_document["parameters"]["baseUrl"] = base_url
            request_content = yaml.safe_dump(request_document, sort_keys=False)
            skill_content = source_skill.read_text(encoding="utf-8")
            temporary_request = temporary_root / "request.yaml"
            temporary_request.write_text(request_content, encoding="utf-8")

            discover = require_success(
                spec_cli(
                    [
                        "discover",
                        "--url",
                        f"{base_url}/projects/new?mode=individual",
                        "--skill",
                        str(source_skill),
                        "--project",
                        str(workspace),
                        "--core-cmd",
                        str(core_repo),
                        "--json",
                    ],
                    cwd=spec_repo,
                    env=runtime_env,
                ),
                "discover-command",
            )
            discover_data = discover.get("data", discover)
            require(discover_data.get("route") == "/sign-in/email", "discover-route")
            require(
                discover_data.get("overall") == "needs-correction",
                "discover-limitation",
            )
            require(
                target_status(discover_data.get("targets"), "emailInput")
                == "resolved-unique",
                "discover-email-target",
            )
            require(
                target_status(discover_data.get("targets"), "projectTitle")
                == "not-found",
                "discover-protected-target",
            )
            assert_state(
                target_state(base_url),
                emailChecks=0,
                signIns=0,
                mediaLookups=0,
                commits=0,
                resources=0,
            )
            summary["gates"]["discoverControl"] = "passed"

            persist_canonical_workflow(
                spec_repo=spec_repo,
                core_repo=core_repo,
                workspace=workspace,
                payload_root=payload_root,
                base_url=base_url,
                request_content=request_content,
                skill_content=skill_content,
                env=runtime_env,
            )
            summary["gates"]["canonicalPersistence"] = "passed"

            updated = require_success(
                spec_cli(
                    [
                        "core",
                        "update",
                        "--project",
                        str(workspace),
                        "--api-base-url",
                        api_base_url,
                        "--json",
                    ],
                    cwd=spec_repo,
                    env={
                        key: value
                        for key, value in runtime_env.items()
                        if key
                        not in {
                            "VERIFYSIGNAL_ENTITLEMENT_RECEIPT",
                            "VERIFYSIGNAL_ENTITLEMENT_RECEIPT_PATH",
                            "VERIFYSIGNAL_ENTITLEMENT_PUBLIC_KEYS_JSON",
                        }
                    },
                ),
                "managed-core-update",
            )
            require(updated.get("status") == "ready", "managed-update-status")
            update_runtime = updated.get("runtime", {})
            require(
                update_runtime.get("source") in {"managed-download", "managed-cache"},
                "managed-update-source",
            )
            require(
                all(
                    item.get("source")
                    not in {"workspace", "env", "path", "ancestor-sibling"}
                    for item in update_runtime.get("attempts", [])
                    if isinstance(item, dict)
                ),
                "managed-update-local-contamination",
            )
            summary["gates"]["managedCoreUpdate"] = "passed"
            summary["observations"] = {
                "managedCoreUpdate": {
                    "source": update_runtime.get("source"),
                    "version": update_runtime.get("runtimeVersion"),
                }
            }

            env_file = workspace / ".env.verifysignal.test.local"
            prepared = require_success(
                spec_cli(
                    [
                        "credentials",
                        "prepare",
                        ALIAS,
                        "--project",
                        str(workspace),
                        "--env-file",
                        str(env_file),
                        "--json",
                    ],
                    cwd=spec_repo,
                    env=runtime_env,
                ),
                "credential-preparation",
            )
            require(prepared.get("gitExcluded") is True, "credential-git-exclude")
            require(prepared.get("permissions") == "0600", "credential-permissions")
            fill_test_environment_file(env_file)
            summary["gates"]["credentialPreparation"] = "passed"

            probe = require_success(
                spec_cli(
                    [
                        "probe",
                        str(workspace / f".verifysignal/run-requests/{ALIAS}.yaml"),
                        "--skill",
                        str(workspace / f".verifysignal/skills/{ALIAS}.browser.md"),
                        "--project",
                        str(workspace),
                        "--core-cmd",
                        str(core_repo),
                        "--env-file",
                        str(env_file),
                        "--json",
                    ],
                    cwd=spec_repo,
                    env=runtime_env,
                ),
                "probe-command",
            )
            require(probe.get("status") == "passed", "probe-status")
            boundary = probe.get("data", {}).get("boundary", probe.get("boundary", {}))
            require(boundary.get("reached") is True, "probe-boundary-reached")
            require(boundary.get("executed") is False, "probe-boundary-not-executed")
            after_probe = target_state(base_url)
            assert_state(
                after_probe,
                emailChecks=1,
                signIns=1,
                mediaLookups=1,
                commits=0,
                resources=0,
            )
            summary["gates"]["probe"] = "passed"
            summary["state"]["afterProbe"] = safe_state(after_probe)

            validation = require_success(
                spec_cli(
                    [
                        "validate",
                        ALIAS,
                        "--runtime-readiness",
                        "--project",
                        str(workspace),
                        "--core-cmd",
                        str(core_repo),
                        "--env-file",
                        str(env_file),
                        "--json",
                    ],
                    cwd=spec_repo,
                    env=runtime_env,
                ),
                "validate-command",
            )
            require(validation.get("status") == "passed", "validate-status")
            summary["gates"]["validate"] = "passed"

            readiness = require_success(
                spec_cli(
                    [
                        "workflow",
                        "check",
                        "run",
                        "--alias",
                        ALIAS,
                        "--project",
                        str(workspace),
                        "--json",
                    ],
                    cwd=spec_repo,
                    env=runtime_env,
                ),
                "run-readiness-command",
            )
            summary["observations"]["runReadiness"] = {
                    "status": readiness.get("status"),
                    "canProceed": bool(readiness.get("canProceed", False)),
                    "requiresConfirmation": bool(
                        readiness.get("requiresConfirmation", False)
                    ),
                    "confirmationScope": (
                        readiness.get("confirmation", {}).get("scope")
                        if isinstance(readiness.get("confirmation"), dict)
                        else None
                    ),
                    "blockerCodes": [
                        str(item.get("code"))
                        for item in readiness.get("blockers", [])
                        if isinstance(item, dict) and item.get("code")
                    ],
            }
            require(readiness.get("status") == "ready", "run-readiness-status")
            require(
                readiness.get("canProceed") is True,
                "run-readiness-cannot-proceed",
            )
            run_args = [
                "run",
                ALIAS,
                "--project",
                str(workspace),
                "--profile",
                "normal",
                "--core-cmd",
                str(core_repo),
                "--env-file",
                str(env_file),
                "--non-interactive",
                "--json",
            ]
            authorization_mode = "isolated-local-invocation"
            if readiness.get("requiresConfirmation") is True:
                confirmation = readiness.get("confirmation")
                require(
                    isinstance(confirmation, dict),
                    "write-confirmation-missing",
                )
                confirmation_id = str(confirmation.get("id") or "")
                require(bool(confirmation_id), "write-confirmation-id-missing")
                run_args.extend(["--confirm-risk", confirmation_id])
                authorization_mode = "confirm-risk"
            summary["observations"]["runAuthorization"] = {
                "mode": authorization_mode
            }

            after_readiness = target_state(base_url)
            assert_state(
                after_readiness,
                emailChecks=1,
                signIns=1,
                mediaLookups=1,
                commits=0,
                resources=0,
            )
            summary["gates"]["runReadiness"] = "passed"
            summary["state"]["afterRunReadiness"] = safe_state(after_readiness)

            run = require_success(
                spec_cli(
                    run_args,
                    cwd=spec_repo,
                    env=runtime_env,
                ),
                "authorized-run-command",
            )
            require(run.get("status") == "passed", "run-status")
            require(
                run.get("postCommitInterpretation", {}).get("sideEffectStatus")
                == "committed-confirmed",
                "run-commit-confirmation",
            )
            after_run = target_state(base_url)
            assert_state(
                after_run,
                emailChecks=2,
                signIns=2,
                mediaLookups=2,
                commits=1,
                resources=1,
            )
            title = str(after_run.get("resources", [{}])[0].get("title") or "")
            require("Reference project" in title, "run-resource-identity")
            summary["gates"]["run"] = "passed"
            summary["state"]["afterRun"] = safe_state(after_run)
            summary["status"] = "green"
        except DogfoodFailure as error:
            summary["blocker"] = {"code": error.code, "message": str(error)}
        except Exception as error:  # pragma: no cover - defensive summary boundary
            summary["blocker"] = {
                "code": "dogfood-execution-error",
                "message": str(error),
            }
        finally:
            if server is not None:
                stop_target(server)
            resources.close()

    print(json.dumps(summary, indent=2))
    return 0 if summary["status"] == "green" else 1


def persist_canonical_workflow(
    *,
    spec_repo: Path,
    core_repo: Path,
    workspace: Path,
    payload_root: Path,
    base_url: str,
    request_content: str,
    skill_content: str,
    env: dict[str, str],
) -> None:
    require_success(
        spec_cli(
            [
                "init",
                str(workspace),
                "--integration",
                "codex",
                "--core-cmd",
                str(core_repo),
                "--json",
            ],
            cwd=spec_repo,
            env=env,
        ),
        "init-command",
    )
    require_success(
        spec_cli(
            [
                "workflow",
                "run",
                "verifysignal-use-case",
                "--goal",
                "Validate the identity-neutral authenticated project creation flow.",
                "--alias",
                ALIAS,
                "--integration",
                "codex",
                "--project",
                str(workspace),
                "--json",
            ],
            cwd=spec_repo,
            env=env,
        ),
        "workflow-run-command",
    )

    runtime_inputs = [
        {
            "name": "baseUrl",
            "source": "default",
            "value": base_url,
            "persistValue": True,
        },
        {
            "name": "projectTitle",
            "source": "generated",
            "value": "Reference project",
            "template": "Reference project {{run.shortId}}",
            "refreshOnRerunAfterCommit": True,
            "persistValue": False,
        },
        {
            "name": "mediaUrl",
            "source": "default",
            "value": "https://media.example.test/reference",
            "persistValue": True,
        },
    ]
    stages: list[tuple[str, dict[str, Any]]] = [
        (
            "understand",
            {
                "repositorySummary": (
                    "Identity-neutral local reference application with split "
                    "authentication and an authenticated project publish flow."
                ),
                "localStartInstructions": (
                    "node "
                    f"{core_repo / 'examples/targets/authenticated-project-creation-dogfood-app/server.mjs'}"
                ),
                "git": {
                    "available": True,
                    "hash": revision(core_repo),
                },
                "safeInspectionPaths": [
                    "examples/targets/authenticated-project-creation-dogfood-app/",
                    "examples/run-requests/authenticated-project-creation-dogfood.yaml",
                    "examples/skills/authenticated-project-creation-dogfood.browser.md",
                ],
                "blockedSensitivePaths": [".env", ".env.*", "*secret*"],
                "validationGoals": [
                    "Prove protected-page grounding through the authenticated state.",
                    "Prove probe creates zero resources and normal run creates exactly one.",
                ],
                "knownRuntimeRequirements": [
                    {"name": "baseUrl", "value": base_url},
                    {
                        "name": "qa",
                        "description": "Runtime-only environment credential references.",
                    },
                ],
                "coverageInventory": {
                    "status": "complete",
                    "sourceFilesVisited": 3,
                    "items": [
                        {
                            "id": "flow-authenticated-project-create",
                            "surfaceType": "flow",
                            "path": "/projects/new?mode=individual",
                            "title": "Authenticated project creation",
                            "sourceRefs": [
                                "examples/targets/authenticated-project-creation-dogfood-app/server.mjs",
                                "examples/skills/authenticated-project-creation-dogfood.browser.md",
                            ],
                            "priority": "high",
                        }
                    ],
                    "candidateUseCases": [
                        {
                            "alias": ALIAS,
                            "surface": "/projects/new?mode=individual",
                            "behavior": (
                                "Authenticate, resolve linked media, and publish "
                                "one individual project."
                            ),
                            "rationale": (
                                "Structural dogfood for protected-page grounding "
                                "and a controlled write boundary."
                            ),
                            "confidence": "high",
                            "priority": "high",
                            "sourceInventoryItems": [
                                "flow-authenticated-project-create"
                            ],
                            "knownRuntimeRequirements": [
                                "credential:qa",
                                "write operation",
                            ],
                        }
                    ],
                },
            },
        ),
        (
            "specify",
            {
                "alias": ALIAS,
                "surface": "/projects/new?mode=individual",
                "behavior": (
                    "Authenticate through split email and password routes, resolve "
                    "linked media, and publish one individual project."
                ),
                "expectedOutcome": (
                    "Probe reaches but does not execute publish; confirmed normal "
                    "run creates one traceable local project."
                ),
                "customSourceReason": "Identity-neutral cross-repository structural dogfood.",
            },
        ),
        (
            "clarify",
            {
                "alias": ALIAS,
                "answers": [
                    {
                        "questionId": "browser-target-environment",
                        "answerSummary": base_url,
                        "confirmationSource": "explicit-command",
                    }
                ],
                "blockingQuestionsResolved": True,
            },
        ),
        (
            "plan",
            {
                "alias": ALIAS,
                "runRequest": f".verifysignal/run-requests/{ALIAS}.yaml",
                "reusableSkills": [
                    f".verifysignal/skills/{ALIAS}.browser.md"
                ],
                "runtimeInputs": runtime_inputs,
                "validationGates": [
                    {
                        "id": "created-project-title",
                        "description": (
                            "The created project page renders the generated title."
                        ),
                        "required": True,
                    }
                ],
                "unresolvedBlockingClarifications": [],
            },
        ),
        (
            "tasks",
            {
                "alias": ALIAS,
                "tasks": [
                    {
                        "id": "T001",
                        "description": "Persist the structural browser artifacts.",
                        "artifact": "run-request",
                    },
                    {
                        "id": "T002",
                        "description": "Probe before publish and run after confirmation.",
                        "artifact": "runtime-validation",
                    },
                ],
                "dependencies": [{"task": "T002", "dependsOn": ["T001"]}],
                "parallelizableGroups": [],
            },
        ),
        (
            "implement",
            {
                "alias": ALIAS,
                "runRequest": {
                    "path": f".verifysignal/run-requests/{ALIAS}.yaml",
                    "content": request_content,
                },
                "skills": [
                    {
                        "path": f".verifysignal/skills/{ALIAS}.browser.md",
                        "content": skill_content,
                    }
                ],
                "runtimeInputs": runtime_inputs,
                "sideEffects": {
                    "class": "write",
                    "mode": "enforce",
                    "commitStepId": "publish",
                    "allowed": [
                        {
                            "id": "allow-email-check",
                            "kind": "authentication",
                            "methods": ["POST"],
                            "urlContains": "/sign-in/email",
                            "timing": "before-commit",
                        },
                        {
                            "id": "allow-password-sign-in",
                            "kind": "authentication",
                            "methods": ["POST"],
                            "urlContains": "/sign-in/password",
                            "timing": "before-commit",
                        },
                        {
                            "id": "allow-media-lookup",
                            "kind": "metadata-lookup",
                            "methods": ["POST"],
                            "urlContains": "/api/media/resolve",
                            "timing": "before-commit",
                        },
                        {
                            "id": "allow-project-create",
                            "kind": "project-create",
                            "methods": ["POST"],
                            "urlContains": "/api/projects",
                            "timing": "at-commit",
                        },
                    ],
                    "forbidden": [],
                    "confirmationSignals": [
                        {
                            "id": "created-route",
                            "type": "finalUrl",
                            "pathEquals": "/projects/reference-project-1",
                            "required": True,
                        },
                        {
                            "id": "created-title",
                            "type": "runtimeOutput",
                            "reference": "createdTitle",
                            "expectedContains": "{{parameters.projectTitle}}",
                            "required": True,
                        },
                    ],
                },
                "resourceIdentity": {
                    "resourceType": "project",
                    "identityStrategy": "generated-input",
                    "identityInput": "projectTitle",
                    "collisionPolicy": "avoid",
                    "targetScope": base_url,
                    "confidence": "high",
                },
                "runtimeOutputs": [
                    {
                        "name": "createdTitle",
                        "source": "dom",
                        "target": "createdTitle",
                        "extract": "textContent",
                    }
                ],
                "sideEffectLifecycle": {
                    "cleanupPolicy": "automated",
                    "cleanupRequired": False,
                    "trackingIntent": "ephemeral-target-reset",
                    "instructions": (
                        "Stopping the isolated target process removes all local "
                        "fixture resources."
                    ),
                },
                "rerunPolicy": {
                    "afterNoCommit": "allowed",
                    "afterCommit": "blocked",
                },
                "writeFlowSummary": {
                    "commitBoundary": "publish",
                    "resourceType": "project",
                    "target": "isolated-local-reference-app",
                },
                "recordUpdates": {},
            },
        ),
    ]

    for stage, content in stages:
        payload_path = payload_root / f"{stage}.json"
        payload_path.write_text(
            json.dumps(
                {
                    "stage": stage,
                    "alias": ALIAS,
                    "requestedAt": "2026-07-26T00:00:00Z",
                    "payload": content,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        require_success(
            spec_cli(
                [
                    "workflow",
                    "persist",
                    stage,
                    *(
                        ["--scope", "all"]
                        if stage == "understand"
                        else ["--alias", ALIAS]
                    ),
                    "--project",
                    str(workspace),
                    "--payload",
                    str(payload_path),
                    "--json",
                ],
                cwd=spec_repo,
                env=env,
            ),
            f"persist-{stage}",
        )


class CliResult:
    def __init__(
        self,
        *,
        returncode: int,
        document: dict[str, Any],
        stdout: str,
        stderr: str,
    ) -> None:
        self.returncode = returncode
        self.document = document
        self.stdout = stdout
        self.stderr = stderr


def spec_cli(
    args: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
) -> CliResult:
    child = subprocess.run(
        [sys.executable, "-c", CLI_BOOTSTRAP, *args],
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    try:
        document = json.loads(child.stdout)
    except json.JSONDecodeError as error:
        message = child.stderr.strip() or child.stdout.strip() or str(error)
        raise DogfoodFailure("spec-cli-json-invalid", message) from error
    if not isinstance(document, dict):
        raise DogfoodFailure("spec-cli-json-invalid", "Spec CLI output was not an object.")
    return CliResult(
        returncode=child.returncode,
        document=document,
        stdout=child.stdout,
        stderr=child.stderr,
    )


def require_success(result: CliResult, code: str) -> dict[str, Any]:
    if result.returncode != 0:
        message = (
            result.stderr.strip()
            or result.document.get("reason")
            or json.dumps(result.document)
        )
        raise DogfoodFailure(code, str(message))
    return result.document


def ensure_source_layout(core_repo: Path) -> None:
    required = [
        core_repo / "package.json",
        core_repo / "scripts/examples/with-example-entitlement.mjs",
        core_repo
        / "examples/targets/authenticated-project-creation-dogfood-app/server.mjs",
        core_repo
        / "examples/run-requests/authenticated-project-creation-dogfood.yaml",
        core_repo
        / "examples/skills/authenticated-project-creation-dogfood.browser.md",
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise DogfoodFailure(
            "core-source-layout-missing",
            f"Missing required Core dogfood source: {', '.join(missing)}",
        )


def build_core(core_repo: Path) -> None:
    child = subprocess.run(
        ["npm", "run", "runtime:package", "--silent"],
        cwd=core_repo,
        text=True,
        capture_output=True,
        check=False,
    )
    if child.returncode != 0:
        raise DogfoodFailure(
            "core-build-failed",
            child.stderr.strip() or child.stdout.strip() or "Core build failed.",
        )


def fill_test_environment_file(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "VS_DOGFOOD_EMAIL=tester@example.test",
                "VS_DOGFOOD_PASSWORD=reference-password",
                "",
            ]
        ),
        encoding="utf-8",
    )
    path.chmod(0o600)


def start_target(
    core_repo: Path, port: int, env: dict[str, str]
) -> subprocess.Popen[str]:
    target = (
        core_repo
        / "examples/targets/authenticated-project-creation-dogfood-app/server.mjs"
    )
    return subprocess.Popen(
        ["node", str(target)],
        cwd=core_repo,
        env={**env, "PORT": str(port)},
        text=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )


def stop_target(server: subprocess.Popen[str]) -> None:
    if server.poll() is not None:
        return
    server.terminate()
    try:
        server.wait(timeout=3)
    except subprocess.TimeoutExpired:
        server.kill()
        server.wait(timeout=3)


def wait_for_http(
    url: str, server: subprocess.Popen[str], timeout_seconds: float = 7
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if server.poll() is not None:
            stderr = server.stderr.read().strip() if server.stderr else ""
            raise DogfoodFailure(
                "target-start-failed",
                stderr or f"Target exited with code {server.returncode}.",
            )
        try:
            with urllib.request.urlopen(url, timeout=0.5) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, TimeoutError):
            pass
        time.sleep(0.1)
    raise DogfoodFailure("target-start-timeout", f"Timed out waiting for {url}.")


def target_state(base_url: str) -> dict[str, Any]:
    with urllib.request.urlopen(f"{base_url}/__state", timeout=2) as response:
        document = json.load(response)
    if not isinstance(document, dict):
        raise DogfoodFailure("target-state-invalid")
    return document


def assert_state(
    state: dict[str, Any],
    *,
    emailChecks: int,
    signIns: int,
    mediaLookups: int,
    commits: int,
    resources: int,
) -> None:
    expected = {
        "emailChecks": emailChecks,
        "signIns": signIns,
        "mediaLookups": mediaLookups,
        "commits": commits,
    }
    for name, value in expected.items():
        if state.get(name) != value:
            raise DogfoodFailure(
                f"state-{name}",
                f"Expected {name}={value}, observed {state.get(name)!r}.",
            )
    actual_resources = state.get("resources")
    if not isinstance(actual_resources, list) or len(actual_resources) != resources:
        raise DogfoodFailure(
            "state-resources",
            f"Expected resources={resources}, observed {actual_resources!r}.",
        )


def safe_state(state: dict[str, Any]) -> dict[str, int]:
    resources = state.get("resources")
    return {
        "emailChecks": int(state.get("emailChecks", 0)),
        "signIns": int(state.get("signIns", 0)),
        "mediaLookups": int(state.get("mediaLookups", 0)),
        "commits": int(state.get("commits", 0)),
        "resourceCount": len(resources) if isinstance(resources, list) else 0,
    }


def target_status(targets: Any, name: str) -> str | None:
    if not isinstance(targets, list):
        return None
    for target in targets:
        if isinstance(target, dict) and target.get("name") == name:
            value = target.get("status")
            return str(value) if value is not None else None
    return None


def require(condition: bool, code: str, message: str | None = None) -> None:
    if not condition:
        raise DogfoodFailure(code, message)


def available_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as allocator:
        allocator.bind(("127.0.0.1", 0))
        return int(allocator.getsockname()[1])


def revision(repo: Path) -> str:
    git = shutil.which("git")
    if git is None:
        return "unknown"
    child = subprocess.run(
        [git, "rev-parse", "HEAD"],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    return child.stdout.strip() if child.returncode == 0 else "unknown"


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except DogfoodFailure as error:
        print(
            json.dumps(
                {
                    "schema": SCHEMA,
                    "scenario": SCENARIO,
                    "status": "red",
                    "blocker": {"code": error.code, "message": str(error)},
                },
                indent=2,
            )
        )
        raise SystemExit(1)
