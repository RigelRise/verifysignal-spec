"""Host-agent MCP-server configuration.

VerifySignal ships zero inference; the host agent (e.g. Claude Code) is the brain. To make live
authoring frictionless, integrations register the managed server in agent user scope through the
host's public CLI and retain a project-scoped entry as a compatibility fallback.

The merge is SAFE by construction: it preserves the user's other servers, is idempotent, and never
clobbers a file it cannot parse. A differing user-scoped or project-scoped entry is user-owned and
is never overwritten.
"""

from __future__ import annotations

import json
import os
import signal
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, MutableMapping
from pathlib import Path
from typing import Any

import tomlkit
from tomlkit.exceptions import ParseError

from verifysignal_spec.process import popen_text, run_text
from verifysignal_spec.workspace.repository import save_document

# Exact legacy entry emitted through 0.21.0 and the first 0.21.1 parity draft.
LEGACY_PLAYWRIGHT_MCP_SERVER: dict[str, Any] = {
    "type": "stdio",
    "command": "npx",
    "args": ["-y", "@playwright/mcp@latest"],
}
PLAYWRIGHT_MCP_VERSION = "0.0.78"
PLAYWRIGHT_MCP_PACKAGE = f"@playwright/mcp@{PLAYWRIGHT_MCP_VERSION}"
PLAYWRIGHT_MCP_CACHE_ENV = "VERIFYSIGNAL_PLAYWRIGHT_MCP_CACHE_DIR"
PLAYWRIGHT_MCP_SETUP_COMMAND = (
    "verifysignal integration setup-playwright-mcp --json"
)
AGENT_MCP_AUTO_REGISTER_ENV = (
    "VERIFYSIGNAL_AGENT_MCP_AUTO_REGISTER"
)
PLAYWRIGHT_MCP_SERVER_NAME = "playwright"

# Canonical managed entry. The launcher keeps provider artifacts outside the
# target project while remaining a host-owned MCP authoring aid.
PLAYWRIGHT_MCP_SERVER: dict[str, Any] = {
    "type": "stdio",
    "command": "verifysignal",
    "args": ["integration", "playwright-mcp"],
}

# Codex can make a project-scoped server a startup requirement. This turns a
# missing browser backend into an explicit session-start failure instead of a
# later browser-first run with an empty tool inventory. Claude's JSON contract
# intentionally keeps the shared entry unchanged.
CODEX_PLAYWRIGHT_MCP_SERVER: dict[str, Any] = {
    "command": "verifysignal",
    "args": ["integration", "playwright-mcp"],
    "required": True,
}

AgentCommandRunner = Callable[
    ...,
    subprocess.CompletedProcess[str],
]


def managed_playwright_mcp_server(
    *,
    required: bool = False,
) -> dict[str, Any]:
    """Return the managed server with any explicit cache override pinned.

    Agent hosts do not guarantee that their MCP child processes inherit the
    shell environment. When setup uses a non-default cache, persist that one
    non-sensitive path in the MCP definition so the launcher can find the
    provider after the agent starts.
    """

    server = dict(
        CODEX_PLAYWRIGHT_MCP_SERVER
        if required
        else PLAYWRIGHT_MCP_SERVER
    )
    override = os.environ.get(PLAYWRIGHT_MCP_CACHE_ENV)
    if override:
        server["env"] = {
            PLAYWRIGHT_MCP_CACHE_ENV: str(
                Path(override).expanduser().resolve()
            )
        }
    return server


