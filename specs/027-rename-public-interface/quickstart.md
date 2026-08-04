# Quickstart: Canonical VerifySignal Distribution

## Red/green discipline

For each stage, commit focused tests before implementation, run them to record an expected failure, then commit the smallest implementation separately and re-run focused tests green.

## Focused canonical checks

```sh
.venv/bin/pytest tests/contract/test_docs_install_urls.py tests/contract/test_public_cli_entrypoint_contract.py tests/unit/test_repos.py -q
```

Add packaging identity, compatibility inventory, and migration/release workflow contracts under `tests/contract/` before changing metadata or prose.

## Regression and artifact checks

```sh
.venv/bin/pytest -q
.venv/bin/python -m build
.venv/bin/python -m twine check dist/*
```

Use a clean temporary environment to install each built wheel and invoke both `verifysignal --help` and `verifysignal-spec --help`. Run `scripts/verify-docker.sh` where Docker is available.

## Manual gates

Follow `contracts/release-cutover.md` exactly. Record PyPI project/version URLs, wheel metadata, CLI smoke output, GitHub rename/redirect checks, and trusted-publisher identity in the corresponding PR or release evidence.

