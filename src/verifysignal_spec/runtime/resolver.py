from __future__ import annotations

import os
import shutil
from pathlib import Path

from verifysignal_spec.core.adapter import CoreAdapter
from verifysignal_spec.core.contracts import (
    PUBLIC_CONTRACT_VERSION,
    core_supports_crystallize,
    core_supports_discover,
    core_supports_probe,
    core_supports_run_record,
    core_supports_run_replay,
)
from verifysignal_spec.core.errors import CoreExecutionError, CoreMissingError
from verifysignal_spec.workspace.repository import (
    get_core_command,
    get_core_configuration,
    get_entitlement_api_base_url,
)

from .cache import load_cache_entry, mark_cache_used
from .distribution import (
    RuntimeDistributionClient,
    install_from_authorization,
    install_from_manifest,
    load_manifest,
    manifest_entries,
    normalize_platform,
    prepare_verification_keys,
    select_manifest_entry,
)
from .entitlement import ensure_entitlement, load_receipt, resolve_entitlement_config
from .models import (
    ManagedRuntimeReadinessResult,
    RuntimeApiStatus,
    RuntimeCacheStatus,
    RuntimeEntitlementStatus,
    RuntimeVerificationKeyStatus,
    RuntimeSetupBlocker,
    RuntimeSourceAttempt,
)

# Optional Core operations are ADVERTISED, never assumed: they are deliberately excluded from
# REQUIRED_OPERATIONS (requiring them would mark every older Core incompatible), so a Core can be
# fully compatible and still not implement them. Invoking one anyway crashes inside Core on an
# unknown subcommand — an opaque failure the caller cannot act on.
#
# Every context that invokes an optional operation registers it here ONCE, and `_verify_command`
# enforces the registry on every ready-returning path. That is what keeps this a closed class: a
# newly wired optional operation gets the capability gate (and its ratchet test) by registration,
# instead of each new caller having to remember to re-add the check.
OPTIONAL_CAPABILITY_PROBES = {
    "discover": core_supports_discover,
    "crystallize": core_supports_crystallize,
    "probe": core_supports_probe,
    # run --record / --replay are MODES of run, advertised in its version entry. They are required
    # CONDITIONALLY (only when the flag is passed), so they are registered here but selected by the
    # caller via ensure_core_runtime(required_capability=...), not by CONTEXT_REQUIRED_CAPABILITY.
    "run-record": core_supports_run_record,
    "run-replay": core_supports_run_replay,
}
CONTEXT_REQUIRED_CAPABILITY = {
    "discover": "discover",
    "crystallize": "crystallize",
    "probe": "probe",
}


def capability_blocker_code(capability: str) -> str:
    return f"core.{capability}-unsupported"


CAPABILITY_BLOCKER_CODES = {capability_blocker_code(name) for name in OPTIONAL_CAPABILITY_PROBES}


def resolve_requested_core_version(project: Path) -> tuple[str | None, RuntimeSetupBlocker | None]:
    """Resolve a LOCALLY-pinned Core version for the managed distribution API.

    Order: explicit env pin, then the workspace-persisted version (recorded by
    `core setup` as the last verified version). There is still no shipped default —
    guessing a version yields opaque 404s from the exact-match download API — but a
    local answer is no longer the only answer: when this returns None the caller asks
    the backend for the current version (`/runtimes/latest`). That matters because the
    persisted version can ONLY ever be written after a Core is already installed, so on
    a fresh machine this function cannot succeed by construction.
    """
    env_version = (os.environ.get("VERIFYSIGNAL_CORE_VERSION") or "").strip()
    if env_version:
        return env_version, None
    workspace_version = get_core_configuration(project).get("coreVersion")
    if workspace_version:
        return str(workspace_version), None
    return None, RuntimeSetupBlocker(
        code="distribution.version-unspecified",
        message="No VerifySignal Core version is pinned for managed runtime download.",
        recoveryCommand=(
            "Set VERIFYSIGNAL_CORE_VERSION=<version>, configure "
            "VERIFYSIGNAL_RUNTIME_MANIFEST_PATH, or run "
            "`verifysignal core setup --core-cmd <path>`."
        ),
    )


