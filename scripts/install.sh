#!/bin/sh
# Bootstrap installer for the VerifySignal CLI on macOS and Linux.
#
# The documented one-line install used to be `uv tool install verifysignal-spec`, which silently
# assumes the reader already has uv — and most first-time readers do not. They hit
# `command not found: uv` on step 01 of onboarding, with no in-product way forward. This script is
# the missing step: it installs uv when it is absent, and uv in turn downloads a managed Python
# 3.11+ when the machine has none. So the only real prerequisite left is curl (or wget).
#
# What it deliberately does NOT do: install Node.js or Chromium. Those belong to run-time readiness,
# which `verifysignal check` already owns and reports far better than a bootstrap script could. We
# warn about them and stop there — an installer that reaches for a package manager to satisfy a
# runtime dependency is an installer that fails on the machines it was written to help.
#
# Usage:
#   curl -LsSf https://verifysignal.io/install.sh | sh
#   curl -LsSf https://verifysignal.io/install.sh | sh -s -- --version 0.22.0
#
# Options:
#   --version <X.Y.Z>   Install an exact release from PyPI instead of the latest.
#   --from <spec>       Install from an arbitrary source (e.g. a git+https URL) instead of PyPI.
#   --no-modify-path    Do not let uv touch shell profiles to put its bin directory on PATH.
#   --help              Print this usage and exit.
#
# Environment equivalents: VERIFYSIGNAL_INSTALL_VERSION, VERIFYSIGNAL_INSTALL_FROM,
# VERIFYSIGNAL_NO_MODIFY_PATH.
set -eu

PACKAGE="verifysignal-spec"
# The interpreter the CLI runs on. Pinned rather than left to the system Python so that the install
# is identical on a machine with Python 3.9, a machine with 3.13, and a machine with none at all.
PYTHON_VERSION="3.12"
UV_INSTALLER_URL="https://astral.sh/uv/install.sh"
DOCS_URL="https://github.com/RigelRise/verifysignal-spec/blob/main/docs/installation.md"
WINDOWS_ONELINER='powershell -ExecutionPolicy Bypass -c "irm https://verifysignal.io/install.ps1 | iex"'

version="${VERIFYSIGNAL_INSTALL_VERSION:-}"
from_spec="${VERIFYSIGNAL_INSTALL_FROM:-}"
modify_path=1
if [ -n "${VERIFYSIGNAL_NO_MODIFY_PATH:-}" ]; then
  modify_path=0
fi

# Colour only when stdout is a terminal. Piped into a log or a CI transcript, escape codes are noise.
if [ -t 1 ]; then
  bold="$(printf '\033[1m')"
  red="$(printf '\033[31m')"
  yellow="$(printf '\033[33m')"
  green="$(printf '\033[32m')"
  reset="$(printf '\033[0m')"
else
  bold=""
  red=""
  yellow=""
  green=""
  reset=""
fi

# Everything diagnostic goes to stderr: `sh` may be reading this script from stdin, and a caller
# that pipes our stdout somewhere should get the result, not the commentary.
say() { printf '%s\n' "$*" >&2; }
step() { printf '%s==>%s %s\n' "$bold" "$reset" "$*" >&2; }
warn() { printf '%swarning:%s %s\n' "$yellow" "$reset" "$*" >&2; }
die() {
  printf '%serror:%s %s\n' "$red" "$reset" "$*" >&2
  exit 1
}

# Inlined rather than read back out of this file with sed: piped into `sh` from curl there is no
# file to read, and --help printing nothing is exactly the failure mode this script exists to fix.
usage() {
  cat >&2 <<'USAGE'
Install the VerifySignal CLI on macOS or Linux. Installs uv when it is missing; uv then provides
a managed Python 3.11+, so no pre-existing Python is required.

Usage:
  curl -LsSf https://verifysignal.io/install.sh | sh
  curl -LsSf https://verifysignal.io/install.sh | sh -s -- --version 0.22.0

Options:
  --version <X.Y.Z>   Install an exact release from PyPI instead of the latest.
  --from <spec>       Install from an arbitrary source (e.g. a git+https URL) instead of PyPI.
  --no-modify-path    Do not let uv touch shell profiles to put its bin directory on PATH.
  -h, --help          Print this usage and exit.

Environment equivalents: VERIFYSIGNAL_INSTALL_VERSION, VERIFYSIGNAL_INSTALL_FROM,
VERIFYSIGNAL_NO_MODIFY_PATH.
USAGE
}

while [ $# -gt 0 ]; do
  case "$1" in
    --version)
      [ $# -ge 2 ] || die "--version needs a value (e.g. --version 0.22.0)"
      version="$2"
      shift 2
      ;;
    --version=*)
      version="${1#--version=}"
      shift
      ;;
    --from)
      [ $# -ge 2 ] || die "--from needs a value (e.g. --from git+https://github.com/RigelRise/verifysignal-spec.git)"
      from_spec="$2"
      shift 2
      ;;
    --from=*)
      from_spec="${1#--from=}"
      shift
      ;;
    --no-modify-path)
      modify_path=0
      shift
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      die "unknown option: $1 (try --help)"
      ;;
  esac
done

[ -z "$version" ] || [ -z "$from_spec" ] ||
  die "--version and --from are mutually exclusive: pin the version inside the --from spec instead"

# --- platform gate -----------------------------------------------------------------------------
os="$(uname -s 2>/dev/null || echo unknown)"
arch="$(uname -m 2>/dev/null || echo unknown)"
case "$os" in
  Darwin | Linux) ;;
  MINGW* | MSYS* | CYGWIN* | Windows_NT)
    die "this script is for macOS and Linux. On Windows run:
    $WINDOWS_ONELINER"
    ;;
  *)
    die "unsupported platform: $os ($arch). See $DOCS_URL"
    ;;