def register_agent_user_mcp(
    integration_key: str,
    *,
    agent_command: str | None = None,
    command_runner: AgentCommandRunner = run_text,
    timeout_seconds: float = 30,
) -> dict[str, Any]:
    """Register the managed Playwright server through the host's public CLI.

    Agent commands run from a private empty directory so project-scoped MCP
    configuration cannot be mistaken for the required user-scoped entry.
    Existing differing entries are user-owned and are never overwritten.
    """

    if integration_key not in {"codex", "claude"}:
        raise ValueError(
            f"Unsupported MCP user registration integration: "
            f"{integration_key}"
        )
    executable_name = "codex" if integration_key == "codex" else "claude"
    executable = agent_command or shutil.which(executable_name)
    status = _agent_user_mcp_status(integration_key, executable)
    if not executable:
        status.update(
            {
                "status": "blocked",
                "code": "agent.command-missing",
                "message": (
                    f"{_agent_display_name(integration_key)} is not "
                    "installed or is not available on PATH."
                ),
                "nextAction": (
                    f"Install {_agent_display_name(integration_key)} and "
                    "rerun the same command."
                ),
            }
        )
        return status

    with tempfile.TemporaryDirectory(
        prefix="verifysignal-agent-mcp-"
    ) as temporary:
        inspection = _inspect_agent_user_mcp(
            integration_key,
            executable,
            command_runner=command_runner,
            cwd=Path(temporary),
            timeout_seconds=timeout_seconds,
        )
        if inspection["state"] == "managed":
            status.update(
                {
                    "status": "ready",
                    "managedServers": [PLAYWRIGHT_MCP_SERVER_NAME],
                    "unchanged": True,
                    "nextAction": None,
                }
            )
            return status
        if inspection["state"] == "conflict":
            status.update(
                {
                    "status": "blocked",
                    "code": "agent-mcp.conflict",
                    "preserved": [PLAYWRIGHT_MCP_SERVER_NAME],
                    "message": (
                        "The existing user-scoped Playwright MCP server is "
                        "user-owned and differs from the VerifySignal "
                        "managed launcher."
                    ),
                    "nextAction": (
                        "Review the existing user-scoped MCP server named "
                        "'playwright', then rerun the same command."
                    ),
                }
            )
            return status
        if inspection["state"] == "error":
            status.update(
                {
                    "status": "blocked",
                    "code": "agent-mcp.inspect-failed",
                    "message": (
                        f"{_agent_display_name(integration_key)} could not "
                        "inspect its user MCP configuration."
                    ),
                    "nextAction": (
                        f"Run `{executable_name} mcp list`, resolve the "
                        "reported agent configuration error, and rerun the "
                        "same command."
                    ),
                }
            )
            return status

        add_command = _agent_mcp_add_command(
            integration_key,
            executable,
        )
        added = _run_agent_command(
            add_command,
            command_runner=command_runner,
            cwd=Path(temporary),
            timeout_seconds=timeout_seconds,
        )
        if added is None or added.returncode != 0:
            status.update(
                {
                    "status": "blocked",
                    "code": "agent-mcp.registration-failed",
                    "message": (
                        f"{_agent_display_name(integration_key)} could not "
                        "register the managed Playwright MCP server in user "
                        "scope."
                    ),
                    "nextAction": (
                        "Resolve the agent MCP configuration error and rerun "
                        "the same command."
                    ),
                }
            )
            return status

        verified = _inspect_agent_user_mcp(
            integration_key,
            executable,
            command_runner=command_runner,
            cwd=Path(temporary),
            timeout_seconds=timeout_seconds,
        )
        if verified["state"] != "managed":
            status.update(
                {
                    "status": "blocked",
                    "code": "agent-mcp.verification-failed",
                    "message": (
                        "The agent accepted the MCP registration command but "
                        "did not expose the expected user-scoped managed "
                        "entry."
                    ),
                    "nextAction": (
                        f"Run `{executable_name} mcp get playwright`, "
                        "resolve the reported configuration, and rerun the "
                        "same command."
                    ),
                }
            )
            return status

    status.update(
        {
            "status": "ready",
            "added": [PLAYWRIGHT_MCP_SERVER_NAME],
            "managedServers": [PLAYWRIGHT_MCP_SERVER_NAME],
            "nextAction": None,
        }
    )
    return status


def _agent_user_mcp_status(
    integration_key: str,
    executable: str | None,
) -> dict[str, Any]:
    return {
        "status": "pending",
        "scope": "user",
        "integrationKey": integration_key,
        "serverName": PLAYWRIGHT_MCP_SERVER_NAME,
        "agentCommand": executable,
        "added": [],
        "preserved": [],
        "managedServers": [],
        "unchanged": False,
        "nextAction": None,
    }


def _agent_display_name(integration_key: str) -> str:
    return "Codex" if integration_key == "codex" else "Claude Code"


def _agent_mcp_get_command(
    integration_key: str,
    executable: str,
) -> list[str]:
    command = [
        executable,
        "mcp",
        "get",
        PLAYWRIGHT_MCP_SERVER_NAME,
    ]
    if integration_key == "codex":
        command.append("--json")
    return command


