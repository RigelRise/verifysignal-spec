# Installation

VerifySignal uses the public `verifysignal` CLI as the user-facing command.
`verifysignal-spec` remains a backward-compatible alias for existing projects and
generated guidance.

## From PyPI (recommended)

Once released, install the CLI from PyPI:

```sh
uv tool install verifysignal-spec        # or: pipx install verifysignal-spec
verifysignal --version
```

Run it once without installing:

```sh
uvx verifysignal-spec --version
```

The sections below install directly from the Git repository. Useful for the
bleeding edge, a fork, or before the first tagged release is published to PyPI.

## Persistent Installation

Install a tagged release (replace `vX.Y.Z` with a real tag; the `@vX.Y.Z` forms below only resolve
once a release has been tagged on the repository; until then use the default-branch form):

```sh
uv tool install verifysignal-spec --from git+https://github.com/RigelRise/verifysignal-spec.git@vX.Y.Z
```

Install the latest commit from the default branch:

```sh
uv tool install verifysignal-spec --from git+https://github.com/RigelRise/verifysignal-spec.git
```

Verify:

```sh
verifysignal --version
verifysignal --help
```

Upgrade:

```sh
uv tool install verifysignal-spec --force --from git+https://github.com/RigelRise/verifysignal-spec.git@vX.Y.Z
```

Uninstall:

```sh
uv tool uninstall verifysignal
```

## One-Time Usage

Run without installing permanently:

```sh
uvx --from git+https://github.com/RigelRise/verifysignal-spec.git@vX.Y.Z verifysignal init --here --integration codex
```

## Initialize A Real Project

```sh
cd /path/to/target-project
verifysignal init --here --integration codex
verifysignal check
verifysignal workflow info verifysignal-use-case --json
codex
```

For Claude Code:

```sh
verifysignal init --here --integration claude
claude
```

Initialization installs the pinned Playwright MCP provider and registers its
VerifySignal launcher in the selected agent's user scope through the agent's
public MCP command. It preserves an existing differing `playwright` entry and
reports a blocker instead of overwriting it. After initialization, start the
agent with the ordinary `codex` or `claude` command; no wrapper, `-c` override,
or synthetic project trust is required for browser discovery.

Codex exposes staged workflow skills with dollar-prefixed invocation:

```text
$verifysignal-understand
$verifysignal-specify
$verifysignal-clarify
$verifysignal-plan
$verifysignal-tasks
$verifysignal-implement
$verifysignal-validate
$verifysignal-list
$verifysignal-run
$verifysignal-repair
```

Claude Code uses slash-prefixed invocation:

```text
/verifysignal-understand
/verifysignal-specify
/verifysignal-clarify
/verifysignal-plan
/verifysignal-tasks
/verifysignal-implement
/verifysignal-validate
/verifysignal-list
/verifysignal-run
/verifysignal-repair
```

For browser use cases, a URL found in repository start instructions is only a
suggestion. The agent must ask you to confirm that target or provide another one
for the current workflow before it plans, probes, or runs the browser flow.

Installed workflow commands use `verifysignal workflow check <stage> --json`
before stage-specific work. After upgrading VerifySignal, rerun integration
installation so regenerated agent skills receive the latest prerequisite
guidance:

```sh
verifysignal integration upgrade codex
verifysignal integration upgrade claude
```

Use the same deterministic check outside an agent conversation:

```sh
verifysignal workflow check specify --json
verifysignal workflow check plan --alias login --json
```

The deterministic runner is available without an active agent conversation:

```sh
verifysignal workflow run verifysignal-use-case \
  --goal "Validate that a QA user can sign in." \
  --alias login \
  --integration codex

verifysignal workflow status
verifysignal workflow resume <run-id>
```

Existing legacy `verifysignal-spec-*` skills may be left in place for projects
that already installed the earlier thin CLI flow. New installations prefer
the selected agent's native `$verifysignal-*` or `/verifysignal-*` workflow
commands.

## Managed Runtime And Development Overrides

The normal onboarding path automatically ensures a compatible private runtime:

```sh
verifysignal init --here --integration codex
```

When no override or verified cache exists, VerifySignal asks for the email unlock
token from the official unlock flow, exchanges it for a signed entitlement
receipt through `https://verifysignal.io/api`, requests authorized runtime
metadata/download from the backend, verifies the package, and stores the runtime
in the user cache. The backend owns email delivery, token expiry, exchange
limits, refresh policy, throttling, receipt signing, and runtime download
authorization. The current public/free token policy allows 1 exchange,
at most 1 exchange per hour, with a 30-day default token TTL. The target
project's `.verifysignal/` workspace stays portable and does not store raw
emails, raw tokens, receipt payloads, signed URLs, credentials, screenshots,
browser storage, or private runtime contents.

The CLI asks for the token only after the backend accepts email delivery. If
the message does not arrive, press Enter at the token prompt to preserve the
pending-delivery blocker. Delivery failure or throttling returns its original
blocker immediately and does not attempt a token exchange.

For staging, local backend development, and tests, use an explicit API override:

```sh
verifysignal init --here --integration codex --api-base-url http://localhost:3000/api
```

