# Contributing to VerifySignal

Thanks for contributing. This guide gets you productive fast. By taking part you
agree to our [Code of Conduct](CODE_OF_CONDUCT.md).

## You do not need the proprietary runtime

You can build, run, and test the entire CLI without VerifySignal Core. This repo
ships a full fake Core that implements the public contract
([`tests/fixtures/verifysignal-core/fake_verifysignal.py`](tests/fixtures/verifysignal-core/fake_verifysignal.py)).
The whole suite runs against it, so you can clone, install, and get a green suite
in a couple of minutes. No account, no runtime download, no network.

## Setup

Python 3.11+ (CI uses 3.12). Node 24+ only if you run a real browser flow.

```sh
python -m pip install -e ".[dev]"
python -m pytest
```

A green suite means you are ready.

## Layout

- `src/verifysignal_spec/`: the CLI.
  - `commands/`: subcommands.
  - `workflows/`: the staged engine, gates, coverage, repair.
  - `core/`: the public Core adapter and contract, the only path to the runtime.
  - `runtime/`: managed download, entitlement, signature, cache.
  - `workspace/`: the `.verifysignal/` layout and validation.
  - `integrations/`: Claude Code and Codex installers.
  - `templates/`: agent skills and workspace scaffolding shipped in the wheel.
- `tests/`: `unit/`, `contract/` (pin the public boundary plus docs and packaging), `integration/` (drive the CLI against the fake Core), `fixtures/`.
- `docs/`: guides and architecture ([index](docs/README.md)).

## Rules that matter here

- **Stay behind the public boundary.** Never import private Core packages or read undocumented report internals. The CLI talks to the runtime only through the `verifysignal-public-cli-json/v1` contract.
- **Red, then green.** For behavior changes, write the failing test first, confirm it fails for the right reason, then make the smallest change that passes. Do not weaken assertions to match an implementation; change the spec first if the intent changed.
- **Preserve behavior.** Existing tests, flags, schemas, templates, and workspace semantics are compatibility contracts. Changes are additive or migrated, with coverage for old and new paths.
- **Secrets never persist.** Credentials resolve from the environment at run time. Never add a secret-looking value to code, tests, docs, or examples.
- **Versions bump themselves.** Do not hand-edit the version: when a PR merges, the version-bump workflow classifies the PR title, updates `pyproject.toml`, `src/verifysignal_spec/__init__.py`, and `CHANGELOG.md` together, tags `vX.Y.Z`, and the tag publishes to PyPI. `tests/unit/test_version_consistency.py` keeps the declarations in sync.
- **English** for committed artifacts.

## Commits and pull requests

Use [Conventional Commits](https://www.conventionalcommits.org) for commits AND
for the PR title: `feat(...)`, `fix(...)`, `docs(...)`, `test(...)`, `ci:`. The
merged-PR title is what decides the release (`!` -> major, feat -> minor,
fix/perf -> patch, others -> none) — the pr-title check enforces the grammar.
Keep pull requests focused, fill in the template, confirm `python -m pytest` is
green, and link the issue.

## Issues and security

Use the issue forms. For anything that could be a vulnerability, follow
[SECURITY.md](SECURITY.md) instead of a public issue.

## Decisions

VerifySignal is open-core. [GOVERNANCE.md](GOVERNANCE.md) explains what is open,
what is managed, and how proposals are decided.