def _agent_mcp_add_command(
    integration_key: str,
    executable: str,
) -> list[str]:
    command = [executable, "mcp", "add"]
    if integration_key == "claude":
        command.extend(["--scope", "user"])
    cache_override = os.environ.get(PLAYWRIGHT_MCP_CACHE_ENV)
    cache_environment = (
        f"{PLAYWRIGHT_MCP_CACHE_ENV}="
        f"{Path(cache_override).expanduser().resolve()}"
        if cache_override
        else None
    )
    if integration_key == "claude":
        command.append(PLAYWRIGHT_MCP_SERVER_NAME)
    if cache_environment:
        command.extend(["--env", cache_environment])
    if integration_key == "codex":
        command.append(PLAYWRIGHT_MCP_SERVER_NAME)
    command.extend(
        [
            "--",
            "verifysignal",
            "integration",
            "playwright-mcp",
        ]
    )
    return command


def _run_agent_command(
    command: list[str],
    *,
    command_runner: AgentCommandRunner,
    cwd: Path,
    timeout_seconds: float,
) -> subprocess.CompletedProcess[str] | None:
    try:
        return command_runner(
            command,
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def _inspect_agent_user_mcp(
    integration_key: str,
    executable: str,
    *,
    command_runner: AgentCommandRunner,
    cwd: Path,
    timeout_seconds: float,
) -> dict[str, str]:
    completed = _run_agent_command(
        _agent_mcp_get_command(integration_key, executable),
        command_runner=command_runner,
        cwd=cwd,
        timeout_seconds=timeout_seconds,
    )
    if completed is None:
        return {"state": "error"}
    if completed.returncode != 0:
        combined = f"{completed.stdout}\n{completed.stderr}".lower()
        if (
            "no mcp server named" in combined
            or "not found" in combined
        ):
            return {"state": "missing"}
        return {"state": "error"}
    if integration_key == "codex":
        return {
            "state": (
                "managed"
                if _codex_user_mcp_is_managed(completed.stdout)
                else "conflict"
            )
        }
    return {
        "state": (
            "managed"
            if _claude_user_mcp_is_managed(completed.stdout)
            else "conflict"
        )
    }


def _codex_user_mcp_is_managed(raw: str) -> bool:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return False
    if not isinstance(payload, dict):
        return False
    transport = payload.get("transport")
    return (
        payload.get("name") == PLAYWRIGHT_MCP_SERVER_NAME
        and isinstance(transport, dict)
        and transport.get("type") == "stdio"
        and transport.get("command") == "verifysignal"
        and transport.get("args")
        == ["integration", "playwright-mcp"]
    )


def _claude_user_mcp_is_managed(raw: str) -> bool:
    fields: dict[str, str] = {}
    for line in raw.splitlines():
        stripped = line.strip()
        if ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        fields[key.strip().lower()] = value.strip()
    return (
        fields.get("scope", "").lower().startswith("user")
        and fields.get("type", "").lower() == "stdio"
        and fields.get("command") == "verifysignal"
        and fields.get("args") == "integration playwright-mcp"
    )


def node_available() -> bool:
    """True when Node's package installer is available for MCP setup."""
    return shutil.which("npm") is not None


def playwright_mcp_cache_root(
    cache_root: Path | str | None = None,
) -> Path:
    """Return the user-owned cache for the pinned Playwright MCP provider."""

    if cache_root is not None:
        return Path(cache_root).expanduser().resolve()
    override = os.environ.get(PLAYWRIGHT_MCP_CACHE_ENV)
    if override:
        return Path(override).expanduser().resolve()
    return (
        Path.home()
        / ".cache"
        / "verifysignal"
        / "playwright-mcp"
    ).resolve()


def _playwright_mcp_install_dir(
    cache_root: Path | str | None = None,
) -> Path:
    return playwright_mcp_cache_root(cache_root) / PLAYWRIGHT_MCP_VERSION


def _playwright_mcp_executable(install_dir: Path) -> Path:
    suffix = ".cmd" if sys.platform == "win32" else ""
    return (
        install_dir
        / "node_modules"
        / ".bin"
        / f"playwright-mcp{suffix}"
    )


def _installed_playwright_mcp_runtime(
    cache_root: Path | str | None = None,
    *,
    source: str = "managed-cache",
) -> dict[str, Any] | None:
    install_dir = _playwright_mcp_install_dir(cache_root)
    package_json = (
        install_dir
        / "node_modules"
        / "@playwright"
        / "mcp"
        / "package.json"
    )
    executable = _playwright_mcp_executable(install_dir)
    try:
        package = json.loads(package_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if (
        not isinstance(package, dict)
        or package.get("name") != "@playwright/mcp"
        or package.get("version") != PLAYWRIGHT_MCP_VERSION
        or not executable.is_file()
        or (
            sys.platform != "win32"
            and not os.access(executable, os.X_OK)
        )
    ):
        return None
    return {
        "status": "ready",
        "source": source,
        "package": PLAYWRIGHT_MCP_PACKAGE,
        "version": PLAYWRIGHT_MCP_VERSION,
        "cachePath": str(install_dir),
        "executable": str(executable),
        "offlineReady": True,
        "nextAction": None,
    }


def _blocked_playwright_mcp_runtime(
    message: str,
    *,
    source: str,
    cache_root: Path | str | None = None,
) -> dict[str, Any]:
    return {
        "status": "blocked",
        "source": source,
        "package": PLAYWRIGHT_MCP_PACKAGE,
        "version": PLAYWRIGHT_MCP_VERSION,
        "cachePath": str(_playwright_mcp_install_dir(cache_root)),
        "executable": None,
        "offlineReady": False,
        "message": message,
        "nextAction": PLAYWRIGHT_MCP_SETUP_COMMAND,
    }


def _verify_playwright_mcp_handshake(
    executable: Path | str,
    *,
    timeout_seconds: float = 10,
) -> bool:
    requests = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {
                    "name": "verifysignal-setup",
                    "version": "1",
                },
            },
        },
        {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
        },
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {},
        },
    ]
    payload = "".join(json.dumps(item) + "\n" for item in requests)
    with tempfile.TemporaryDirectory(
        prefix="verifysignal-playwright-mcp-check-"
    ) as temporary:
        temporary_path = Path(temporary)
        os.chmod(temporary_path, 0o700)
        output_dir = temporary_path / ".playwright-mcp"
        output_dir.mkdir(mode=0o700)
        try:
            process = popen_text(
                [
                    str(executable),
                    "--isolated",
                    "--output-dir",
                    str(output_dir),
                ],
                cwd=temporary_path,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, _stderr = process.communicate(
                payload,
                timeout=timeout_seconds,
            )
        except (OSError, subprocess.TimeoutExpired):
            if "process" in locals() and process.poll() is None:
                process.kill()
                process.communicate()
            return False
    if process.returncode != 0:
        return False
    try:
        messages = [
            json.loads(line)
            for line in stdout.splitlines()
            if line.strip()
        ]
        initialize = next(
            item for item in messages if item.get("id") == 1
        )
        tools_list = next(
            item for item in messages if item.get("id") == 2
        )
        server_name = (
            initialize.get("result", {})
            .get("serverInfo", {})
            .get("name")
        )
        tools = {
            item.get("name")
            for item in tools_list.get("result", {}).get("tools", [])
            if isinstance(item, dict)
        }
    except (
        json.JSONDecodeError,
        StopIteration,
        AttributeError,
        TypeError,
    ):
        return False
    return server_name == "Playwright" and {
        "browser_navigate",
        "browser_snapshot",
    }.issubset(tools)


def ensure_playwright_mcp_runtime(
    *,
    npm_command: str | None = None,
    cache_root: Path | str | None = None,
    timeout_seconds: float = 180,
) -> dict[str, Any]:
    """Install the pinned provider ahead of agent startup.

    Codex starts MCP servers in a network-restricted process. Resolving an npm
    package from that process can hang until the MCP handshake deadline, so
    setup installs the exact provider into a stable user cache and the runtime
    launcher executes that cached binary directly.
    """

    installed = _installed_playwright_mcp_runtime(cache_root)
    if installed:
        if _verify_playwright_mcp_handshake(
            str(installed["executable"]),
        ):
            installed["handshakeVerified"] = True
            return installed
        return _blocked_playwright_mcp_runtime(
            "The cached Playwright MCP provider failed its stdio handshake.",
            source="cache-invalid",
            cache_root=cache_root,
        )

    npm = npm_command or shutil.which("npm")
    if not npm:
        return _blocked_playwright_mcp_runtime(
            "Playwright MCP setup requires Node/npm on PATH.",
            source="npm-missing",
            cache_root=cache_root,
        )

    root = playwright_mcp_cache_root(cache_root)
    try:
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(root, 0o700)
        staging = Path(
            tempfile.mkdtemp(
                prefix=f".{PLAYWRIGHT_MCP_VERSION}-",
                dir=root,
            )
        )
    except OSError:
        return _blocked_playwright_mcp_runtime(
            "Could not create the private Playwright MCP cache.",
            source="cache-error",
            cache_root=cache_root,
        )

    command = [
        npm,
        "install",
        "--prefix",
        str(staging),
        "--no-package-lock",
        "--no-save",
        "--ignore-scripts",
        "--no-audit",
        "--no-fund",
        PLAYWRIGHT_MCP_PACKAGE,
    ]
    try:
        completed = run_text(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
            check=False,
        )
        if completed.returncode != 0:
            return _blocked_playwright_mcp_runtime(
                "npm could not install the pinned Playwright MCP provider "
                f"(exit {completed.returncode}).",
                source="managed-install",
                cache_root=cache_root,
            )

        staged_package = (
            staging
            / "node_modules"
            / "@playwright"
            / "mcp"
            / "package.json"
        )
        staged_executable = _playwright_mcp_executable(staging)
        try:
            staged_metadata = json.loads(
                staged_package.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):
            staged_metadata = {}
        if (
            not isinstance(staged_metadata, dict)
            or staged_metadata.get("name") != "@playwright/mcp"
            or staged_metadata.get("version") != PLAYWRIGHT_MCP_VERSION
            or not staged_executable.is_file()
        ):
            return _blocked_playwright_mcp_runtime(
                "The installed Playwright MCP provider did not match the "
                "pinned package contract.",
                source="managed-install",
                cache_root=cache_root,
            )
        if not _verify_playwright_mcp_handshake(staged_executable):
            return _blocked_playwright_mcp_runtime(
                "The installed Playwright MCP provider failed its stdio "
                "handshake.",
                source="managed-install",
                cache_root=cache_root,
            )

        destination = _playwright_mcp_install_dir(cache_root)
        if destination.exists():
            concurrent = _installed_playwright_mcp_runtime(cache_root)
            if concurrent and _verify_playwright_mcp_handshake(
                str(concurrent["executable"])
            ):
                concurrent["handshakeVerified"] = True
                return concurrent
            return _blocked_playwright_mcp_runtime(
                "The managed Playwright MCP cache contains an invalid "
                "existing installation.",
                source="cache-invalid",
                cache_root=cache_root,
            )
        staging.replace(destination)
        installed = _installed_playwright_mcp_runtime(
            cache_root,
            source="managed-install",
        )
        if installed:
            installed["handshakeVerified"] = True
            return installed
        return _blocked_playwright_mcp_runtime(
            "The managed Playwright MCP installation could not be verified.",
            source="managed-install",
            cache_root=cache_root,
        )
    except subprocess.TimeoutExpired:
        return _blocked_playwright_mcp_runtime(
            "Timed out while installing the pinned Playwright MCP provider.",
            source="managed-install",
            cache_root=cache_root,
        )
    except OSError:
        return _blocked_playwright_mcp_runtime(
            "Could not start npm to install the Playwright MCP provider.",
            source="managed-install",
            cache_root=cache_root,
        )
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)


