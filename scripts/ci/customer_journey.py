"""Product-truth customer journey (fixture trust).

One real customer walk, end to end, against live processes — the leg the readiness
reassessment (item #4) calls the heart of the product-truth gate:

1. the sibling Backend runs as a REAL HTTP server (``ci:journey-server``) on local
   Supabase, signs receipts with Core's committed fixture entitlement key, and serves
   the TEST-key-signed Core package built into ``dist/runtime-journey``;
2. this script mints a dev token, and the Spec CLI — driven only through its public
   surface — exchanges it, downloads the packaged runtime over HTTP
   (``GET /runtimes/{version}``; the dev-channel release 404s on ``/latest`` by
   design), verifies and installs it, and executes every protected leg with the
   BE-issued receipt on the INSTALLED runtime (never a source-checkout override);
3. a seeded run-request version drift turns validate RED with the packaged runtime's
   own ``main-skill-mismatch`` finding, ``repair`` stays byte-inert without approval
   (exit 4), the documented recovery (persist implement) restores green, and the one
   confirmed write run commits exactly one resource;
4. a second, unauthenticated use case is recorded (``run --record``), crystallized,
   and replayed with the target STOPPED — ``replayComparison.status == reproduced``
   proves the offline replay.

Trust is deliberately non-adversarial (fixture keys are committed material); what this
leg proves is the PLUMBING: real HTTP, real receipts, real download verification, real
protected execution, one lifecycle.

Usage: ``python scripts/ci/customer_journey.py`` (from the Spec repo root), with the
sibling checkouts resolvable (``VERIFYSIGNAL_CORE_DIR`` / ``VERIFYSIGNAL_BACKEND_DIR``
or identity resolution), the Core journey package already built
(``VERIFYSIGNAL_ALLOW_TEST_RELEASE_KEYS=1 npm run runtime:package -- --platform
current --out-dir dist/runtime-journey`` in the Core repo), BE deps installed and
``next build`` done, and local Supabase running with the BE schema applied.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import secrets
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

SCHEMA = "verifysignal.customer-journey/v1"
SCENARIO = "fixture-trust-customer-journey"
AUTH_ALIAS = "authenticated-project-creation-journey"
RECORD_ALIAS = "journey-home-recorded"
CLI_BOOTSTRAP = "import sys; from verifysignal_spec.cli import main; sys.exit(main())"
TEST_EMAIL = "journey@verifysignal.test"
BUCKET = "verifysignal-runtimes"

# Any of these lets the journey pass WITHOUT touching the BE or the packaged runtime:
# the flag re-trusts the committed test release key process-wide, the manifest vars
# short-circuit the HTTP download with a file:// install, and a pre-provisioned trust
# store / receipt / source Core would make the BE-issued receipt and the managed
# download decorative. Fail closed before anything else runs.
FORBIDDEN_ENV = [
    "VERIFYSIGNAL_ALLOW_TEST_RELEASE_KEYS",
    "VERIFYSIGNAL_RUNTIME_MANIFEST_PATH",
    "VERIFYSIGNAL_RUNTIME_MANIFEST_JSON",
    "VERIFYSIGNAL_ENTITLEMENT_PUBLIC_KEYS_JSON",
    "VERIFYSIGNAL_ENTITLEMENT_RECEIPT",
    "VERIFYSIGNAL_ENTITLEMENT_RECEIPT_PATH",
    "VERIFYSIGNAL_CORE_CMD",
]


class JourneyFailure(RuntimeError):
    def __init__(self, code: str, message: str | None = None) -> None:
        super().__init__(message or code)
        self.code = code


def require(condition: object, code: str, message: str | None = None) -> None:
    if not condition:
        raise JourneyFailure(code, message)


class CliResult:
    def __init__(
        self, *, returncode: int, document: dict[str, Any], stdout: str, stderr: str
    ) -> None:
        self.returncode = returncode
        self.document = document
        self.stdout = stdout
        self.stderr = stderr


def spec_cli(args: list[str], *, cwd: Path, env: dict[str, str]) -> CliResult:
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
        raise JourneyFailure("spec-cli-json-invalid", f"{args[0]}: {message}") from error
    if not isinstance(document, dict):
        raise JourneyFailure("spec-cli-json-invalid", "Spec CLI output was not an object.")
    return CliResult(
        returncode=child.returncode,
        document=document,
        stdout=child.stdout,
        stderr=child.stderr,
    )


def require_success(result: CliResult, code: str) -> dict[str, Any]:
    if result.returncode != 0:
        message = result.stderr.strip() or json.dumps(result.document)
        raise JourneyFailure(code, message)
    return result.document


def require_exit(result: CliResult, expected: int, code: str) -> dict[str, Any]:
    if result.returncode != expected:
        raise JourneyFailure(
            code,
            f"expected exit {expected}, got {result.returncode}: "
            f"{result.stderr.strip() or json.dumps(result.document)}",
        )
    return result.document


def run_json_tool(
    args: list[str], *, cwd: Path, env: dict[str, str], code: str
) -> dict[str, Any]:
    child = subprocess.run(
        args, cwd=cwd, env=env, text=True, capture_output=True, check=False
    )
    if child.returncode != 0:
        raise JourneyFailure(
            code, child.stderr.strip() or child.stdout.strip() or f"{args} failed"
        )
    text = child.stdout.strip()
    brace = text.find("{")
    try:
        document = json.loads(text[brace:] if brace >= 0 else text)
    except (json.JSONDecodeError, ValueError) as error:
        raise JourneyFailure(code, f"non-JSON output: {child.stdout[-400:]}") from error
    require(isinstance(document, dict), code, "tool output was not an object")
    return document


def available_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_for_http(url: str, server: subprocess.Popen[str], timeout_seconds: float = 10) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if server.poll() is not None:
            stderr = server.stderr.read().strip() if server.stderr else ""
            raise JourneyFailure(
                "target-start-failed", stderr or f"target exited {server.returncode}"
            )
        try:
            with urllib.request.urlopen(url, timeout=0.5) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, TimeoutError):
            pass
        time.sleep(0.1)
    raise JourneyFailure("target-start-timeout", f"timed out waiting for {url}")


def target_state(base_url: str) -> dict[str, Any]:
    with urllib.request.urlopen(f"{base_url}/__state", timeout=2) as response:
        document = json.load(response)
    require(isinstance(document, dict), "target-state-invalid")
    return document


def assert_state(state: dict[str, Any], code: str, **expected: int) -> None:
    for key, value in expected.items():
        observed = state.get(key)
        if key == "resources":
            observed = len(state.get("resources", []))
        require(observed == value, code, f"{key}: expected {value}, observed {observed}")


def revision(repo: Path) -> str:
    child = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    return child.stdout.strip() if child.returncode == 0 else "unknown"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def extract_fixture_entitlement_pem(core_repo: Path) -> str:
    source = (core_repo / "tests/fixtures/entitlement/receipt-fixtures.ts").read_text(
        encoding="utf-8"
    )
    begin = source.index("-----BEGIN PRIVATE KEY-----")
    end = source.index("-----END PRIVATE KEY-----", begin)
    block = source[begin : end + len("-----END PRIVATE KEY-----")]
    # The TS fixture may inline the PEM with template-literal escapes; normalize both.
    pem = block.replace("\\n", "\n").replace('" +\n  "', "").replace('",\n', "\n")
    require("BEGIN PRIVATE KEY" in pem and "END PRIVATE KEY" in pem, "fixture-pem-missing")
    return pem.strip() + "\n"


def parse_supabase_env(backend_repo: Path, base_env: dict[str, str]) -> dict[str, str]:
    child = subprocess.run(
        ["npm", "run", "--silent", "supabase:local-env"],
        cwd=backend_repo,
        env=base_env,
        text=True,
        capture_output=True,
        check=False,
    )
    values: dict[str, str] = {}
    for line in child.stdout.splitlines():
        if "=" in line and not line.startswith("#"):
            key, _, value = line.partition("=")
            if key in {"SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"} and value:
                values[key] = value
    require(
        "SUPABASE_URL" in values and "SUPABASE_SERVICE_ROLE_KEY" in values,
        "supabase-env-unavailable",
        child.stderr.strip() or child.stdout.strip() or "supabase:local-env yielded nothing",
    )
    return values


def record_skill_content() -> str:
    return "\n".join(
        [
            "# Journey home recorded (record → crystallize → offline replay)",
            "",
            "Loads the reference target's public home page and asserts the ready heading.",
            "",
            "```yaml",
            "schemaVersion: qa-skill/v1",
            "skill:",
            f"  id: skill.{RECORD_ALIAS}",
            "  version: 1.0.0",
            "  kind: browser",
            "  name: Journey Home Recorded",
            "  description: Load the public home page and assert the ready heading.",
            "  status: active",
            "  tags: [journey, replay, browser]",
            "parameters:",
            "  - name: baseUrl",
            "    type: string",
            "    required: true",
            "failurePolicy:",
            "  stopOnFailure: true",
            "  retries: 0",
            "evidence:",
            "  required: [report]",
            "  optional: []",
            "browser:",
            "  targets:",
            "    readyHeading:",
            "      css: h1",
            "  steps:",
            "    - id: open",
            "      action: navigate",
            '      value: "{{parameters.baseUrl}}"',
            "  assertions:",
            "    - id: home-heading-visible",
            "      kind: text",
            "      target: readyHeading",
            "      expected: Reference application ready",
            "      gateId: home-heading",
            "      evidenceRequired: []",
            "```",
            "",
        ]
    )


def record_run_request_content(base_url: str) -> str:
    return yaml.safe_dump(
        {
            "schemaVersion": "qa-run-request/v1",
            "request": {
                "id": f"request.{RECORD_ALIAS}",
                "name": "Journey home recorded",
            },
            "target": "browser",
            "validationScope": "feature-level",
            "skills": [{"id": f"skill.{RECORD_ALIAS}", "version": "1.0.0"}],
            "parameters": {"baseUrl": base_url},
            "sideEffectPolicy": {"class": "none", "mode": "enforce"},
            "evidenceOverrides": {"required": ["report"], "optional": ["network"]},
        },
        sort_keys=False,
    )


def persist_stage(
    *,
    stage: str,
    alias: str,
    payload: dict[str, Any],
    scope_all: bool,
    workspace: Path,
    payload_root: Path,
    spec_repo: Path,
    env: dict[str, str],
) -> None:
    payload_path = payload_root / f"{alias}-{stage}.json"
    payload_path.write_text(
        json.dumps(
            {
                "stage": stage,
                "alias": alias,
                "requestedAt": "2026-07-31T00:00:00Z",
                "payload": payload,
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
                *(["--scope", "all"] if scope_all else ["--alias", alias]),
                "--project",
                str(workspace),
                "--payload",
                str(payload_path),
                "--json",
            ],
            cwd=spec_repo,
            env=env,
        ),
        f"persist-{alias}-{stage}",
    )


def auth_stage_payloads(
    *,
    core_repo: Path,
    base_url: str,
    request_content: str,
    skill_content: str,
) -> list[tuple[str, dict[str, Any]]]:
    runtime_inputs = [
        {"name": "baseUrl", "source": "default", "value": base_url, "persistValue": True},
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
    return [
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
                "git": {"available": True, "hash": revision(core_repo)},
                "safeInspectionPaths": [
                    "examples/targets/authenticated-project-creation-dogfood-app/",
                    "examples/run-requests/authenticated-project-creation-dogfood.yaml",
                    "examples/skills/authenticated-project-creation-dogfood.browser.md",
                ],
                "blockedSensitivePaths": [".env", ".env.*", "*secret*"],
                "validationGoals": [
                    "Prove the full customer journey against the managed runtime.",
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
                        },
                        {
                            "id": "surface-public-home",
                            "surfaceType": "page",
                            "path": "/",
                            "title": "Public home page",
                            "sourceRefs": [
                                "examples/targets/authenticated-project-creation-dogfood-app/server.mjs",
                            ],
                            "priority": "medium",
                        },
                    ],
                    "candidateUseCases": [
                        {
                            "alias": AUTH_ALIAS,
                            "surface": "/projects/new?mode=individual",
                            "behavior": (
                                "Authenticate, resolve linked media, and publish one "
                                "individual project."
                            ),
                            "rationale": (
                                "Customer-journey leg for protected-page grounding and "
                                "a controlled write boundary."
                            ),
                            "confidence": "high",
                            "priority": "high",
                            "sourceInventoryItems": ["flow-authenticated-project-create"],
                            "knownRuntimeRequirements": ["credential:qa", "write operation"],
                        },
                        {
                            "alias": RECORD_ALIAS,
                            "surface": "/",
                            "behavior": "Load the public home page and assert readiness.",
                            "rationale": (
                                "Unauthenticated record → crystallize → offline replay leg."
                            ),
                            "confidence": "high",
                            "priority": "medium",
                            "sourceInventoryItems": ["surface-public-home"],
                            "knownRuntimeRequirements": [],
                        },
                    ],
                },
            },
        ),
        (
            "specify",
            {
                "alias": AUTH_ALIAS,
                "surface": "/projects/new?mode=individual",
                "behavior": (
                    "Authenticate through split email and password routes, resolve "
                    "linked media, and publish one individual project."
                ),
                "expectedOutcome": (
                    "Probe reaches but does not execute publish; confirmed normal run "
                    "creates one traceable local project."
                ),
                "customSourceReason": "Cross-repository customer-journey leg.",
            },
        ),
        (
            "clarify",
            {
                "alias": AUTH_ALIAS,
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
                "alias": AUTH_ALIAS,
                "runRequest": f".verifysignal/run-requests/{AUTH_ALIAS}.yaml",
                "reusableSkills": [f".verifysignal/skills/{AUTH_ALIAS}.browser.md"],
                "runtimeInputs": runtime_inputs,
                "validationGates": [
                    {
                        "id": "created-project-title",
                        "description": "The created project page renders the generated title.",
                        "required": True,
                    }
                ],
                "unresolvedBlockingClarifications": [],
            },
        ),
        (
            "tasks",
            {
                "alias": AUTH_ALIAS,
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
                "alias": AUTH_ALIAS,
                "runRequest": {
                    "path": f".verifysignal/run-requests/{AUTH_ALIAS}.yaml",
                    "content": request_content,
                },
                "skills": [
                    {
                        "path": f".verifysignal/skills/{AUTH_ALIAS}.browser.md",
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
                        "Stopping the isolated target process removes all local fixture "
                        "resources."
                    ),
                },
                "rerunPolicy": {"afterNoCommit": "allowed", "afterCommit": "blocked"},
                "writeFlowSummary": {
                    "commitBoundary": "publish",
                    "resourceType": "project",
                    "target": "isolated-local-reference-app",
                },
                "recordUpdates": {},
            },
        ),
    ]


def record_stage_payloads(base_url: str) -> list[tuple[str, dict[str, Any]]]:
    request_content = record_run_request_content(base_url)
    skill_content = record_skill_content()
    return [
        (
            "specify",
            {
                "alias": RECORD_ALIAS,
                "surface": "/",
                "behavior": "Load the public home page and assert the ready heading.",
                "expectedOutcome": "The public home page renders the ready heading.",
                "customSourceReason": "Unauthenticated record/replay journey leg.",
                "sideEffects": {"class": "none"},
            },
        ),
        (
            "clarify",
            {
                "alias": RECORD_ALIAS,
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
                "alias": RECORD_ALIAS,
                "runRequest": f".verifysignal/run-requests/{RECORD_ALIAS}.yaml",
                "reusableSkills": [f".verifysignal/skills/{RECORD_ALIAS}.browser.md"],
                "runtimeInputs": [
                    {
                        "name": "baseUrl",
                        "source": "default",
                        "value": base_url,
                        "persistValue": True,
                    }
                ],
                "validationGates": [
                    {
                        "id": "home-heading",
                        "description": "The public home page renders the ready heading.",
                        "required": True,
                    }
                ],
                "unresolvedBlockingClarifications": [],
            },
        ),
        (
            "tasks",
            {
                "alias": RECORD_ALIAS,
                "tasks": [
                    {
                        "id": "T001",
                        "description": "Persist the read-only browser artifacts.",
                        "artifact": "run-request",
                    }
                ],
                "dependencies": [],
                "parallelizableGroups": [],
            },
        ),
        (
            "implement",
            {
                "alias": RECORD_ALIAS,
                "runRequest": {
                    "path": f".verifysignal/run-requests/{RECORD_ALIAS}.yaml",
                    "content": request_content,
                },
                "skills": [
                    {
                        "path": f".verifysignal/skills/{RECORD_ALIAS}.browser.md",
                        "content": skill_content,
                    }
                ],
                "runtimeInputs": [
                    {
                        "name": "baseUrl",
                        "source": "default",
                        "value": base_url,
                        "persistValue": True,
                    }
                ],
                "sideEffects": {"class": "none"},
                "recordUpdates": {},
            },
        ),
    ]


def main() -> int:
    # Guards FIRST — before sibling resolution, before any verifysignal_spec import.
    for name in FORBIDDEN_ENV:
        if os.environ.get(name) is not None:
            print(f"FAIL: {name} is set — the journey must not inherit it.", file=sys.stderr)
            return 1

    from verifysignal_spec.repos import resolve_sibling_repo
    from verifysignal_spec.runtime.distribution import normalize_platform
    from verifysignal_spec.runtime.release_signature import (
        TEST_RELEASE_KEY_ID,
        TEST_RELEASE_PUBLIC_KEY_PEM,
    )

    spec_repo = Path(__file__).resolve().parents[2]
    core_repo = resolve_sibling_repo("core")
    backend_repo = resolve_sibling_repo("backend")
    if core_repo is None or backend_repo is None:
        print("FAIL: sibling Core/Backend checkouts are not resolvable.", file=sys.stderr)
        return 1
    core_repo = Path(core_repo)
    backend_repo = Path(backend_repo)

    summary: dict[str, Any] = {
        "schema": SCHEMA,
        "scenario": SCENARIO,
        "status": "red",
        "specRevision": revision(spec_repo),
        "coreRevision": revision(core_repo),
        "backendRevision": revision(backend_repo),
        "gates": {},
        "observations": {},
    }

    base_env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("VERIFYSIGNAL_")
        and key not in {"NEXT_PUBLIC_SUPABASE_URL", "SUPABASE_SECRET_KEY"}
    }
    if base_env.get("NODE_ENV") == "test":
        del base_env["NODE_ENV"]

    target: subprocess.Popen[str] | None = None
    backend_started = False
    exit_stack = contextlib.ExitStack()

    with tempfile.TemporaryDirectory(prefix="verifysignal-customer-journey-") as temporary:
        tmp = Path(temporary)
        try:
            platform = normalize_platform()
            require(bool(platform), "managed-platform-unsupported")

            # Artifact preflight: the journey package must be the TEST-key build in its
            # own out dir — never the ephemeral production-shaped build in dist/runtime.
            journey_dist = core_repo / "dist/runtime-journey"
            metadata_path = journey_dist / "verifysignal-core-release.json"
            signature_path = journey_dist / "verifysignal-core-release.json.sig"
            require(
                metadata_path.exists() and signature_path.exists(),
                "journey-package-missing",
                "Build it with: VERIFYSIGNAL_ALLOW_TEST_RELEASE_KEYS=1 npm run "
                "runtime:package -- --platform current --out-dir dist/runtime-journey",
            )
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            signature = json.loads(signature_path.read_text(encoding="utf-8"))
            require(metadata.get("channel") == "dev", "journey-package-not-test-key")
            require(
                signature.get("keyId") == TEST_RELEASE_KEY_ID,
                "journey-package-wrong-signer",
            )
            entry = next(
                (
                    item
                    for item in metadata.get("packages", [])
                    if item.get("platform") == str(platform)
                ),
                None,
            )
            require(entry is not None, "journey-package-platform-missing")
            artifact_path = journey_dist / str(entry["filename"])
            require(artifact_path.exists(), "journey-artifact-missing")
            core_version = str(entry["coreVersion"])
            declared_version = str(
                json.loads((core_repo / "package.json").read_text(encoding="utf-8"))[
                    "version"
                ]
            )
            require(core_version == declared_version, "journey-version-skew")
            summary["gates"]["artifactPreflight"] = "passed"

            release_keys = json.dumps({TEST_RELEASE_KEY_ID: TEST_RELEASE_PUBLIC_KEY_PEM})
            fixture_pem = extract_fixture_entitlement_pem(core_repo)
            token_hash_secret = secrets.token_hex(32)
            supabase = parse_supabase_env(backend_repo, base_env)

            be_env = {
                **base_env,
                **supabase,
                "VERIFYSIGNAL_TOKEN_HASH_SECRET": token_hash_secret,
                "VERIFYSIGNAL_ENTITLEMENT_PRIVATE_KEY": fixture_pem,
                "VERIFYSIGNAL_ENTITLEMENT_KEY_ID": "vs-entitlement-fixture-key",
                "VERIFYSIGNAL_RUNTIME_RELEASE_PUBLIC_KEYS": release_keys,
                "VERIFYSIGNAL_RUNTIME_STORAGE_BUCKET": BUCKET,
            }

            be_port = available_port()
            ready = run_json_tool(
                [
                    "npm",
                    "run",
                    "--silent",
                    "ci:journey-server",
                    "--",
                    "start",
                    "--port",
                    str(be_port),
                ],
                cwd=backend_repo,
                env=be_env,
                code="backend-start-failed",
            )
            require(ready.get("status") == "ready", "backend-not-ready")
            backend_started = True
            summary["gates"]["backendUp"] = "passed"

            registered = run_json_tool(
                [
                    "npm",
                    "run",
                    "--silent",
                    "entitlement:register-runtime-release",
                    "--",
                    "--artifact",
                    str(artifact_path),
                    "--metadata",
                    str(metadata_path),
                    "--signature",
                    str(signature_path),
                    "--platform",
                    "current",
                    "--bucket",
                    BUCKET,
                    "--json",
                ],
                cwd=backend_repo,
                env=be_env,
                code="release-registration-failed",
            )
            require(registered.get("status") == "accepted", "release-not-accepted")
            summary["gates"]["releaseRegistered"] = "passed"

            token_document = run_json_tool(
                [
                    "npm",
                    "run",
                    "--silent",
                    "entitlement:dev-token",
                    "--",
                    "--email",
                    TEST_EMAIL,
                    "--environment",
                    "local",
                    "--local-only",
                    "--json",
                ],
                cwd=backend_repo,
                env=be_env,
                code="dev-token-failed",
            )
            raw_token = str(token_document.get("rawToken") or "")
            require(raw_token.startswith("vs_"), "dev-token-shape")
            summary["gates"]["tokenIssued"] = "passed"

            api_base_url = f"http://127.0.0.1:{be_port}/api"
            spec_env = {
                **base_env,
                "VERIFYSIGNAL_API_BASE_URL": api_base_url,
                "VERIFYSIGNAL_EMAIL_UNLOCK_TOKEN": raw_token,
                "VERIFYSIGNAL_RUNTIME_CACHE_DIR": str(tmp / "managed-cache"),
                "VERIFYSIGNAL_CORE_VERSION": core_version,
                "VERIFYSIGNAL_RUNTIME_RELEASE_PUBLIC_KEYS": release_keys,
                "VERIFYSIGNAL_USAGE_PING": "0",
            }
            protected_env = {
                **spec_env,
                "VERIFYSIGNAL_ALLOW_FIXTURE_ENTITLEMENT_KEYS": "1",
            }

            workspace = tmp / "workspace"
            payload_root = tmp / "payloads"
            workspace.mkdir(parents=True)
            payload_root.mkdir(parents=True)
            subprocess.run(
                ["git", "init", "-q", str(workspace)],
                check=True,
                capture_output=True,
                text=True,
            )

            initialized = require_success(
                spec_cli(
                    ["init", str(workspace), "--integration", "codex", "--json"],
                    cwd=spec_repo,
                    env=spec_env,
                ),
                "init-command",
            )
            init_runtime = initialized.get("runtime") or initialized.get(
                "managedRuntimeReadiness", {}
            )
            require(
                init_runtime.get("source") == "managed-download",
                "managed-install-source",
                f"init runtime source was {init_runtime.get('source')!r}",
            )
            summary["gates"]["managedInstall"] = "passed"
            summary["observations"]["managedInstall"] = {
                "source": init_runtime.get("source"),
                "version": init_runtime.get("runtimeVersion"),
            }

            require_success(
                spec_cli(
                    ["core", "reset", "--project", str(workspace), "--json"],
                    cwd=spec_repo,
                    env=spec_env,
                ),
                "core-reset-command",
            )

            checked = require_success(
                spec_cli(
                    ["check", "--project", str(workspace), "--json"],
                    cwd=spec_repo,
                    env=spec_env,
                ),
                "check-command",
            )
            check_runtime = checked.get("managedRuntimeReadiness", {})
            require(
                check_runtime.get("source") == "managed-cache",
                "managed-cache-source",
                f"check runtime source was {check_runtime.get('source')!r}",
            )
            require(
                all(
                    item.get("source")
                    not in {"workspace", "env", "path", "ancestor-sibling"}
                    for item in check_runtime.get("attempts", [])
                    if isinstance(item, dict)
                ),
                "managed-local-contamination",
            )
            summary["gates"]["managedCache"] = "passed"

            version_document = require_success(
                spec_cli(
                    ["core", "version", "--project", str(workspace), "--json"],
                    cwd=spec_repo,
                    env=spec_env,
                ),
                "core-version-command",
            )
            version_data = version_document.get("data", version_document)
            package_id = (version_data.get("runtime") or {}).get("packageId")
            require(bool(package_id), "packaged-identity-missing")
            require(
                version_data.get("verifysignalVersion") == core_version,
                "packaged-version-mismatch",
            )
            summary["gates"]["packagedIdentity"] = "passed"
            summary["observations"]["packagedIdentity"] = {"packageId": package_id}

            target_port = available_port()
            base_url = f"http://127.0.0.1:{target_port}"
            target = subprocess.Popen(
                [
                    "node",
                    str(
                        core_repo
                        / "examples/targets/authenticated-project-creation-dogfood-app/server.mjs"
                    ),
                ],
                cwd=core_repo,
                env={
                    **base_env,
                    "PORT": str(target_port),
                    "VS_DOGFOOD_EMAIL": "tester@example.test",
                    "VS_DOGFOOD_PASSWORD": "reference-password",
                },
                text=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            wait_for_http(f"{base_url}/", target)

            source_request = (
                core_repo / "examples/run-requests/authenticated-project-creation-dogfood.yaml"
            )
            source_skill = (
                core_repo / "examples/skills/authenticated-project-creation-dogfood.browser.md"
            )
            request_document = yaml.safe_load(source_request.read_text(encoding="utf-8"))
            request_document["request"]["id"] = f"request.{AUTH_ALIAS}"
            request_document["parameters"]["baseUrl"] = base_url
            request_document["skills"] = [
                {"id": f"skill.{AUTH_ALIAS}", "version": "1.0.0"}
            ]
            request_content = yaml.safe_dump(request_document, sort_keys=False)
            skill_content = source_skill.read_text(encoding="utf-8").replace(
                "skill.authenticated-project-creation-dogfood", f"skill.{AUTH_ALIAS}"
            )

            require_success(
                spec_cli(
                    [
                        "workflow",
                        "run",
                        "verifysignal-use-case",
                        "--goal",
                        "Validate the full customer journey against the managed runtime.",
                        "--alias",
                        AUTH_ALIAS,
                        "--integration",
                        "codex",
                        "--project",
                        str(workspace),
                        "--json",
                    ],
                    cwd=spec_repo,
                    env=spec_env,
                ),
                "workflow-run-auth",
            )
            for stage, payload in auth_stage_payloads(
                core_repo=core_repo,
                base_url=base_url,
                request_content=request_content,
                skill_content=skill_content,
            ):
                persist_stage(
                    stage=stage,
                    alias=AUTH_ALIAS,
                    payload=payload,
                    scope_all=stage == "understand",
                    workspace=workspace,
                    payload_root=payload_root,
                    spec_repo=spec_repo,
                    env=spec_env,
                )
            summary["gates"]["canonicalPersistence"] = "passed"

            env_file = workspace / ".env.verifysignal.test.local"
            prepared = require_success(
                spec_cli(
                    [
                        "credentials",
                        "prepare",
                        AUTH_ALIAS,
                        "--project",
                        str(workspace),
                        "--env-file",
                        str(env_file),
                        "--json",
                    ],
                    cwd=spec_repo,
                    env=spec_env,
                ),
                "credential-preparation",
            )
            require(prepared.get("gitExcluded") is True, "credential-git-exclude")
            require(prepared.get("permissions") == "0600", "credential-permissions")
            env_file.write_text(
                "VS_DOGFOOD_EMAIL=tester@example.test\n"
                "VS_DOGFOOD_PASSWORD=reference-password\n",
                encoding="utf-8",
            )
            env_file.chmod(0o600)
            summary["gates"]["credentialPreparation"] = "passed"

            probe = require_success(
                spec_cli(
                    [
                        "probe",
                        str(workspace / f".verifysignal/run-requests/{AUTH_ALIAS}.yaml"),
                        "--skill",
                        str(workspace / f".verifysignal/skills/{AUTH_ALIAS}.browser.md"),
                        "--project",
                        str(workspace),
                        "--env-file",
                        str(env_file),
                        "--json",
                    ],
                    cwd=spec_repo,
                    env=protected_env,
                ),
                "probe-command",
            )
            require(probe.get("status") == "passed", "probe-status")
            boundary = probe.get("data", {}).get("boundary", probe.get("boundary", {}))
            require(boundary.get("reached") is True, "probe-boundary-reached")
            require(boundary.get("executed") is False, "probe-boundary-not-executed")
            assert_state(
                target_state(base_url),
                "probe-state",
                emailChecks=1,
                signIns=1,
                mediaLookups=1,
                commits=0,
                resources=0,
            )
            summary["gates"]["probe"] = "passed"

            # Seeded failure: version drift on the SKILL's declared version. The skill is
            # the legitimately hand-editable artifact (the generated run-request is
            # defended by the workspace's own stage-handoff guardrail), and the packaged
            # runtime's reference validation must detect the mismatch against the
            # run-request's pinned 1.0.0 — a real product red from the installed runtime.
            skill_path = workspace / f".verifysignal/skills/{AUTH_ALIAS}.browser.md"
            run_request_path = workspace / f".verifysignal/run-requests/{AUTH_ALIAS}.yaml"
            request_sha_before = sha256_bytes(run_request_path.read_bytes())
            drifted_skill = skill_path.read_text(encoding="utf-8").replace(
                "version: 1.0.0", "version: 9.9.9", 1
            )
            require("9.9.9" in drifted_skill, "seeded-drift-rewrite")
            skill_path.write_text(drifted_skill, encoding="utf-8")
            drifted_sha = sha256_bytes(skill_path.read_bytes())

            red_validate = spec_cli(
                [
                    "validate",
                    AUTH_ALIAS,
                    "--runtime-readiness",
                    "--project",
                    str(workspace),
                    "--env-file",
                    str(env_file),
                    "--json",
                ],
                cwd=spec_repo,
                env=protected_env,
            )
            require_exit(red_validate, 2, "seeded-drift-not-red")
            # The validate envelope wraps the runtime finding in a generic
            # runtime.authoring-readiness-blocked blocker; the SPECIFIC category surfaces
            # on the detail command the blocker itself names as the recovery path.
            drift_detail = red_validate.stdout
            if "main-skill-mismatch" not in drift_detail:
                drift_detail = spec_cli(
                    [
                        "workflow",
                        "check",
                        "validate",
                        "--alias",
                        AUTH_ALIAS,
                        "--project",
                        str(workspace),
                        "--json",
                    ],
                    cwd=spec_repo,
                    env=protected_env,
                ).stdout
            debug_dir = os.environ.get("VERIFYSIGNAL_JOURNEY_DEBUG_DIR")
            if debug_dir and "main-skill-mismatch" not in drift_detail:
                Path(debug_dir, "red-validate.json").write_text(
                    red_validate.stdout, encoding="utf-8"
                )
                Path(debug_dir, "drift-detail.json").write_text(
                    drift_detail, encoding="utf-8"
                )
            require(
                "main-skill-mismatch" in drift_detail,
                "seeded-drift-finding",
                f"neither validate nor its detail surface named main-skill-mismatch: "
                f"{drift_detail[-900:]}",
            )
            summary["gates"]["seededDrift"] = "passed"

            repair = spec_cli(
                ["repair", AUTH_ALIAS, "--project", str(workspace), "--json"],
                cwd=spec_repo,
                env=protected_env,
            )
            require_exit(repair, 4, "repair-approval-exit")
            approval_status = repair.document.get("repair", {}).get("approvalStatus")
            require(
                approval_status in {"pending", "proposed"},
                "repair-approval-status",
                f"approvalStatus was {approval_status!r}: "
                f"{json.dumps(repair.document)[:600]}",
            )
            summary["observations"]["repairApprovalStatus"] = approval_status
            require(
                sha256_bytes(skill_path.read_bytes()) == drifted_sha,
                "repair-approval-not-inert",
            )
            require(
                sha256_bytes(run_request_path.read_bytes()) == request_sha_before,
                "repair-touched-run-request",
            )
            summary["gates"]["repairApprovalGate"] = "passed"

            # Documented recovery: re-persist the canonical implement payload.
            implement_payload = auth_stage_payloads(
                core_repo=core_repo,
                base_url=base_url,
                request_content=request_content,
                skill_content=skill_content,
            )[-1][1]
            persist_stage(
                stage="implement",
                alias=AUTH_ALIAS,
                payload=implement_payload,
                scope_all=False,
                workspace=workspace,
                payload_root=payload_root,
                spec_repo=spec_repo,
                env=spec_env,
            )
            green_validate = require_success(
                spec_cli(
                    [
                        "validate",
                        AUTH_ALIAS,
                        "--runtime-readiness",
                        "--project",
                        str(workspace),
                        "--env-file",
                        str(env_file),
                        "--json",
                    ],
                    cwd=spec_repo,
                    env=protected_env,
                ),
                "restored-validate",
            )
            require(green_validate.get("status") == "passed", "restored-validate-status")
            summary["gates"]["canonicalRestore"] = "passed"

            readiness = require_success(
                spec_cli(
                    [
                        "workflow",
                        "check",
                        "run",
                        "--alias",
                        AUTH_ALIAS,
                        "--project",
                        str(workspace),
                        "--json",
                    ],
                    cwd=spec_repo,
                    env=spec_env,
                ),
                "run-readiness",
            )
            require(readiness.get("status") == "ready", "run-readiness-status")
            require(readiness.get("canProceed") is True, "run-readiness-cannot-proceed")
            run_args = [
                "run",
                AUTH_ALIAS,
                "--project",
                str(workspace),
                "--profile",
                "normal",
                "--env-file",
                str(env_file),
                "--non-interactive",
                "--json",
            ]
            if readiness.get("requiresConfirmation") is True:
                confirmation = readiness.get("confirmation")
                require(isinstance(confirmation, dict), "write-confirmation-missing")
                confirmation_id = str(confirmation.get("id") or "")
                require(bool(confirmation_id), "write-confirmation-id-missing")
                run_args.extend(["--confirm-risk", confirmation_id])

            committed_run = require_success(
                spec_cli(run_args, cwd=spec_repo, env=protected_env),
                "authorized-run",
            )
            require(committed_run.get("status") == "passed", "run-status")
            require(
                committed_run.get("postCommitInterpretation", {}).get("sideEffectStatus")
                == "committed-confirmed",
                "run-commit-confirmation",
            )
            assert_state(
                target_state(base_url),
                "run-state",
                emailChecks=2,
                signIns=2,
                mediaLookups=2,
                commits=1,
                resources=1,
            )
            summary["gates"]["runCommitted"] = "passed"

            # Record → crystallize → offline replay on the unauthenticated leg.
            require_success(
                spec_cli(
                    [
                        "workflow",
                        "run",
                        "verifysignal-use-case",
                        "--goal",
                        "Record and replay the public home page offline.",
                        "--alias",
                        RECORD_ALIAS,
                        "--integration",
                        "codex",
                        "--project",
                        str(workspace),
                        "--json",
                    ],
                    cwd=spec_repo,
                    env=spec_env,
                ),
                "workflow-run-record",
            )
            for stage, payload in record_stage_payloads(base_url):
                persist_stage(
                    stage=stage,
                    alias=RECORD_ALIAS,
                    payload=payload,
                    scope_all=False,
                    workspace=workspace,
                    payload_root=payload_root,
                    spec_repo=spec_repo,
                    env=spec_env,
                )

            recorded = require_success(
                spec_cli(
                    [
                        "run",
                        RECORD_ALIAS,
                        "--project",
                        str(workspace),
                        "--profile",
                        "normal",
                        "--record",
                        "--non-interactive",
                        "--json",
                    ],
                    cwd=spec_repo,
                    env=protected_env,
                ),
                "record-run",
            )
            require(recorded.get("status") == "passed", "record-run-status")
            evidence_dir = str(recorded.get("evidenceDir") or "")
            require(bool(evidence_dir), "record-evidence-missing")
            evidence_path = Path(evidence_dir)
            if not evidence_path.is_absolute():
                evidence_path = workspace / evidence_path
            require(evidence_path.exists(), "record-evidence-dir-missing")
            summary["gates"]["recordRun"] = "passed"

            fixture_dir = tmp / "crystallized-fixture"
            crystallized = require_success(
                spec_cli(
                    [
                        "crystallize",
                        str(evidence_path),
                        "--out",
                        str(fixture_dir),
                        "--project",
                        str(workspace),
                        "--json",
                    ],
                    cwd=spec_repo,
                    env=protected_env,
                ),
                "crystallize-command",
            )
            require(crystallized.get("status") == "passed", "crystallize-status")
            summary["gates"]["crystallize"] = "passed"

            # Stop the target BEFORE replay: reproduction with the origin dead is the
            # offline proof.
            target.terminate()
            try:
                target.wait(timeout=5)
            except subprocess.TimeoutExpired:
                target.kill()
                target.wait(timeout=5)
            target = None

            replayed = require_success(
                spec_cli(
                    [
                        "run",
                        RECORD_ALIAS,
                        "--project",
                        str(workspace),
                        "--profile",
                        "normal",
                        "--replay",
                        str(fixture_dir),
                        "--non-interactive",
                        "--json",
                    ],
                    cwd=spec_repo,
                    env=protected_env,
                ),
                "replay-run",
            )
            require(replayed.get("status") == "passed", "replay-status")
            comparison = (
                replayed.get("data", {}).get("replayComparison")
                or replayed.get("core", {}).get("data", {}).get("replayComparison")
                or {}
            )
            require(
                comparison.get("status") == "reproduced",
                "replay-not-reproduced",
                f"replayComparison was {comparison!r}",
            )
            summary["gates"]["offlineReplay"] = "passed"
            summary["status"] = "green"
        except JourneyFailure as error:
            summary["blocker"] = {"code": error.code, "message": str(error)}
        except Exception as error:  # noqa: BLE001 - defensive summary boundary
            summary["blocker"] = {"code": "journey-execution-error", "message": str(error)}
        finally:
            if target is not None:
                target.terminate()
                try:
                    target.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    target.kill()
            if backend_started:
                subprocess.run(
                    ["npm", "run", "--silent", "ci:journey-server", "--", "stop"],
                    cwd=backend_repo,
                    env=base_env,
                    capture_output=True,
                    text=True,
                    check=False,
                )
            exit_stack.close()

    print(json.dumps(summary, indent=2))
    if summary["status"] != "green":
        blocker = summary.get("blocker", {})
        print(
            f"FAIL: journey {blocker.get('code', 'unknown')}: {blocker.get('message', '')}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