def _entitlement_free_discover_from_cache(
    project: Path,
    platform: str,
    attempts: list[RuntimeSourceAttempt],
    api_status: RuntimeApiStatus,
    api_base_url: str,
) -> ManagedRuntimeReadinessResult | None:
    """Resolve a cached managed Core for entitlement-free `discover`.

    Returns a ready result ONLY when a compatible Core is already cached AND advertises
    verifysignal.discover/v1 (`core_supports_discover`). Returns None — so the caller falls through
    to the normal entitlement-gated path — when there is no usable cache or the cached Core does not
    advertise discover, so protected operations and non-discover Cores keep blocking without a receipt.
    """
    entry = load_cache_entry(
        platform=platform,
        api_base_url=api_base_url,
    )
    if not entry:
        return None
    try:
        compatibility = CoreAdapter(executable=entry.runtimeCommand, cwd=project).check_compatibility()
    except Exception:
        return None
    if not compatibility.compatible or not core_supports_discover(compatibility.raw or {}):
        return None
    mark_cache_used(entry, api_base_url=api_base_url)
    attempts.append(
        RuntimeSourceAttempt(
            source="managed-cache",
            status="compatible",
            terminal=True,
            command=entry.runtimeCommand,
            platform=platform,
            runtimeVersion=compatibility.verifysignalVersion,
            contractVersion=compatibility.contractVersion,
            message="Entitlement-free discover: cached Core advertises verifysignal.discover/v1.",
        )
    )
    return ManagedRuntimeReadinessResult(
        status="ready",
        source="managed-cache",
        runtimeCommand=entry.runtimeCommand,
        runtimeVersion=compatibility.verifysignalVersion or entry.coreVersion,
        contractVersion=compatibility.contractVersion or entry.contractVersion,
        attempts=attempts,
        api=api_status,
        entitlement=RuntimeEntitlementStatus(status="not-required"),
        cache=RuntimeCacheStatus(status="hit", platform=platform, coreVersion=entry.coreVersion),
        verificationKeys=RuntimeVerificationKeyStatus(status="not-required", source="not-required"),
        message="VerifySignal runtime is ready (entitlement-free discover).",
        nextAction="Continue with discover grounding.",
    )


