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

- Legacy release: migration notice RED 2 / GREEN 2, safe replacement RED 1 / GREEN 8 focused; Docker contracts, old-name wheel/sdist `twine check`, both commands, and import pass; draft PR #21 now targets automated 0.25.1 because 0.25.0 was published while the stack was open.
- Canonical identity: RED 7 expected failures, GREEN 27 passes for distribution, documentation, compatibility inventory, and sibling resolution; draft PR #22.
- Public naming: RED source/recovery assertions, GREEN 19 passes after Runtime/CLI wording; `src/` contains zero `VerifySignal Spec` product labels.
- Release automation: RED 3 expected failures, GREEN 42 passes while retaining the pre-rename OIDC repository identity.
- Regression: full clean-runner GitHub `spec` CI passes after inheriting #24's fixture-freshness ratchet; cross-repository structural dogfood is green with dependencies available in the temporary Core worktree.
- Artifact: `uv build` produces `verifysignal-0.25.0` before automated release bump; wheel and sdist pass `twine check`; isolated metadata is `verifysignal`, both console scripts run, and `verifysignal_spec.runtime.release_signature` imports.
- Docker: 14 canonical distribution, compatibility, URL, and migration contracts pass under the declared toolchain.

## Post-rename patch evidence (2026-08-04)

- Repository identity RED: 5 expected failures; GREEN: 11/11 focused assertions.
- Focused regression: 32 distribution, compatibility, release, freshness, prerequisite, and browser-first assertions pass after the safe-replacement contract was added.
- Full clean-runner GitHub `spec` CI passes without deselection after inheriting #24's fixture-freshness ratchet; real Core dogfood remains covered separately.
- Canonical wheel/sdist build and `twine check`: passed.
- Isolated wheel: canonical metadata, both console scripts, and the stable trust-helper import passed.
- Docker: all 11 post-rename contracts passed.
- Manual gates still block merge/release: repository rename, new exact PyPI publisher binding, 0.23.1 verification, and only then removal of the old binding.
- Draft post-rename patch: #25, stacked on canonical distribution PR #22.
