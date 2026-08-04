"""RATCHET (first-touch onboarding). The only advertised install command used to be
`uv tool install verifysignal-spec`, which silently assumes uv is already on the machine. It is not,
for most first-time readers — so step 01 of onboarding failed with `command not found: uv` and the
docs offered no way forward. scripts/install.{sh,ps1} are that way forward.

These scripts are the one part of the product that runs on a machine where NOTHING of ours is
installed yet, fetched over the network and piped into a shell. Nothing else in the suite can
exercise them: there is no uv-less machine in CI, and the sh/ps1 sources are neither imported nor
type-checked. So this file pins the properties that would break the install silently — a lost
executable bit, a shebang typo, a renamed package, a syntax error, or docs that advertise a URL the
scripts do not serve — and it pins the SAME one-liners the website publishes, because the two live
in different repositories and drift the moment one of them is edited alone.

What it cannot prove: that the download URLs resolve. Serving https://verifysignal.io/install.sh is
an ops action in verifysignal-website (tests/contract/install-endpoint-contract.test.ts pins the
redirect from that side). What it proves is that the docs, the scripts, and the advertised commands
all agree on ONE set of URLs.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess

import pytest

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INSTALL_SH = ROOT / "scripts/install.sh"
INSTALL_PS1 = ROOT / "scripts/install.ps1"
README = ROOT / "README.md"
INSTALL_DOC = ROOT / "docs/installation.md"

# The one-liners advertised to users. Byte-exact, because a user copies them verbatim.
POSIX_ONELINER = "curl -LsSf https://verifysignal.io/install.sh | sh"
WINDOWS_ONELINER = (
    'powershell -ExecutionPolicy Bypass -c "irm https://verifysignal.io/install.ps1 | iex"'
)


def test_both_installers_exist_and_the_posix_one_is_executable():
    assert INSTALL_SH.is_file(), "scripts/install.sh is the macOS/Linux entry point"
    assert INSTALL_PS1.is_file(), "scripts/install.ps1 is the Windows entry point"
    # `curl | sh` does not need the bit, but `git clone && ./scripts/install.sh` does, and that is
    # the path a reader who inspects the script before running it takes.
    mode = INSTALL_SH.stat().st_mode
    assert mode & stat.S_IXUSR, "scripts/install.sh lost its executable bit"


def test_the_posix_installer_targets_plain_sh_and_fails_fast():
    text = INSTALL_SH.read_text(encoding="utf-8")
    first_line = text.splitlines()[0]
    # /bin/sh, not bash: the installer runs on containers and minimal images where bash is absent,
    # and `curl ... | sh` executes it with sh regardless of the shebang.
    assert first_line == "#!/bin/sh", f"unexpected shebang: {first_line!r}"
    assert "\nset -eu\n" in text, "the installer must abort on the first failed step"
    assert "bash" not in text.lower(), "bash-only constructs would break `curl ... | sh`"


def test_the_posix_installer_parses_under_a_posix_shell():
    # A syntax error here ships a broken one-liner to every new user; nothing else parses this file.
    subprocess.run(["sh", "-n", str(INSTALL_SH)], check=True)


def test_the_windows_installer_parses_under_powershell():
    powershell = shutil.which("pwsh") or shutil.which("powershell")
    if powershell is None:
        pytest.skip("no PowerShell available to parse-check scripts/install.ps1")
    script = (
        "$errors = $null; "
        "[System.Management.Automation.Language.Parser]::ParseFile("
        f"'{INSTALL_PS1}', [ref]$null, [ref]$errors) > $null; "
        "if ($errors) { $errors | ForEach-Object { $_.ToString() }; exit 1 }"
    )
    subprocess.run([powershell, "-NoProfile", "-Command", script], check=True)


@pytest.mark.parametrize(
    ("script", "installer_url"),
    [(INSTALL_SH, "https://astral.sh/uv/install.sh"), (INSTALL_PS1, "https://astral.sh/uv/install.ps1")],
)
def test_installers_bootstrap_uv_from_the_vendor_and_install_this_package(script, installer_url):
    text = script.read_text(encoding="utf-8")
    # Bootstrapping uv is the whole point: without it the script is just a slower way to type the
    # command that already failed for the user.
    assert installer_url in text, f"{script.name} must bootstrap uv from Astral's own installer"
    assert "verifysignal-spec" in text, f"{script.name} must install the published package name"
    assert "tool" in text and "install" in text


@pytest.mark.parametrize("script", [INSTALL_SH, INSTALL_PS1])
def test_installers_do_not_reach_for_a_system_package_manager(script):
    # Deliberate scope line: an installer that shells out to apt/brew/winget to satisfy Node or
    # Chromium is an installer that fails on the machines it was written to help. It warns instead.
    text = script.read_text(encoding="utf-8").lower()
    for manager in ("apt-get install", "brew install", "winget install", "choco install"):
        assert manager not in text, f"{script.name} must not install system packages ({manager})"


@pytest.mark.parametrize(
    ("script", "skip_flag"),
    # The opt-out spells itself the way each shell does: a POSIX long flag, a PowerShell switch.
    [(INSTALL_SH, "--skip-playwright-mcp"), (INSTALL_PS1, "SkipPlaywrightMcp")],
)
def test_installers_set_up_the_browser_tooling_and_can_skip_it(script, skip_flag):
    # The agent authors against a live page through the pinned Playwright MCP provider. `init`
    # installs it too, but a machine with no npm only finds that out mid-onboarding, after init
    # comes back blocked and the first agent session has no browser tools at all.
    text = script.read_text(encoding="utf-8")
    assert "integration setup-playwright-mcp" in text, (
        f"{script.name} must pre-install the Playwright MCP provider"
    )
    # Offline installs and CI need a way out; the provider setup hits the npm registry.
    assert skip_flag in text, f"{script.name} must offer {skip_flag}"
    assert "VERIFYSIGNAL_SKIP_PLAYWRIGHT_MCP" in text, f"{script.name} must honour the env opt-out"
    assert "npm" in text, f"{script.name} must handle a machine without npm"


@pytest.mark.parametrize("script", [INSTALL_SH, INSTALL_PS1])
def test_installers_do_not_claim_check_reports_node_or_chromium(script):
    # commands/check.py covers the workspace, the Core runtime, and integrations. It does NOT look
    # at Node, Chromium, or the MCP provider — telling a user otherwise sends them to a command that
    # will happily pass while the thing they are missing is still missing.
    text = script.read_text(encoding="utf-8")
    assert "verifysignal check" in text, f"{script.name} must still point at the readiness command"
    for claim in ("check                              # reports Node", "check reports Node"):
        assert claim not in text, f"{script.name} overstates what `verifysignal check` covers"


def test_the_advertised_one_liners_match_the_scripts_that_exist():
    for doc in (README, INSTALL_DOC):
        text = doc.read_text(encoding="utf-8")
        assert POSIX_ONELINER in text, f"{doc.name} must advertise the macOS/Linux one-liner"
        assert WINDOWS_ONELINER in text, f"{doc.name} must advertise the Windows one-liner"

    # The URL path and the file that serves it are the same string in two repositories; pin the
    # mapping here so a rename of either side fails loudly.
    assert INSTALL_SH.name == POSIX_ONELINER.split("/")[-1].split()[0]
    assert INSTALL_PS1.name in WINDOWS_ONELINER


def test_install_docs_still_offer_the_direct_package_install():
    # The bootstrap must not become the ONLY documented path: readers who already have uv or pipx,
    # and every CI job, need the plain package install.
    doc = INSTALL_DOC.read_text(encoding="utf-8")
    assert "uv tool install verifysignal-spec" in doc
    assert "pipx install verifysignal-spec" in doc


def test_install_docs_show_how_to_read_the_script_before_running_it():
    # Piping a remote script into a shell is only defensible when the docs show the audit path.
    doc = INSTALL_DOC.read_text(encoding="utf-8")
    assert "-o verifysignal-install.sh" in doc
    assert "-OutFile verifysignal-install.ps1" in doc


def test_the_uninstall_command_names_the_tool_that_was_installed():
    # `uv tool uninstall verifysignal` names the COMMAND; uv registers tools under the PACKAGE name,
    # so the old line could never uninstall anything this project installs.
    doc = INSTALL_DOC.read_text(encoding="utf-8")
    assert "uv tool uninstall verifysignal-spec" in doc
    assert "uv tool uninstall verifysignal\n" not in doc


def test_the_posix_installer_prints_usage_without_reading_itself_from_disk():
    # Piped from curl there is no $0 to sed; --help printing nothing is exactly the dead end this
    # script exists to remove. Run it for real: the help path must not touch the network.
    env = {**os.environ, "PATH": os.environ.get("PATH", "")}
    completed = subprocess.run(
        ["sh", str(INSTALL_SH), "--help"],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )
    assert completed.returncode == 0
    assert "--version" in completed.stderr + completed.stdout
