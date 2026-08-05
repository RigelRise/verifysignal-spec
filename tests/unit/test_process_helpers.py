from __future__ import annotations

import re
from pathlib import Path

from verifysignal_spec.process import join_command, launch_argv, resolve_tool, run_text, split_command

SRC = Path(__file__).resolve().parents[2] / "src" / "verifysignal_spec"

# `subprocess.run(..., text=True)` with no `encoding` decodes with the host locale — cp1252 on most
# Windows installs. Core emits UTF-8 JSON, so one accented character in a page title or an error
# message either raises UnicodeDecodeError mid-run or mojibakes into json.loads. The correct
# incantation is TWO keyword arguments, which is exactly the kind of rule that gets half-applied at
# the next call site. This ratchet is what stops that.
_TEXT_TRUE = re.compile(r"\btext\s*=\s*True\b")


def test_no_subprocess_call_decodes_with_the_host_locale() -> None:
    offenders: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        for number, line in enumerate(source.splitlines(), start=1):
            stripped = line.strip()
            # Prose that NAMES the anti-pattern is not the anti-pattern.
            if stripped.startswith("#") or path.name == "process.py":
                continue
            if _TEXT_TRUE.search(line):
                offenders.append(f"{path.relative_to(SRC)}:{number}: {line.strip()}")

    assert offenders == [], (
        "Use run_text/popen_text (or pass encoding= and errors= explicitly) instead of text=True:\n"
        + "\n".join(offenders)
    )


def test_run_text_decodes_utf8_whatever_the_host_locale_is() -> None:
    # A subprocess emitting non-ASCII UTF-8 must round-trip, not raise and not mojibake.
    result = run_text(
        ["python3", "-c", "print('acentua\\u00e7\\u00e3o e emoji \\U0001f7e2')"],
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    assert "acentuação e emoji 🟢" in result.stdout


def test_command_round_trip_survives_a_windows_path() -> None:
    # shlex runs in POSIX mode, where a backslash ESCAPES: shlex.split(r"C:\Tools\core.exe --flag")
    # returns "C:Toolscore.exe", silently eating every separator in a Windows path. That string is
    # persisted as the workspace's coreCommand and re-parsed on the next run.
    raw = r"C:\Tools\VerifySignal\core.exe --flag"
    assert split_command(raw, is_windows=True) == [r"C:\Tools\VerifySignal\core.exe", "--flag"]

    quoted = r'"C:\Program Files\VerifySignal\core.exe" --flag'
    assert split_command(quoted, is_windows=True) == [r"C:\Program Files\VerifySignal\core.exe", "--flag"]

    # POSIX behaviour is untouched.
    assert split_command("/usr/local/bin/core --flag", is_windows=False) == ["/usr/local/bin/core", "--flag"]

    # And the pair round-trips, which is what the persisted coreCommand actually needs.
    for windows in (True, False):
        parts = ["/opt/verify signal/core", "--flag"] if not windows else [r"C:\Program Files\v\core.exe", "--flag"]
        assert split_command(join_command(parts, is_windows=windows), is_windows=windows) == parts


def test_resolve_tool_wraps_a_windows_shim_in_cmd(monkeypatch) -> None:
    # shutil.which applies PATHEXT and happily returns npm.cmd, but CreateProcess cannot execute a
    # .cmd from an argv vector — so a bare "npm" resolved and then failed to launch.
    monkeypatch.setattr("verifysignal_spec.process.shutil.which", lambda name: r"C:\npm\npm.cmd")
    monkeypatch.setenv("COMSPEC", r"C:\Windows\System32\cmd.exe")
    assert resolve_tool("npm", is_windows=True) == [r"C:\Windows\System32\cmd.exe", "/d", "/s", "/c", r"C:\npm\npm.cmd"]

    # A real executable needs no wrapper, on either platform.
    monkeypatch.setattr("verifysignal_spec.process.shutil.which", lambda name: r"C:\npm\npm.exe")
    assert resolve_tool("npm", is_windows=True) == [r"C:\npm\npm.exe"]

    monkeypatch.setattr("verifysignal_spec.process.shutil.which", lambda name: "/usr/bin/npm")
    assert resolve_tool("npm", is_windows=False) == ["/usr/bin/npm"]

    monkeypatch.setattr("verifysignal_spec.process.shutil.which", lambda name: None)
    assert resolve_tool("npm") is None


def test_launch_argv_runs_our_windows_shim_through_node_not_cmd(tmp_path: Path) -> None:
    # The Windows Core package declares bin/verifysignal-core.cmd as its entry point, and
    # CreateProcess cannot execute a batch file from an argv vector (WinError 193).
    package = tmp_path / "verifysignal-core"
    (package / "bin").mkdir(parents=True)
    (package / "runtime").mkdir()
    shim = package / "bin" / "verifysignal-core.cmd"
    shim.write_text("@echo off\n", encoding="utf-8")
    bundle = package / "runtime" / "verifysignal-core.js"
    bundle.write_text("// bundle\n", encoding="utf-8")

    argv = launch_argv(str(shim), is_windows=True)

    # node + the bundle is ONE quoting layer. Going through `cmd.exe /c` would add a second one on
    # top of list2cmdline, which quotes on spaces only -- so an argument containing & ^ or | would be
    # interpreted by cmd.exe. node is already required: the POSIX launcher is itself `exec node`.
    assert argv[0].endswith("node") or argv[0] == "node"
    assert argv[1] == str(bundle)
    assert "cmd.exe" not in " ".join(argv).lower()


def test_launch_argv_falls_back_to_cmd_for_a_shim_we_did_not_write(tmp_path: Path) -> None:
    foreign = tmp_path / "some-tool.cmd"
    foreign.write_text("@echo off\n", encoding="utf-8")

    argv = launch_argv(str(foreign), is_windows=True)

    assert argv[:4] == [argv[0], "/d", "/s", "/c"]
    assert argv[0].lower().endswith("cmd.exe")
    assert argv[4] == str(foreign)


def test_launch_argv_is_a_no_op_on_posix(tmp_path: Path) -> None:
    executable = tmp_path / "verifysignal-core"
    executable.write_text("#!/bin/sh\n", encoding="utf-8")
    assert launch_argv(str(executable), is_windows=False) == [str(executable)]
    # And a plain executable needs no wrapper even on Windows.
    assert launch_argv(r"C:\tools\core.exe", is_windows=True) == [r"C:\tools\core.exe"]