def ensure_core_runtime(
    project: Path,
    *,
    explicit_core_cmd: str | None = None,
    api_base_url: str | None = None,
    email: str | None = None,
    token: str | None = None,
    integration: str | None = None,
    context: str = "runtime",
    required_capability: str | None = None,
) -> ManagedRuntimeReadinessResult:
    project = project.resolve()
    config = resolve_entitlement_config(api_base_url=api_base_url, workspace_api_base_url=get_entitlement_api_base_url(project))
    api_status = RuntimeApiStatus(baseUrl=config.apiBaseUrl, source=config.source, status="not-checked")
    attempts: list[RuntimeSourceAttempt] = []
    # Capability negotiation applies to EVERY source, not just the entitlement-free managed-cache path.
    # Callers may pass a CONDITIONAL requirement (e.g. run-record only when --record was requested);
    # otherwise it derives from the context registry.
    required_capability = required_capability or CONTEXT_REQUIRED_CAPABILITY.get(context)
    for source, command in _override_candidates(project, explicit_core_cmd):
        attempt = _verify_command(project, source, command, required_capability=required_capability)
        attempts.append(attempt)
        if attempt.status == "compatible":
            entitlement, entitlement_checked_api = _override_entitlement_status(
                config,
                email=email,
                token=token,
                integration=integration,
                context=context,
            )
            if entitlement:
                if entitlement_checked_api and not (entitlement.blockerCode or "").startswith("api."):
                    api_status.status = "reachable"
                if entitlement.status != "valid":
                    code = entitlement.blockerCode or _entitlement_blocker_code(entitlement.status)
                    blocker = RuntimeSetupBlocker(
                        code=code,
                        message=entitlement.message or "Email unlock token is required before protected VerifySignal Core operations.",
                        recoveryCommand="Run `verifysignal init --here --integration codex` and enter the email unlock token, or provide a valid entitlement receipt.",
                    )
                    if code.startswith("api."):
                        api_status.status = "unreachable"
                    result = ManagedRuntimeReadinessResult.blocked(
                        blocker,
                        attempts=attempts,
                        entitlement=entitlement,
                        cache=RuntimeCacheStatus(status="not-checked"),
                        message=blocker.message,
                    )
                    result.api = api_status
                    return result
                verification_keys, key_blocker = prepare_verification_keys(config, entitlement)
                if key_blocker:
                    if key_blocker.code == "entitlement.keys-unavailable":
                        api_status.status = "unreachable"
                    result = ManagedRuntimeReadinessResult.blocked(
                        key_blocker,
                        attempts=attempts,
                        entitlement=entitlement,
                        cache=RuntimeCacheStatus(status="not-checked"),
                        verification_keys=verification_keys,
                        message=key_blocker.message,
                    )
                    result.api = api_status
                    return result
            else:
                verification_keys = RuntimeVerificationKeyStatus(status="not-required", source="not-required")
            return ManagedRuntimeReadinessResult(
                status="ready",
                source=source,  # type: ignore[arg-type]
                runtimeCommand=command,
                runtimeVersion=attempt.runtimeVersion,
                contractVersion=attempt.contractVersion or PUBLIC_CONTRACT_VERSION,
                attempts=attempts,
                api=api_status,
                entitlement=entitlement or RuntimeEntitlementStatus(status="not-required"),
                cache=RuntimeCacheStatus(status="not-checked"),
                verificationKeys=verification_keys,
                message="VerifySignal runtime is ready.",
                nextAction="Continue with validation or run.",
            )
        if attempt.terminal:
            return _blocked_from_attempt(attempt, attempts)

    platform = normalize_platform()
    if not platform:
        blocker = RuntimeSetupBlocker(code="platform.unsupported", message="This host platform is not supported by managed VerifySignal runtime distribution.")
        attempts.append(RuntimeSourceAttempt(source="managed-cache", status="skipped", terminal=False, blockerCode=blocker.code, message=blocker.message))
        result = ManagedRuntimeReadinessResult.blocked(blocker, attempts=attempts, cache=RuntimeCacheStatus(status="not-checked"), message=blocker.message)
        result.api = api_status
        return result

    # `discover` is Core's entitlement-free grounding operation. If a compatible managed Core is
    # already cached AND advertises verifysignal.discover/v1, resolve it WITHOUT an entitlement — a
    # receipt gates paid operations and the managed download, not grounding against a Core the user
    # already has. Protected contexts and non-discover Cores fall through to the gate below.
    if context == "discover":
        discover_ready = _entitlement_free_discover_from_cache(
            project,
            platform,
            attempts,
            api_status,
            config.apiBaseUrl,
        )
        if discover_ready is not None:
            return discover_ready

    entitlement = ensure_entitlement(
        config=config,
        email=email,
        token=token,
        request_delivery=context == "init",
        integration=integration,
    )
    if entitlement.status != "valid":
        code = entitlement.blockerCode or _entitlement_blocker_code(entitlement.status)
        blocker = RuntimeSetupBlocker(
            code=code,
            message=entitlement.message or "Email unlock token is required before managed runtime download.",
            recoveryCommand="Run `verifysignal init --here --integration codex` and enter the email unlock token, or use `verifysignal core setup --core-cmd <path>`.",
        )
        attempts.append(RuntimeSourceAttempt(source="managed-download", status="blocked", terminal=True, platform=platform, message=blocker.message, blockerCode=code))
        api_status.status = "unreachable" if code.startswith("api.") else "reachable"
        result = ManagedRuntimeReadinessResult.blocked(
            blocker,
            attempts=attempts,
            entitlement=entitlement,
            cache=RuntimeCacheStatus(status="miss", platform=platform),
        )
        result.api = api_status
        return result
    api_status.status = "reachable"
    verification_keys, key_blocker = prepare_verification_keys(config, entitlement)
    if key_blocker:
        if key_blocker.code == "entitlement.keys-unavailable":
            api_status.status = "unreachable"
        attempts.append(RuntimeSourceAttempt(source="managed-download", status="blocked", terminal=True, platform=platform, message=key_blocker.message, blockerCode=key_blocker.code))
        result = ManagedRuntimeReadinessResult.blocked(
            key_blocker,
            attempts=attempts,
            entitlement=entitlement,
            cache=RuntimeCacheStatus(status="miss", platform=platform),
            verification_keys=verification_keys,
        )
        result.api = api_status
        return result
    entry = load_cache_entry(
        platform=platform,
        api_base_url=config.apiBaseUrl,
    )
    if entry:
        if entry.entitlementReceiptId and entitlement.receiptId and entry.entitlementReceiptId != entitlement.receiptId:
            attempts.append(
                RuntimeSourceAttempt(
                    source="managed-cache",
                    status="blocked",
                    terminal=False,
                    command=entry.runtimeCommand,
                    platform=platform,
                    message="Cached runtime is linked to a different entitlement receipt.",
                    blockerCode="entitlement.rejected",
                )
            )
        else:
            attempt = _verify_command(project, "managed-cache", entry.runtimeCommand, platform=platform, required_capability=required_capability)
            attempts.append(attempt)
            if attempt.status == "compatible":
                mark_cache_used(
                    entry,
                    api_base_url=config.apiBaseUrl,
                )
                return ManagedRuntimeReadinessResult(
                    status="ready",
                    source="managed-cache",
                    runtimeCommand=entry.runtimeCommand,
                    runtimeVersion=attempt.runtimeVersion or entry.coreVersion,
                    contractVersion=attempt.contractVersion or entry.contractVersion,
                    attempts=attempts,
                    api=api_status,
                    entitlement=entitlement,
                    cache=RuntimeCacheStatus(status="hit", platform=platform, coreVersion=entry.coreVersion),
                    verificationKeys=verification_keys,
                    message="VerifySignal runtime is ready.",
                    nextAction="Continue with validation or run.",
                )
            attempts[-1] = RuntimeSourceAttempt(
                source="managed-cache",
                status="incompatible",
                terminal=False,
                command=entry.runtimeCommand,
                platform=platform,
                message=attempt.message,
                blockerCode="core.incompatible",
            )

    manifest, manifest_blocker = load_manifest()
    if manifest_blocker and manifest_blocker.code != "distribution.unavailable":
        attempts.append(RuntimeSourceAttempt(source="managed-download", status="blocked", terminal=True, platform=platform, message=manifest_blocker.message, blockerCode=manifest_blocker.code))
        result = ManagedRuntimeReadinessResult.blocked(
            manifest_blocker,
            attempts=attempts,
            entitlement=entitlement,
            cache=RuntimeCacheStatus(status="miss", platform=platform),
            verification_keys=verification_keys,
        )
        result.api = api_status
        return result
    if manifest:
        try:
            selected = select_manifest_entry(manifest_entries(manifest or {}), platform=platform, contract_version=PUBLIC_CONTRACT_VERSION)
        except Exception:
            blocker = RuntimeSetupBlocker(code="manifest.invalid", message="Managed runtime manifest does not contain a compatible entry for this platform and contract.")
            attempts.append(RuntimeSourceAttempt(source="managed-download", status="blocked", terminal=True, platform=platform, message=blocker.message, blockerCode=blocker.code))
            result = ManagedRuntimeReadinessResult.blocked(blocker, attempts=attempts, entitlement=entitlement, cache=RuntimeCacheStatus(status="miss", platform=platform))
            result.verificationKeys = verification_keys
            result.api = api_status
            return result
        runtime_core_version = str(selected.get("coreVersion"))
        runtime_command, blocker = install_from_manifest(
            selected,
            entitlement_receipt_id=entitlement.receiptId,
            api_base_url=config.apiBaseUrl,
        )
    else:
        receipt = load_receipt(config.apiBaseUrl)
        if not receipt:
            blocker = RuntimeSetupBlocker(code="entitlement.malformed", message="Entitlement receipt file is unavailable after unlock.")
            attempts.append(RuntimeSourceAttempt(source="managed-download", status="blocked", terminal=True, platform=platform, message=blocker.message, blockerCode=blocker.code))
            result = ManagedRuntimeReadinessResult.blocked(blocker, attempts=attempts, entitlement=entitlement, cache=RuntimeCacheStatus(status="miss", platform=platform))
            result.verificationKeys = verification_keys
            result.api = api_status
            return result
        distribution_client = RuntimeDistributionClient(config)
        requested_version, version_blocker = resolve_requested_core_version(project)
        if not requested_version:
            # No local pin, so ASK. This is the whole first-run path: a fresh machine has no env pin
            # and no persisted version (the only writer of that reads it off an installed Core), so
            # without this the managed download dead-ends on `distribution.version-unspecified` — and
            # every recovery it suggested required already having what the download provides.
            # An explicit pin still wins: this only runs when nothing local answered.
            requested_version, version_blocker = distribution_client.resolve_latest_core_version(platform, receipt)
        if version_blocker or not requested_version:
            # Carry the ORIGINATING blocker. This used to rebuild `distribution.version-unspecified`
            # without a recoveryCommand, so the same code surfaced two different recovery strings
            # depending on which branch produced it.
            version_blocker = version_blocker or RuntimeSetupBlocker(
                code="distribution.version-unspecified",
                message="No VerifySignal Core version could be resolved for managed runtime download.",
                recoveryCommand=(
                    "Set VERIFYSIGNAL_CORE_VERSION=<version>, configure "
                    "VERIFYSIGNAL_RUNTIME_MANIFEST_PATH, or run "
                    "`verifysignal core setup --core-cmd <path>`."
                ),
            )
            attempts.append(RuntimeSourceAttempt(source="managed-download", status="blocked", terminal=True, platform=platform, message=version_blocker.message, blockerCode=version_blocker.code))
            result = ManagedRuntimeReadinessResult.blocked(version_blocker, attempts=attempts, entitlement=entitlement, cache=RuntimeCacheStatus(status="miss", platform=platform))
            result.verificationKeys = verification_keys
            result.api = api_status
            return result
        grant = distribution_client.authorize_runtime_download(requested_version, platform, receipt)
        if grant.blocker:
            attempts.append(RuntimeSourceAttempt(source="managed-download", status="blocked", terminal=True, platform=platform, message=grant.blocker.message, blockerCode=grant.blocker.code))
            result = ManagedRuntimeReadinessResult.blocked(grant.blocker, attempts=attempts, entitlement=entitlement, cache=RuntimeCacheStatus(status="miss", platform=platform), verification_keys=verification_keys)
            result.api = api_status
            return result
        runtime_core_version = str(grant.data.get("coreVersion", requested_version))
        runtime_command, blocker = install_from_authorization(
            grant.data,
            entitlement_receipt_id=entitlement.receiptId,
            api_base_url=config.apiBaseUrl,
        )
    if blocker or not runtime_command:
        actual = blocker or RuntimeSetupBlocker(code="distribution.unavailable", message="Managed runtime installation failed.")
        attempts.append(RuntimeSourceAttempt(source="managed-download", status="blocked", terminal=True, platform=platform, message=actual.message, blockerCode=actual.code))
        result = ManagedRuntimeReadinessResult.blocked(actual, attempts=attempts, entitlement=entitlement, cache=RuntimeCacheStatus(status="miss", platform=platform), verification_keys=verification_keys)
        result.api = api_status
        return result
    attempt = _verify_command(project, "managed-download", runtime_command, platform=platform, required_capability=required_capability)
    attempts.append(attempt)
    if attempt.status == "compatible":
        return ManagedRuntimeReadinessResult(
            status="ready",
            source="managed-download",
            runtimeCommand=runtime_command,
            runtimeVersion=attempt.runtimeVersion or runtime_core_version,
            contractVersion=attempt.contractVersion or PUBLIC_CONTRACT_VERSION,
            attempts=attempts,
            api=api_status,
            entitlement=entitlement,
            cache=RuntimeCacheStatus(status="hit", platform=platform, coreVersion=runtime_core_version),
            verificationKeys=verification_keys,
            message="VerifySignal runtime is ready.",
            nextAction="Continue with validation or run.",
        )
    result = _blocked_from_attempt(attempt, attempts, entitlement=entitlement, cache=RuntimeCacheStatus(status="incompatible", platform=platform))
    result.verificationKeys = verification_keys
    result.api = api_status
    return result