esac

# --- downloader --------------------------------------------------------------------------------
# uv's own installer needs one of these too, so failing here produces a better message than letting
# the pipeline collapse halfway through.
if command -v curl >/dev/null 2>&1; then
  fetch() { curl -LsSf "$1"; }
elif command -v wget >/dev/null 2>&1; then
  fetch() { wget -qO- "$1"; }
else
  die "neither curl nor wget is available. Install one of them and re-run. See $DOCS_URL"
fi

# --- resolve uv --------------------------------------------------------------------------------
# uv installs itself to ~/.local/bin, which is very often not on PATH in the shell that is running
# this script (particularly a fresh container or a non-login shell). So a plain `command -v uv` is
# not enough: check the known install locations before deciding uv is missing, and again after
# installing it.
resolve_uv() {
  if command -v uv >/dev/null 2>&1; then
    command -v uv
    return 0
  fi
  # Unset variables collapse a candidate to something like "/uv"; the -x test rejects those, so no
  # separate guard is needed.
  for candidate in \
    "${UV_INSTALL_DIR:-}/uv" \
    "${XDG_BIN_HOME:-}/uv" \
    "$HOME/.local/bin/uv" \
    "$HOME/.cargo/bin/uv" \
    /opt/homebrew/bin/uv \
    /usr/local/bin/uv; do
    if [ -x "$candidate" ]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

uv_bin="$(resolve_uv || true)"

if [ -z "$uv_bin" ]; then
  step "uv not found — installing it from astral.sh"
  # Piping the vendor installer is the documented, signed-release path for uv. We do not mirror or
  # re-host it: a stale copy of someone else's installer is worse than the original.
  fetch "$UV_INSTALLER_URL" | sh >&2 ||
    die "the uv installer failed. Install uv manually (https://docs.astral.sh/uv/getting-started/installation/) and re-run this script."
  # The installer only edits shell profiles; it cannot change THIS shell's PATH. Make its default
  # location visible so the resolve below succeeds without a new terminal.
  PATH="${UV_INSTALL_DIR:-$HOME/.local/bin}:$PATH"
  export PATH
  uv_bin="$(resolve_uv || true)"
  [ -n "$uv_bin" ] ||
    die "uv still not found after installation. Open a new terminal and re-run, or install uv manually. See $DOCS_URL"
  say "  uv installed at $uv_bin"
else
  say "  using uv at $uv_bin"
fi

# --- install the CLI ---------------------------------------------------------------------------
# --force makes re-running the one-liner an upgrade rather than a no-op, which is what a user who
# pastes the install command a second time actually means.
set -- tool install --force --python "$PYTHON_VERSION"

if [ -n "$from_spec" ]; then
  step "Installing $PACKAGE from $from_spec"
  set -- "$@" "$PACKAGE" --from "$from_spec"
elif [ -n "$version" ]; then
  step "Installing $PACKAGE==$version"
  set -- "$@" "$PACKAGE==$version"
else
  step "Installing $PACKAGE"
  set -- "$@" "$PACKAGE"
fi

"$uv_bin" "$@" >&2 || die "installation failed. Re-run with the same command to retry, or see $DOCS_URL"

if [ "$modify_path" -eq 1 ]; then
  # Best effort: uv writes the PATH line into the shell profiles it recognises. A shell it does not
  # recognise is not a reason to fail an otherwise complete install — we print the path below.
  "$uv_bin" tool update-shell >/dev/null 2>&1 ||
    warn "could not update your shell profile automatically; add the directory printed below to PATH yourself"
fi

# --- verify ------------------------------------------------------------------------------------
tool_dir="$("$uv_bin" tool dir --bin 2>/dev/null || printf '%s\n' "$HOME/.local/bin")"
verifysignal_bin="$tool_dir/verifysignal"
[ -x "$verifysignal_bin" ] || verifysignal_bin="$(command -v verifysignal 2>/dev/null || true)"
[ -n "$verifysignal_bin" ] && [ -x "$verifysignal_bin" ] ||
  die "installed, but the verifysignal executable was not found under $tool_dir. See $DOCS_URL"

installed_version="$("$verifysignal_bin" --version 2>&1)" ||
  die "the installed verifysignal binary failed to run: $installed_version"

say ""
printf '%s✓%s %s\n' "$green" "$reset" "$installed_version" >&2

# --- runtime readiness (warn only) ---------------------------------------------------------------
if command -v node >/dev/null 2>&1; then
  node_major="$(node --version 2>/dev/null | sed 's/^v//' | cut -d. -f1)"
  case "$node_major" in
    '' | *[!0-9]*) warn "could not read the Node.js version; VerifySignal needs Node.js 24+" ;;
    *)
      [ "$node_major" -ge 24 ] ||
        warn "Node.js $node_major found; VerifySignal needs Node.js 24+ to run validations"
      ;;
  esac
else
  warn "Node.js not found; VerifySignal needs Node.js 24+ to run validations"
fi

say ""
say "Next steps:"
case ":$PATH:" in
  *":$tool_dir:"*) ;;
  *) say "  0. Open a new terminal (or add $tool_dir to PATH) so 'verifysignal' resolves." ;;
esac
say "  1. cd into your project"
say "  2. verifysignal init --here --integration claude   # or: codex"
say "  3. verifysignal check                              # reports Node.js and Chromium readiness"
