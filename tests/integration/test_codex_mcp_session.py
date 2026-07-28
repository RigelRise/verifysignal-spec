from __future__ import annotations

import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import threading
import time
from typing import Any

import pytest

from verifysignal_spec.integrations.codex import CodexIntegration
from verifysignal_spec.commands.integration import install as install_integration
from verifysignal_spec.integrations.mcp import (
    ensure_playwright_mcp_runtime,
)
from helpers import FAKE_CORE


def _send(
    process: subprocess.Popen[str],
    message: dict[str, object],
) -> None:
    assert process.stdin is not None
    process.stdin.write(json.dumps(message) + "\n")
    process.stdin.flush()


def _receive_until(
    process: subprocess.Popen[str],
    messages: queue.Queue[dict[str, Any] | None],
    request_id: int,
    *,
    timeout_seconds: float = 45,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        remaining = max(0.0, deadline - time.monotonic())
        try:
            message = messages.get(timeout=remaining)
        except queue.Empty:
            break
        if message is None:
            break
        reader_error = message.get("__reader_error__")
        if reader_error:
            raise RuntimeError(f"Codex app-server output reader failed: {reader_error}")
        if message.get("id") == request_id:
            return message
    stderr = ""
    if process.poll() is not None and process.stderr is not None:
        stderr = process.stderr.read().strip()
    raise TimeoutError(
        f"Codex app-server did not answer request {request_id}; "
        f"exit={process.poll()}; stderr={stderr}"
    )


def _start_response_reader(
    process: subprocess.Popen[str],
) -> queue.Queue[dict[str, Any] | None]:
    assert process.stdout is not None
    messages: queue.Queue[dict[str, Any] | None] = queue.Queue()

    def read_messages() -> None:
        try:
            for line in process.stdout:
                if line.strip():
                    messages.put(json.loads(line))
        except Exception as exc:  # pragma: no cover - failure detail only
            messages.put({"__reader_error__": repr(exc)})
        finally:
            messages.put(None)

    threading.Thread(target=read_messages, daemon=True).start()
    return messages


def _server_rows(result: object) -> list[dict[str, Any]]:
    if isinstance(result, dict):
        rows = result.get("data") or result.get("servers")
        if rows is None:
            rows = result
    else:
        rows = result
    if isinstance(rows, dict):
        rows = [
            {"name": name, **value}
            for name, value in rows.items()
            if isinstance(value, dict)
        ]
    return [item for item in rows or [] if isinstance(item, dict)]


def _tool_names(server: dict[str, Any]) -> set[str]:
    tools = server.get("tools") or []
    if isinstance(tools, dict):
        return {str(name) for name in tools}
    return {
        str(item.get("name"))
        for item in tools
        if isinstance(item, dict) and item.get("name")
    }


@pytest.mark.skipif(
    os.environ.get("VERIFYSIGNAL_RUN_REAL_CODEX_TESTS") != "1",
    reason="real Codex session acceptance is enabled explicitly in CI",
)
def test_plain_codex_session_from_fresh_project_discovers_playwright_tools(
    tmp_path,
    monkeypatch,
) -> None:
    codex = shutil.which("codex")
    assert codex, "VERIFYSIGNAL_RUN_REAL_CODEX_TESTS requires the Codex CLI"

    cache = Path(
        os.environ.get(
            "VERIFYSIGNAL_PLAYWRIGHT_MCP_CACHE_DIR",
            str(tmp_path / "playwright-mcp-cache"),
        )
    )
    runtime = ensure_playwright_mcp_runtime(
        cache_root=cache,
        timeout_seconds=180,
    )
    assert runtime["status"] == "ready", runtime

    project = tmp_path / "fresh-project"
    project.mkdir()
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir(mode=0o700)
    environment = dict(os.environ)
    environment["CODEX_HOME"] = str(codex_home)
    environment["VERIFYSIGNAL_PLAYWRIGHT_MCP_CACHE_DIR"] = str(cache)
    environment["VERIFYSIGNAL_PLAYWRIGHT_MCP_AUTO_INSTALL"] = "1"
    environment["VERIFYSIGNAL_AGENT_MCP_AUTO_REGISTER"] = "1"
    environment["VERIFYSIGNAL_CORE_CMD"] = str(FAKE_CORE)
    # The provider has already been prepared above. From this point onward,
    # startup must use only that managed cache: an npx/npm fallback would fail
    # because npm is offline and its ordinary package cache is empty.
    environment["NPM_CONFIG_OFFLINE"] = "true"
    environment["NPM_CONFIG_CACHE"] = str(tmp_path / "empty-npm-cache")
    environment["NPM_CONFIG_REGISTRY"] = "http://127.0.0.1:1/"
    executable_dir = str(Path(sys.executable).resolve().parent)
    environment["PATH"] = os.pathsep.join(
        filter(
            None,
            [executable_dir, environment.get("PATH", "")],
        )
    )
    for key, value in environment.items():
        monkeypatch.setenv(key, value)
    installed = install_integration(project, "codex")
    assert installed["mcp"]["runtime"]["status"] == "ready", installed

    # This is the customer boundary: no wrapper, -c override, or synthetic
    # project trust is allowed between initialization and starting Codex.
    command = [codex, "app-server", "--listen", "stdio://"]
    process = subprocess.Popen(
        command,
        cwd=project,
        env=environment,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    messages = _start_response_reader(process)
    try:
        _send(
            process,
            {
                "method": "initialize",
                "id": 1,
                "params": {
                    "clientInfo": {
                        "name": "verifysignal_regression_test",
                        "title": "VerifySignal regression test",
                        "version": "1",
                    }
                },
            },
        )
        initialized = _receive_until(process, messages, 1)
        assert "error" not in initialized, initialized
        _send(process, {"method": "initialized", "params": {}})

        _send(
            process,
            {
                "method": "thread/start",
                "id": 2,
                "params": {
                    "cwd": str(project),
                    "approvalPolicy": "never",
                    "sandbox": "read-only",
                    "ephemeral": True,
                },
            },
        )
        started = _receive_until(process, messages, 2, timeout_seconds=60)
        assert "error" not in started, started
        thread = started.get("result", {}).get("thread", {})
        thread_id = thread.get("id")
        assert isinstance(thread_id, str) and thread_id

        _send(
            process,
            {
                "method": "mcpServerStatus/list",
                "id": 3,
                "params": {"threadId": thread_id},
            },
        )
        status = _receive_until(process, messages, 3, timeout_seconds=60)
        assert "error" not in status, status
        servers = _server_rows(status.get("result"))
        playwright = next(
            (
                item
                for item in servers
                if str(item.get("name", "")).lower() == "playwright"
            ),
            None,
        )
        assert playwright is not None, {
            "servers": [item.get("name") for item in servers]
        }
        assert {
            "browser_navigate",
            "browser_snapshot",
            "browser_click",
        }.issubset(_tool_names(playwright)), playwright
        assert not (project / ".playwright-mcp").exists()
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