def _override_candidates(project: Path, explicit_core_cmd: str | None) -> list[tuple[str, str]]:
    candidates: list[tuple[str, str]] = []
    if explicit_core_cmd:
        candidates.append(("explicit", explicit_core_cmd))
    workspace_cmd = get_core_command(project)
    if workspace_cmd:
        candidates.append(("workspace", workspace_cmd))
    env_cmd = os.environ.get("VERIFYSIGNAL_CORE_CMD")
    if env_cmd:
        candidates.append(("env", env_cmd))
    path_core = shutil.which("verifysignal-core")
    if path_core:
        candidates.append(("path", path_core))
    for path in _ancestor_sibling_paths(project):
        candidates.append(("ancestor-sibling", str(path)))
    return candidates


def _ancestor_sibling_paths(project: Path) -> list[Path]:
    paths: list[Path] = []
    seen: set[Path] = set()
    start = project.resolve()
    for node in [start, *start.parents]:
        sibling = (node.parent / "verifysignal").resolve()
        if sibling == start or sibling in seen:
            continue
        seen.add(sibling)
        if sibling.exists():
            paths.append(sibling)
    return paths


def _override_entitlement_status(
    config,
    *,
    email: str | None,
    token: str | None,
    integration: str | None,
    context: str,
) -> tuple[RuntimeEntitlementStatus | None, bool]:
    token_available = bool(token or os.environ.get("VERIFYSIGNAL_EMAIL_UNLOCK_TOKEN"))
    email_available = bool(email or os.environ.get("VERIFYSIGNAL_EMAIL"))
    receipt_available = load_receipt(config.apiBaseUrl) is not None
    should_resolve = token_available or receipt_available or (context == "init" and email_available)
    if not should_resolve:
        return None, False
    return (
        ensure_entitlement(
            config=config,
            email=email,
            token=token,
            request_delivery=context == "init",
            integration=integration,
        ),
        token_available or (context == "init" and email_available),
    )


