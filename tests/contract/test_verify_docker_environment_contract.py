"""Ratchet the Docker verifier against host architecture and dependency leakage.

The Spec suite executes a real sibling Core during dogfood. On Apple Silicon,
Docker otherwise selects Linux ARM (which Core does not publish) and the bind
mount exposes Darwin-native ``node_modules`` to Linux. Both failures happen
before the product behavior under test, so the verifier must select the CI
platform and install Core dependencies inside the container.
"""

from __future__ import annotations

import re
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "verify-docker.sh"


def test_docker_verifier_uses_the_supported_ci_platform() -> None:
    script = SCRIPT.read_text(encoding="utf-8")

    assert 'docker_platform="linux/amd64"' in script
    assert 'docker build --platform "$docker_platform"' in script
    assert 'docker run --rm --platform "$docker_platform"' in script


def test_docker_verifier_installs_core_dependencies_in_an_isolated_volume() -> None:
    script = SCRIPT.read_text(encoding="utf-8")
    declaration = re.search(
        r"^([a-z_]*core[a-z_]*node_modules[a-z_]*)=.*mktemp -d",
        script,
        flags=re.MULTILINE,
    )

    assert declaration is not None, "Core node_modules must use a temporary host directory"
    variable = declaration.group(1)
    variable_reference = rf"\$(?:{re.escape(variable)}|\{{{re.escape(variable)}\}})"
    mount = next(
        (
            line
            for line in script.splitlines()
            if "-v " in line
            and "VERIFYSIGNAL_CORE_DIR" in line
            and "node_modules" in line
        ),
        "",
    )
    assert mount, "the temporary dependency directory must mask the pinned Core node_modules"
    assert re.search(variable_reference, mount)

    container_command = script[script.index("sh -c") :]
    explicit_pin = r'"\$(?:VERIFYSIGNAL_CORE_DIR|\{VERIFYSIGNAL_CORE_DIR\})"'
    npm_ci_for_pin = rf"npm\s+(?:ci\s+--prefix\s+{explicit_pin}|--prefix\s+{explicit_pin}\s+ci)"
    assert re.search(npm_ci_for_pin, container_command), (
        "the container must run npm ci against the explicitly pinned Core checkout"
    )

    cleanup = next(
        (
            line
            for line in script.splitlines()
            if line.lstrip().startswith("trap ") and "EXIT" in line
        ),
        "",
    )
    assert "rm -rf --" in cleanup
    assert re.search(variable_reference, cleanup)