def run_playwright_mcp(
    *,
    provider_command: str | None = None,
    cache_root: Path | str | None = None,
) -> int:
    """Proxy the preinstalled Playwright MCP from a private workspace."""

    runtime = _installed_playwright_mcp_runtime(cache_root)
    executable = provider_command or (
        str(runtime["executable"]) if runtime else None
    )
    if not executable:
        print(
            "Playwright MCP runtime is not installed. Run "
            f"`{PLAYWRIGHT_MCP_SETUP_COMMAND}` before starting the agent.",
            file=sys.stderr,
        )
        return 78

    with tempfile.TemporaryDirectory(
        prefix="verifysignal-playwright-mcp-"
    ) as temporary:
        temporary_path = Path(temporary)
        os.chmod(temporary_path, 0o700)
        output_dir = temporary_path / ".playwright-mcp"
        output_dir.mkdir(mode=0o700)
        command = [
            executable,
            "--isolated",
            "--output-dir",
            str(output_dir),
        ]
        process = subprocess.Popen(command, cwd=temporary_path)
        previous_handlers: dict[signal.Signals, Any] = {}

        def forward(signum: int, _frame: Any) -> None:
            if process.poll() is None:
                process.send_signal(signum)

        for signum in (signal.SIGINT, signal.SIGTERM):
            try:
                previous_handlers[signum] = signal.getsignal(signum)
                signal.signal(signum, forward)
            except ValueError:
                # Signal handlers are only installed by the CLI's main thread.
                continue
        try:
            return_code = process.wait()
        except KeyboardInterrupt:
            if process.poll() is None:
                process.send_signal(signal.SIGINT)
            process.wait()
            return_code = 130
        finally:
            for signum, handler in previous_handlers.items():
                signal.signal(signum, handler)
            if process.poll() is None:
                process.terminate()
                process.wait()
        if return_code < 0:
            return 128 + abs(return_code)
        return return_code


