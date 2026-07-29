<p align="center">
  <img src="docs/assets/logo.svg" width="72" alt="VerifySignal">
</p>

<h1 align="center">VerifySignal</h1>

<p align="center"><b>AI writes the validation. A deterministic runtime proves it.</b></p>

<p align="center">
  <a href="https://github.com/RigelRise/verifysignal-spec/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/RigelRise/verifysignal-spec/ci.yml?branch=main&label=CI" alt="CI status"></a>
  <a href="https://pypi.org/project/verifysignal-spec/"><img src="https://img.shields.io/pypi/v/verifysignal-spec?color=37E5C4" alt="PyPI version"></a>
  <img src="https://img.shields.io/pypi/pyversions/verifysignal-spec" alt="Supported Python versions">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-Apache_2.0-blue" alt="License: Apache-2.0"></a>
</p>

---

AI multiplied your features. Validating each one is still manual. VerifySignal
turns a product flow (login, checkout, onboarding) into an automatic, repeatable
validation with evidence, straight from your repository.

Your coding agent (Claude Code or Codex) authors the validation and grounds it
against your live app. The VerifySignal runtime runs it deterministically and
leaves a report you can audit. No model decides pass/fail. Same input, same
verdict, every time.

This repo is the open half (Apache-2.0): the `verifysignal` CLI, the
`.verifysignal/` workspace, and the agent skills. The runtime (VerifySignal Core)
is a signed download, unlocked with a free email. No account.

## Quickstart

You need Python 3.11+ and Node 24+. Install the CLI:

```sh
uv tool install verifysignal-spec        # or: pipx install verifysignal-spec
```

Set up your project and check readiness:

```sh
cd your-project
verifysignal init --here --integration claude   # or: codex
verifysignal check
```

Then run the whole flow from your agent, in one line:

```text
/verifysignal "Validate that a user can sign in against https://staging.example.com"
```

The agent drafts the use case, grounds selectors against the live app, validates,
runs, and repairs. It stops only for real unknowns, missing credentials, or a
write it should not make on its own. Credentials come from environment variables
at run time and never touch disk.

<details>
<summary>Install from source</summary>

```sh
uv tool install verifysignal-spec --from git+https://github.com/RigelRise/verifysignal-spec.git
```

</details>

## What you get

- **AI authors, you approve.** The agent drafts and repairs. Nothing runs until it is validated.
- **Deterministic execution.** A fixed action set, no inference. Green means the same thing every time.
- **Evidence, not a checkmark.** Every run leaves a report, screenshots, and a network log you can review and share.
- **Write safety.** Flows that mutate data declare a side-effect policy, are watched at run time, and gate their own reruns.

## How it works

```text
  your repo          verifysignal CLI          VerifySignal Core         evidence
  .verifysignal/  ->  open · Apache-2.0     ->  signed runtime       ->  report.md
  use cases          authoring · gates          deterministic run        report.json
  skills · state     workflow · repair          no model at runtime      screenshots
                                                                          network log
```

The CLI owns authoring, gates, workflow state, and repair. Core owns execution.
They meet at one versioned JSON contract, nothing else. Every command speaks
`--json`, and exit codes are stable (`0` ok, `2` validation, `3` core,
`4` approval, `5` input).

## What a run leaves behind

```text
.verifysignal/runs/login/<run-id>/
  report.md            human-readable, gate by gate
  report.json          machine-readable (qa-report/v1)
  browser/screenshots  captured evidence
  browser/network.ndjson
```

`report.md` says what passed, what failed and why, and links each claim to its
evidence. See [`examples/`](examples/) for two full samples, including a write
flow.

## Open-core

| Open (this repo, Apache-2.0) | Managed (VerifySignal Core) |
| --- | --- |
| CLI, `.verifysignal/` workspace, agent skills, the public contract | deterministic execution, evidence capture, redaction |
| fork it, read it, test all of it against the bundled fake Core | a signed download, free to unlock, no account |

Authoring and safety are open and forkable. Execution stays signed so "green"
means the same thing for everyone. See [GOVERNANCE.md](GOVERNANCE.md).

## Safety

- **Secrets never persist.** Credentials resolve from your environment at run time. Tokens, receipts, and signed URLs are redacted from all output.
- **Writes are declared and watched.** A write flow states what it may touch, is checked at run time, and needs approval to rerun after a commit.
- **The runtime wins.** If the agent and the run disagree, the run result stands. Agents stop and ask instead of inventing selectors.

## What it is not

- Not a replacement for your unit tests or CI. It makes manual product validation repeatable.
- Not an agent that decides pass/fail. Execution is a fixed action set; the agent only authors and repairs.
- Not a service. Everything it manages lives in your repo under `.verifysignal/`.

## CLI

| Command | Purpose |
| --- | --- |
| `verifysignal init --here --integration claude\|codex` | Create `.verifysignal/` and install agent skills |
| `verifysignal check` | Workspace, runtime, and entitlement readiness |
| `verifysignal author <alias> "<description>"` | Register a use case |
| `verifysignal validate <alias>` | Run authoring gates |
| `verifysignal run <alias>` | Execute and capture evidence |
| `verifysignal repair <alias>` | Classify findings and propose repairs |
| `verifysignal discover --url <url> --skill <path>` | Ground selectors against the live DOM |
| `verifysignal workflow ...` | Staged workflow engine |

## Docs and community

- [Documentation](docs/README.md), [Installation](docs/installation.md), [Golden Path](docs/golden-path.md)
- [Contributing](CONTRIBUTING.md), [Governance](GOVERNANCE.md), [Roadmap](ROADMAP.md)
- [Issues](https://github.com/RigelRise/verifysignal-spec/issues),
  [Discussions](https://github.com/RigelRise/verifysignal-spec/discussions)
- Security: please use
  [private reporting](https://github.com/RigelRise/verifysignal-spec/security/advisories/new)
  ([SECURITY.md](SECURITY.md))

## Development

```sh
python -m pip install -e ".[dev]"
python -m pytest
```

Needs Python 3.11+, and a browser for the cross-repo dogfood. To run against the toolchain CI
declares instead of whatever your machine has:

```sh
scripts/verify-docker.sh
```

That mounts the sibling checkouts too, so the cross-repo tests actually run. Without them they skip,
which reads like a pass. It takes any `pytest` arguments: `scripts/verify-docker.sh tests/unit -q`.

The suite runs against a full fake Core, so you can build and test everything
without the runtime.

## License

[Apache-2.0](LICENSE)
