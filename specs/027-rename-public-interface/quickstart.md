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

## Local validation evidence (2026-08-04)

- Legacy release: RED 2 expected failures, GREEN 2 passes; adjacent contracts 7 passes; Docker 2 passes; old-name wheel/sdist pass `twine check`; both commands and import pass in an isolated environment; draft PR #21.
- Canonical identity: RED 7 expected failures, GREEN 27 passes for distribution, documentation, compatibility inventory, and sibling resolution.
- Public naming: RED source/recovery assertions, GREEN 19 passes after Runtime/CLI wording; `src/` contains zero `VerifySignal Spec` product labels.
- Release automation: RED 3 expected failures, GREEN 42 passes while retaining the pre-rename OIDC repository identity.
- Regression: the complete pytest suite passes with four known baseline node IDs deselected; all four reproduce on `origin/main`. Cross-repository structural dogfood is green with dependencies available in the temporary Core worktree.
- Artifact: `uv build` produces `verifysignal-0.22.0` before automated release bump; wheel and sdist pass `twine check`; isolated metadata is `verifysignal`, both console scripts run, and `verifysignal_spec.runtime.release_signature` imports.
- Docker: 14 canonical distribution, compatibility, URL, and migration contracts pass under the declared toolchain.