def merge_mcp_servers(project: Path, servers: dict[str, Any]) -> dict[str, Any]:
    """Merge ``servers`` into ``<project>/.mcp.json`` under the ``mcpServers`` key.

    Preserves existing servers, only writes when something changed (idempotent), and skips (leaving
    the file untouched) when an existing ``.mcp.json`` is not safely mergeable. Returns a status dict.
    """

    path = project / ".mcp.json"
    status: dict[str, Any] = {
        "path": ".mcp.json",
        "integrationKey": "claude",
        "format": "claude-json",
        "added": [],
        "updated": [],
        "preserved": [],
        "managedServers": [],
        "unchanged": False,
        "skipped": False,
        "nodeAvailable": node_available(),
        "warnings": [],
    }

    existing: Any = {}
    if path.exists():
        # Parse strictly as JSON. If it is not valid JSON (or not an object), do NOT overwrite the
        # user's file — surface a skip so the caller can warn instead of destroying their config.
        try:
            existing = json.loads(path.read_text(encoding="utf-8") or "{}")
        except json.JSONDecodeError:
            status["skipped"] = True
            status["reason"] = "existing .mcp.json is not valid JSON; left untouched"
            return status
        if not isinstance(existing, dict):
            status["skipped"] = True
            status["reason"] = "existing .mcp.json is not a JSON object; left untouched"
            return status

    current_servers = existing.get("mcpServers", {})
    if not isinstance(current_servers, dict):
        status["skipped"] = True
        status["reason"] = "existing .mcp.json `mcpServers` is not an object; left untouched"
        return status

    merged = dict(current_servers)
    for name, spec in servers.items():
        if name not in merged:
            status["added"].append(name)
            merged[name] = spec
        elif _mcp_entry_matches(merged[name], spec):
            status["managedServers"].append(name)
            continue
        elif _mcp_entry_matches(
            merged[name], LEGACY_PLAYWRIGHT_MCP_SERVER
        ):
            status["updated"].append(name)
            merged[name] = spec
        else:
            status["preserved"].append(name)
            status["warnings"].append(
                f"Preserved user-owned MCP server '{name}' because it differs "
                "from the exact legacy VerifySignal entry."
            )
        if _mcp_entry_matches(merged.get(name), spec):
            status["managedServers"].append(name)
    status["preserved"].extend(
        name
        for name in current_servers
        if name not in servers and name not in status["preserved"]
    )

    if merged == current_servers:
        status["unchanged"] = True
        return status

    new_doc = dict(existing)
    new_doc["mcpServers"] = merged
    save_document(path, new_doc)
    return status