def _verify_command(
    project: Path, source: str, command: str, *, platform: str | None = None, required_capability: str | None = None
) -> RuntimeSourceAttempt:
    """Verify a candidate Core command.

    `required_capability` makes capability negotiation part of the SINGLE gate every ready-returning
    path crosses. Previously only the entitlement-free managed-cache branch consulted
    `core_supports_discover`, so a compatible Core WITHOUT verifysignal.discover/v1 reached via the
    explicit/workspace/env/PATH override, the valid-cache path, or a managed download resolved `ready`
    and only then failed inside Core on an unknown `discover` subcommand. Requiring it here closes
    every source at once rather than patching them one by one, and taking the probe from
    OPTIONAL_CAPABILITY_PROBES closes every optional OPERATION the same way.
    """
    terminal = source in {"explicit", "workspace", "env"}
    try:
        compatibility = CoreAdapter(executable=command, cwd=project).check_compatibility()
    except CoreMissingError as exc:
        return RuntimeSourceAttempt(source=source, status="missing", terminal=terminal, command=command, platform=platform, message=str(exc), blockerCode="core.missing")
    except CoreExecutionError as exc:
        return RuntimeSourceAttempt(source=source, status="error", terminal=terminal, command=command, platform=platform, message=str(exc), blockerCode="core.incompatible")
    except Exception as exc:
        return RuntimeSourceAttempt(source=source, status="error", terminal=terminal, command=command, platform=platform, message=str(exc), blockerCode="core.incompatible")
    if compatibility.compatible and required_capability:
        supports = OPTIONAL_CAPABILITY_PROBES[required_capability]
        if not supports(compatibility.raw or {}):
            return RuntimeSourceAttempt(
                source=source,
                status="incompatible",
                terminal=terminal,
                command=command,
                platform=platform,
                runtimeVersion=compatibility.verifysignalVersion,
                contractVersion=compatibility.contractVersion,
                message=(
                    f"This Core is compatible but does not advertise verifysignal.{required_capability}/v1, "
                    f"so it cannot serve `{required_capability}`."
                ),
                blockerCode=capability_blocker_code(required_capability),
            )
    if compatibility.compatible:
        return RuntimeSourceAttempt(
            source=source,
            status="compatible",
            terminal=True,
            command=command,
            platform=platform,
            runtimeVersion=compatibility.verifysignalVersion,
            contractVersion=compatibility.contractVersion,
            message="Core command verified through public CLI contract.",
        )
    return RuntimeSourceAttempt(
        source=source,
        status="incompatible",
        terminal=terminal,
        command=command,
        platform=platform,
        runtimeVersion=compatibility.verifysignalVersion,
        contractVersion=compatibility.contractVersion,
        message=compatibility.message,
        blockerCode="core.incompatible",
    )


