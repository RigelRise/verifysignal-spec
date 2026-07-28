from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from helpers import FAKE_CORE
from verifysignal_spec.commands.integration import install as install_integration
from verifysignal_spec.integrations.mcp import ensure_playwright_mcp_runtime


@pytest.mark.skipif(
    os.environ.get("VERIFYSIGNAL_RUN_REAL_CLAUDE_TESTS") != "1",
    reason="real Claude session acceptance is enabled explicitly in CI",
)
def test_plain_claude_from_second_project_discovers_user_playwright(
    tmp_path,
    monkeypatch,
) -> None:
    claude = shutil.which("claude")
    assert claude, (
        "VERIFYSIGNAL_RUN_REAL_CLAUDE_TESTS requires the Claude Code CLI"
    )

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

    initial_project = tmp_path / "initialized-project"
    initial_project.mkdir()
    second_project = tmp_path / "plain-claude-project"
    second_project.mkdir()
    claude_config = tmp_path / "claude-config"
    claude_config.mkdir(mode=0o700)

    environment = dict(os.environ)
    environment["CLAUDE_CONFIG_DIR"] = str(claude_config)
    environment["VERIFYSIGNAL_PLAYWRIGHT_MCP_CACHE_DIR"] = str(cache)
    environment["VERIFYSIGNAL_PLAYWRIGHT_MCP_AUTO_INSTALL"] = "1"
    environment["VERIFYSIGNAL_AGENT_MCP_AUTO_REGISTER"] = "1"
    environment["VERIFYSIGNAL_CORE_CMD"] = str(FAKE_CORE)
    environment["NPM_CONFIG_OFFLINE"] = "true"
    environment["NPM_CONFIG_CACHE"] = str(tmp_path / "empty-npm-cache")
    environment["NPM_CONFIG_REGISTRY"] = "http://127.0.0.1:1/"
    executable_dir = str(Path(sys.executable).resolve().parent)
    environment["PATH"] = os.pathsep.join(
        filter(None, [executable_dir, environment.get("PATH", "")])
    )
    for key, value in environment.items():
        monkeypatch.setenv(key, value)

    installed = install_integration(initial_project, "claude")
    registration = installed["mcp"]["userRegistration"]
    assert registration["status"] == "ready", installed
    assert registration["scope"] == "user", registration

    observed = subprocess.run(
        [claude, "mcp", "get", "playwright"],
        cwd=second_project,
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=30,
        check=False,
    )

    assert observed.returncode == 0, observed.stderr
    assert "Scope: User config" in observed.stdout
    assert "Command: verifysignal" in observed.stdout
    assert "Args: integration playwright-mcp" in observed.stdout
    assert not (second_project / ".mcp.json").exists()