def merge_codex_mcp_servers(
    project: Path,
    servers: dict[str, Any],
) -> dict[str, Any]:
    """Merge MCP servers into the project's fallback ``.codex/config.toml``.

    Existing server definitions are user-owned and remain untouched. New
    entries are appended through ``tomlkit`` so comments, ordering, and
    unrelated Codex settings survive byte-for-byte except for the appended
    table.
    """

    path = project / ".codex" / "config.toml"
    status: dict[str, Any] = {
        "path": ".codex/config.toml",
        "integrationKey": "codex",
        "format": "codex-toml",
        "added": [],
        "updated": [],
        "preserved": [],
        "managedServers": [],
        "unchanged": False,
        "skipped": False,
        "nodeAvailable": node_available(),
        "warnings": [],
    }

    if path.exists():
        source = path.read_text(encoding="utf-8")
        try:
            document = tomlkit.parse(source)
        except (ParseError, ValueError, TypeError):
            status["skipped"] = True
            status["reason"] = (
                "existing .codex/config.toml is not valid TOML; left untouched"
            )
            return status
    else:
        document = tomlkit.document()

    current_servers = document.get("mcp_servers")
    if current_servers is None:
        current_servers = tomlkit.table()
        document.add("mcp_servers", current_servers)
    elif not isinstance(current_servers, MutableMapping):
        status["skipped"] = True
        status["reason"] = (
            "existing .codex/config.toml `mcp_servers` is not a table; "
            "left untouched"
        )
        return status

    for name, spec in servers.items():
        if name not in current_servers:
            entry = tomlkit.table()
            fields = _codex_mcp_fields(spec)
            command = fields.get("command")
            args = fields.get("args")
            if not isinstance(command, str) or not isinstance(args, list):
                raise ValueError(
                    f"Codex MCP server {name!r} requires command and args."
                )
            for key, value in fields.items():
                entry.add(key, value)
            current_servers.add(name, entry)
            status["added"].append(name)
            status["managedServers"].append(name)
            continue
        existing = current_servers[name]
        if _codex_mcp_entry_matches(existing, spec):
            status["preserved"].append(str(name))
            status["managedServers"].append(name)
            continue
        if (
            name == "playwright"
            and (
                _codex_mcp_entry_matches(
                    existing,
                    LEGACY_PLAYWRIGHT_MCP_SERVER,
                )
                or _codex_mcp_entry_matches(
                    existing,
                    PLAYWRIGHT_MCP_SERVER,
                )
            )
        ):
            for key, value in _codex_mcp_fields(spec).items():
                existing[key] = value
            status["updated"].append(name)
            status["managedServers"].append(name)
            continue
        status["preserved"].append(str(name))
        status["warnings"].append(
            f"Preserved user-owned MCP server '{name}' because it differs "
            "from the exact legacy VerifySignal entry."
        )

    for name in current_servers.keys():
        if (
            name not in servers
            and str(name) not in status["preserved"]
        ):
            status["preserved"].append(str(name))

    preserved_set = set(status["preserved"])
    status["preserved"] = [
        str(name)
        for name in current_servers.keys()
        if str(name) in preserved_set
    ]

    if not status["added"] and not status["updated"]:
        status["unchanged"] = True
        return status

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(tomlkit.dumps(document), encoding="utf-8")
    return status