def _blocked_from_attempt(
    attempt: RuntimeSourceAttempt,
    attempts: list[RuntimeSourceAttempt],
    *,
    entitlement: RuntimeEntitlementStatus | None = None,
    cache: RuntimeCacheStatus | None = None,
) -> ManagedRuntimeReadinessResult:
    # Preserve the attempt's own blocker code instead of flattening every non-missing attempt to
    # `core.incompatible` (behaviour-identical for the pre-existing codes, which already set it).
    code = attempt.blockerCode or ("core.missing" if attempt.status == "missing" else "core.incompatible")
    if code in CAPABILITY_BLOCKER_CODES:
        # A capability gap is not a version incompatibility: the Core is fine, it just cannot serve
        # this operation — so the request is BLOCKED, matching every other capability block.
        status = "blocked"
    else:
        status = "incompatible" if attempt.status == "incompatible" else ("blocked" if attempt.status == "missing" else "error")
    blocker = RuntimeSetupBlocker(
        code=code,
        message=attempt.message or "Configured VerifySignal runtime is incompatible.",
        recoveryCommand="verifysignal core setup --json" if code == "core.missing" else "verifysignal core setup --core-cmd <path>",
    )
    return ManagedRuntimeReadinessResult(
        status=status,  # type: ignore[arg-type]
        source="none",
        runtimeCommand=attempt.command,
        runtimeVersion=attempt.runtimeVersion,
        contractVersion=attempt.contractVersion or PUBLIC_CONTRACT_VERSION,
        attempts=attempts,
        entitlement=entitlement or RuntimeEntitlementStatus(status="not-checked"),
        cache=cache or RuntimeCacheStatus(status="not-checked"),
        blockers=[blocker],
        message=blocker.message,
        nextAction=blocker.recoveryCommand or "Resolve Core compatibility.",
    )


def _entitlement_blocker_code(status: str) -> str:
    mapping = {
        "required": "entitlement.unlock-required",
        "expired": "entitlement.expired",
        "revoked": "entitlement.revoked",
        "rejected": "entitlement.rejected",
        "malformed": "entitlement.rejected",
        "unverifiable": "entitlement.rejected",
    }
    return mapping.get(status, "entitlement.rejected")
