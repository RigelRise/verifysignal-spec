from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def isolate_verifysignal_runtime_cache(tmp_path, monkeypatch):
    if "VERIFYSIGNAL_RUNTIME_CACHE_DIR" not in os.environ:
        monkeypatch.setenv("VERIFYSIGNAL_RUNTIME_CACHE_DIR", str(tmp_path / "runtime-cache"))
    if "VERIFYSIGNAL_PLAYWRIGHT_MCP_CACHE_DIR" not in os.environ:
        monkeypatch.setenv(
            "VERIFYSIGNAL_PLAYWRIGHT_MCP_CACHE_DIR",
            str(tmp_path / "playwright-mcp-cache"),
        )
    if "VERIFYSIGNAL_PLAYWRIGHT_MCP_AUTO_INSTALL" not in os.environ:
        # Integration-install tests exercise config generation without network.
        # Dedicated MCP runtime tests cover setup and the stdio handshake.
        monkeypatch.setenv(
            "VERIFYSIGNAL_PLAYWRIGHT_MCP_AUTO_INSTALL",
            "0",
        )
    if "VERIFYSIGNAL_AGENT_MCP_AUTO_REGISTER" not in os.environ:
        # Ordinary tests must never mutate the developer's Codex or Claude
        # user configuration. Dedicated registration and real-session tests
        # opt into the product behavior with isolated agent state.
        monkeypatch.setenv(
            "VERIFYSIGNAL_AGENT_MCP_AUTO_REGISTER",
            "0",
        )