def _mcp_entry_matches(existing: Any, expected: dict[str, Any]) -> bool:
    if not isinstance(existing, MutableMapping):
        return False
    command = existing.get("command")
    args = existing.get("args")
    expected_command = expected.get("command")
    expected_args = expected.get("args")
    return (
        command == expected_command
        and isinstance(args, (list, tuple))
        and list(args) == list(expected_args or [])
    )


def _codex_mcp_fields(spec: Any) -> dict[str, Any]:
    if not isinstance(spec, dict):
        return {}
    fields: dict[str, Any] = {}
    for key, value in spec.items():
        if key == "type":
            continue
        if key == "args" and isinstance(value, list):
            fields[key] = [str(item) for item in value]
        else:
            fields[key] = value
    return fields


def _codex_mcp_entry_matches(
    existing: Any,
    expected: dict[str, Any],
) -> bool:
    if not isinstance(existing, MutableMapping):
        return False
    expected_fields = _codex_mcp_fields(expected)
    if {str(key) for key in existing.keys()} != set(expected_fields):
        return False
    for key, expected_value in expected_fields.items():
        observed = existing.get(key)
        if isinstance(expected_value, list):
            if not isinstance(observed, (list, tuple)):
                return False
            if list(observed) != expected_value:
                return False
        elif observed != expected_value:
            return False
    return True


def configure_mcp_servers(
    project: Path,
    integration_key: str,
    config_format: str,
    servers: dict[str, Any],
) -> dict[str, Any]:
    """Write an integration's MCP servers to its documented project config."""

    if config_format == "claude-json":
        result = merge_mcp_servers(project, servers)
        result["integrationKey"] = integration_key
        return result
    if config_format == "codex-toml":
        return merge_codex_mcp_servers(project, servers)
    raise ValueError(
        f"Unsupported MCP configuration format for {integration_key}: "
        f"{config_format}"
    )
