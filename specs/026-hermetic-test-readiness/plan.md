# Implementation Plan: Hermetic Update and Test Readiness

**Branch**: `026-hermetic-test-readiness` | **Date**: 2026-07-26  
**Spec**: `specs/026-hermetic-test-readiness/spec.md`

## Summary

Add a managed-only Core resolution path with explicit reset/update commands,
make browser target confirmation a workflow-run-scoped user decision, and add a
strict opt-in test environment file that carries only declared runtime keys to
Core child processes. Core itself does not change.

## Technical Context

- **Language**: Python 3.11+
- **CLI**: Typer/argparse-compatible command dispatcher in
  `src/verifysignal_spec/cli.py`
- **Models**: Pydantic/dataclasses and YAML/JSON workspace repositories
- **Tests**: pytest unit, contract, integration, and cross-repository dogfood
- **Storage**: `.verifysignal/` for non-secret state; explicit Git-ignored
  dotenv file for secret test values; verified managed cache outside workspace
- **Dependency decision**: use Python standard library for strict dotenv
  parsing; do not introduce executable shell loading or a new package
- **Version**: backward-compatible public capabilities require
  `0.20.0` → `0.21.0`

## Constitution Check

| Principle | Design response |
|---|---|
| Public Core Boundary | All execution remains through Core CLI JSON; update uses the existing signed distribution contract. |
| Workspace Portability | New mode and run-scoped confirmation are additive fields with legacy defaults. |
| Secret Safety | No implicit dotenv reads; strict allowlist, permissions, Git exclusion, and redaction. |
| Agent-Neutral Interface | Shared CLI and templates drive Codex and Claude behavior. |
| Testable Spec-Driven Delivery | Contracts and tasks precede code; focused red/green and structural dogfood are required. |

No constitutional violations are required.

## Project Structure

```text
src/verifysignal_spec/
├── cli.py
├── commands/
│   ├── core_runtime.py
│   └── credentials.py
├── runtime/
│   ├── env_file.py
│   └── resolver.py
├── workflows/
│   ├── core_setup.py
│   ├── stage_persistence.py
│   ├── prerequisites.py
│   └── target_confirmation.py
└── workspace/
    ├── models.py
    └── repository.py

tests/
├── contract/
├── integration/
└── unit/
```

## Design

### Managed Core lifecycle

`core reset` atomically removes persisted local command/source/version fields
and stores `coreResolutionMode: managed-only`. `core update` performs reset
first, requests managed latest without consulting local candidates or version
pins, reuses only an exact verified cache hit, otherwise downloads and verifies
the release. Managed metadata records active version and timestamps separately
from development override fields. A failed update may restore only the previous
verified managed cache selection.

Resolver behavior remains `legacy-auto` when the field is absent. Explicit
per-command `--core-cmd` remains highest priority for that invocation.
`core setup --core-cmd` persists `development-override`.

`integration upgrade` renders files from stored state and emits a stable
`not-checked` Core status without calling resolution or setup.

### Target confirmation

Repository and prior-workflow URLs become `AuthoringQuestion` suggestions with
source metadata. Only clarification persisted with `direct-user` or
`explicit-command` provenance records confirmation on the active
`WorkflowRun`. Specification, plan, and implementation persistence cannot
answer the question. Browser prerequisites check the active run and return the
named structured blocker until confirmation exists.

### Credential preparation

The preparation command derives an exact environment key allowlist from the
registered use case. It resolves `.git/info/exclude`, proves the target path is
excluded, creates/updates the file with mode `0600`, preserves existing
declared assignments, and appends missing `KEY=` declarations. It blocks before
the dotenv write when safety cannot be guaranteed.

The loader accepts comments, blank lines, optional `export`, and single-line
quoted or unquoted values. It rejects duplicate/undeclared keys, interpolation,
command substitution, backticks, multiline syntax, invalid identifiers, and
unsafe permissions. It returns a child-process-only mapping; the adapter's
existing environment merge gives explicit file values precedence without
mutating `os.environ`.

### Structural red/green

A loopback fixture exposes the authenticated create-project structure without
names, URLs, or visual identity from any real product. It also places a
discoverable fake local Core near the workspace. The dogfood proves update
selects managed Core, suggested target blocks, explicit staging-like loopback
confirmation unblocks, exact keys guide preparation, probe commits zero
resources, and one authorized run commits one.

## Delivery Phases

1. Contract artifacts and red tests.
2. Hermetic Core reset/update and pure integration upgrade.
3. Workflow-scoped target confirmation.
4. Secure environment preparation and CLI propagation.
5. Shared agent guidance and compatibility regressions.
6. Version bump, full suite, and cross-repository dogfood.

## Validation Commands

```bash
pytest -q tests/integration/test_core_update.py
pytest -q tests/integration/test_workflow_target_confirmation.py
pytest -q tests/unit/test_env_file.py tests/integration/test_credentials_prepare.py
pytest -q tests/integration/test_authenticated_project_dogfood.py
pytest -q
```

## Complexity Tracking

No exception is requested. Managed runtime fallback reuses the existing signed
cache model; target confirmation reuses workflow entities; credential handling
uses a small strict parser rather than general dotenv semantics.