or:

```sh
export VERIFYSIGNAL_API_BASE_URL=http://localhost:3000/api
```

Do not put credentials, tokens, signed URLs, or query secrets in the API base
URL.

Managed runtime state is isolated by the canonical entitlement API endpoint.
The default production endpoint keeps the existing cache layout for backward
compatibility. Local and staging endpoints use separate deterministic
namespaces for receipts, refresh credentials, verification keys, and runtime
packages, so changing `--api-base-url` cannot reuse trust material from another
backend. An explicit `VERIFYSIGNAL_RUNTIME_CACHE_DIR` remains an exact
maintainer override.

For local development, CI, or offline diagnostics, pass the private Core
repository directory during initialization:

```sh
verifysignal init --here --integration codex \
  --core-cmd /path/to/verifysignal
```

That value is stored in `.verifysignal/workspace.yaml` and reused by `check`,
`validate`, `run`, `repair`, and `core version`. Diagnostic setup remains
available:

```sh
verifysignal core setup --core-cmd /path/to/verifysignal --json
verifysignal core version --json
```

To leave development override mode and select the latest verified managed
runtime, use:

```sh
verifysignal core update --json
verifysignal core version --json
```

`core update` removes workspace-local Core command and version selections before
resolution. It ignores environment, `PATH`, local sibling checkouts, and managed
version pins. An already cached copy is reused only when it is the exact latest
version returned by the backend and still verifies successfully. If acquiring
the latest release fails, VerifySignal may retain a previously verified managed
runtime as an explicit fallback; it never falls back to a local checkout.

To remove persisted local selection without contacting the backend:

```sh
verifysignal core reset --json
```

Reset changes the workspace to managed-only resolution. A one-shot
`--core-cmd` remains available for an explicitly requested diagnostic command
and does not change the persisted mode.

You can also configure the command through an environment variable:

```sh
export VERIFYSIGNAL_CORE_CMD=/path/to/verifysignal
verifysignal core version --json
```

When the value points to a directory with `package.json`, VerifySignal runs:

```sh
npm --silent --prefix <repo> run verifysignal:dev -- <verifysignal-args>
```

Use an explicit command string if needed:

```sh
export VERIFYSIGNAL_CORE_CMD="npm --silent --prefix /path/to/verifysignal run verifysignal:dev --"
```

Overrides are not entitlement success. They only select a Core executable for
development, CI, diagnostics, or offline environments. If the selected runtime
requires entitlement for `authoring-check`, `run`, or `report.inspect`,
VerifySignal provides the cached receipt reference when available or reports the
runtime's public entitlement rejection as a non-repairable blocker.

## Test Credentials

After a use case declares credential environment keys, VerifySignal can prepare
an explicit project-local test file:

```sh
verifysignal credentials prepare create-project \
  --env-file .env.verifysignal.test.local \
  --json
```

The command first installs and verifies an exact entry in the repository-local
Git exclude file, then creates or updates the environment file with owner-only
permissions. It preserves existing values, appends only missing declared keys,
and never prints credential assignments. It blocks before writing the
environment file when the target is not inside a Git repository.

Fill the empty values locally and pass the file explicitly:

```sh
verifysignal validate create-project --runtime-readiness \
  --env-file .env.verifysignal.test.local --json
verifysignal run create-project \
  --env-file .env.verifysignal.test.local --json
```

VerifySignal never reads `.env`, `.env.local`, or another default dotenv path.
The explicit file is parsed as data, not sourced as shell code: undeclared or
duplicate keys, interpolation, substitutions, backticks, multiline constructs,
malformed quoting, and group/other-readable permissions are rejected before
Core starts. Only declared values are passed to the Core child process, and the
parent process environment is not mutated.

## Local Checkout Before Publishing

If the repository has not been published yet:

```sh
uv tool install verifysignal-spec --from /path/to/verifysignal-spec
```

For development inside this repository:

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

## Core Runtime Resolution

Untouched legacy workspaces retain the historical resolution order:

1. Explicit `--core-cmd` flag.
2. Workspace-persisted command (`verifysignal core setup`).
3. `VERIFYSIGNAL_CORE_CMD` environment variable.
4. `verifysignal-core` on `PATH`.
5. A local Core development checkout (maintainers only).
6. Managed download from the entitlement API, pinned by
   `VERIFYSIGNAL_CORE_VERSION` or the workspace-persisted core version.

Workspaces configured by `core setup` use development-override mode: the
persisted command is preferred and managed resolution remains its fallback.
Workspaces reset or updated to managed-only mode ignore workspace commands,
`VERIFYSIGNAL_CORE_CMD`, `PATH`, and sibling checkouts. `core update` is
stricter still: it also ignores a one-shot override and all version pins while
resolving the latest backend release.

Overrides are development and CI conveniences; they do not count as managed
entitlement success. If an override-selected runtime enforces entitlement for a
protected operation, the CLI passes the cached receipt when available or
surfaces the runtime's public entitlement blocker.

The CLI requires the public contract operations `version`, `contracts`,
`authoring-check`, `run`, and `report.inspect`; `discover` is used when the
runtime advertises it.
