# Implementation Plan: Canonical VerifySignal Distribution

**Branch**: `027-rename-public-interface` | **Date**: 2026-08-04 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/027-rename-public-interface/spec.md`

## Summary

Execute a three-release identity cutover: announce migration in final `verifysignal-spec` patch 0.22.1; publish the same compatible interface as canonical distribution `verifysignal` 0.23.0 before repository rename; then canonicalize GitHub metadata and trusted publishing in 0.23.1 after rename. Preserve the import package, both console scripts, all schemas, workspace state, environment variables, roles, commands, skill aliases, Runtime contracts, and secret behavior.

## Technical Context

**Language/Version**: Python 3.11+; GitHub Actions YAML
**Primary Dependencies**: Typer, Rich, Pydantic 2, PyYAML, cryptography, setuptools
**Storage**: Project-local `.verifysignal/` files remain schema-compatible; no migration
**Testing**: pytest 8, `build`, `twine`, isolated `uv`/venv installation, Docker regression
**Target Platform**: PyPI and Python 3.11-3.13 on supported desktop/CI platforms
**Project Type**: Open-source Python CLI, workspace engine, integration/skill templates, and Runtime adapter
**Performance Goals**: No CLI or workflow performance regression; packaging-only overhead is zero at runtime
**Constraints**: Immutable PyPI identities; exact trusted-publisher repository binding; automated version bumps only; one final old-name release; no internal identifier rewrite
**Scale/Scope**: One distribution metadata switch, two entry points, 47 distinct versioned schema IDs, hundreds of existing tests, staged GitHub/PyPI operations

## Constitution Check

*GATE: Passed before and after design.*

- **Public Core boundary**: No Runtime interaction changes; public CLI/release contracts remain the only boundary.
- **Project-local workspace portability**: `.verifysignal/`, schemas, and manifest interpretation remain unchanged and receive explicit compatibility tests.
- **Secret safety**: No secret inputs or storage change; full secret-safety regressions remain mandatory.
- **Agent-neutral interface**: Canonical `verifysignal` CLI remains the source of truth; legacy and current integrations remain adapters.
- **Testable spec-driven delivery**: Each behavior starts with a focused failing test; packaging, metadata, CLI, compatibility, build, isolated install, full pytest, Docker, and release smoke evidence cover the cutover.
- No new dependency, schema, storage, service, or private Runtime import is introduced.

## Project Structure

### Documentation (this feature)

```text
specs/027-rename-public-interface/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── public-identity-compatibility.md
│   └── release-cutover.md
├── checklists/requirements.md
└── tasks.md
```

### Source Code (repository root)

```text
pyproject.toml
README.md
CHANGELOG.md
docs/
├── installation.md
└── release-readiness.md
.github/workflows/
├── release.yml
└── version-bump.yml
src/verifysignal_spec/
├── repos.py
├── cli.py
├── integrations/
└── templates/
tests/
├── contract/
├── integration/
└── unit/
```

**Structure Decision**: Keep the existing import/source tree and versioned artifacts. Change distribution metadata and active public prose narrowly, add additive sibling aliases, and protect the intentionally retained identifiers with contract tests.

## Release and Branch Sequence

1. `fix/announce-verifysignal-distribution` from current main: red migration-notice contract, green notice, focused/full tests, PR title `fix: announce the verifysignal distribution migration`; merge and verify automated 0.22.1.
2. Manual gate: create pending PyPI trusted publisher for project `verifysignal`, owner `RigelRise`, repository `verifysignal-spec`, workflow `release.yml`, environment `pypi`.
3. `027-rename-public-interface`: include the notice commit, red packaging/compatibility tests, green canonical distribution and public wording, build/isolated/full regression; PR title `feat: publish the canonical verifysignal distribution`; merge and verify automated 0.23.0.
4. Manual gate: rename GitHub repository to `RigelRise/verifysignal`, retain old redirect, and add the exact new trusted publisher binding.
5. `fix/canonical-verifysignal-repository`: red repository/workflow metadata tests, green canonical URLs/publisher instructions, full regression; PR title `fix: canonicalize renamed repository publishing`; merge and verify automated 0.23.1 before removing the old binding.

## Compatibility Freeze List

- Python import `verifysignal_spec`
- CLI commands `verifysignal` and `verifysignal-spec`
- all `verifysignal-spec-*/v1` identifiers
- `.verifysignal/`
- `VERIFYSIGNAL_SPEC_*`
- workflow role `spec`
- `/verifysignal-specify`
- public legacy `verifysignal-spec` and `verifysignal-spec-*` integration/skill aliases

## Complexity Tracking

No constitution violations require justification. The staged release sequence is required by immutable PyPI project identity and exact trusted-publisher bindings, not by a new application abstraction.
