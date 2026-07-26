# Contributing to VerifySignal

Thanks for considering a contribution. VerifySignal turns product flows into
deterministic, evidence-backed browser validations. This guide gets you
productive fast.

By participating you agree to our [Code of Conduct](CODE_OF_CONDUCT.md).

## You do not need the proprietary runtime

The most important thing to know up front: **you can build, run, and test the
entire CLI without VerifySignal Core.** This repository ships a full fake Core
that implements the public `verifysignal-public-cli-json/v1` contract
([`tests/fixtures/verifysignal-core/fake_verifysignal.py`](tests/fixtures/verifysignal-core/fake_verifysignal.py)).
The whole suite — unit, contract, and integration — runs against it. A
first-time contributor can clone, install, and get a green suite in a couple of
minutes: no account, no runtime download, no network.

## Development setup

You need Python 3.11+ (CI uses 3.12). Node 24+ is only needed if you exercise
real browser runs against a runtime.

```sh
python -m pip install -e ".[dev]"
python -m pytest
```

A green suite means your environment is ready.

## How the codebase is organized

- `src/verifysignal_spec/` — the CLI.
  - `commands/` — subcommands (`init`, `check`, `author`, `validate`, `run`, `repair`, `discover`, `workflow`, …)
  - `workflows/` — the staged workflow engine, gates, coverage, and repair orchestration
  - `core/` — the public Core adapter and contract projection (the only path to the runtime)
  - `runtime/` — managed download, entitlement, signature verification, cache
  - `workspace/` — the project-local `.verifysignal/` layout and validation
  - `integrations/` — Claude Code and Codex installers
  - `templates/` — agent skills and workspace scaffolding shipped inside the wheel
- `tests/` — `unit/`, `contract/` (pin the public boundary plus docs/packaging), `integration/` (drive the CLI against the fake Core), and `fixtures/`
- `docs/` — user guides and architecture references (see [docs/README.md](docs/README.md))

## The rules that matter here

**Stay behind the public Core boundary.** Never import private VerifySignal Core
packages or read undocumented report internals. The CLI talks to the runtime
only through the versioned `verifysignal-public-cli-json/v1` contract. (This is
Principle I of the [constitution](.specify/memory/constitution.md).)

**Red/green TDD for behavior changes.** Write or update the failing test first,
confirm it fails for the expected reason, then make the smallest change that
passes. Do not weaken assertions or delete meaningful coverage to match an
implementation — if the expected behavior changed, change the spec/plan first
and make that intent explicit.

**Preserve existing behavior.** Treat existing tests, CLI flags, schemas,
templates, run-request and skill formats, and workspace semantics as
compatibility contracts. Changes are additive or intentionally migrated, with
regression coverage for the old and new paths.

**Secret safety is non-negotiable.** Credential values are resolved from the
environment at run time and never persisted — not in `.verifysignal/`, reports,
logs, or fixtures. Never add a secret-looking value to a test, doc, or example.

**Bump the version deliberately.** Any behavior, CLI, schema, template, or
packaging change updates both `pyproject.toml` and
`src/verifysignal_spec/__init__.py` together (patch for fixes, minor for new
backwards-compatible capability, major for a breaking change).
`tests/unit/test_version_consistency.py` enforces that the two stay in sync.

**English only** for committed artifacts — code, comments, docs, and specs.

## Commits and pull requests

- Use [Conventional Commits](https://www.conventionalcommits.org): `feat(...)`,
  `fix(...)`, `docs(...)`, `test(...)`, `ci: …`.
- Keep pull requests focused. Fill in the PR template and confirm
  `python -m pytest` is green.
- Link the issue your change addresses.

## Filing issues

Use the issue forms — **Bug report** or **Feature request**. For anything that
could be a vulnerability, follow [SECURITY.md](SECURITY.md) instead of opening a
public issue.

## How decisions get made

VerifySignal is open-core. [GOVERNANCE.md](GOVERNANCE.md) explains what is open,
what is managed, and how proposals are decided.
