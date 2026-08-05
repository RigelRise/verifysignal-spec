# Implementation Plan: Entitlement Preflight Recovery

**Branch**: `028-entitlement-preflight-recovery` | **Date**: 2026-08-05 | **Spec**: [spec.md](spec.md)
**Input**: Confirmed diagnosis in [diagnosis.md](diagnosis.md) and the approved
Core/Spec recovery plan.

## Summary

Make fresh runtime selection intentional, split readiness into compatibility,
trust-input, and protected-operation proof, normalize all protected Core outcomes
at one public-contract boundary, and prevent any blocked preflight or Core error
from becoming a synthetic browser run. Direct run and workflow check will share
one pure decision engine; rerun/confirmation state will use the same authority;
WorkflowRun will become the source for every rendered workflow projection.

The implementation is additive for persisted v1 schemas and older Core error
envelopes. It intentionally changes only one earlier runtime behavior:
successful explicit `init --core-cmd` now persists development override, matching
explicit `core setup --core-cmd`. No dependency, backend production change,
manual version bump, or private Core access is introduced.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: Existing Typer, Rich, PyYAML, Pydantic, pathspec,
packaging, cryptography, and tomlkit dependencies; no new dependency
**Storage**: Project-local YAML/JSON/Markdown under `.verifysignal/`
**Testing**: pytest unit, contract, integration, Docker regression, and pinned
Core/Spec/backend product-truth journeys
**Target Platform**: Cross-platform CLI on Linux, macOS, and Windows
**Project Type**: Python CLI and coding-agent interface
**Performance Goals**: A blocked run preflight performs zero Core/runtime work;
existing list/readiness overhead remains within its 50 ms representative test
budget; entitlement checks retain existing Core-side performance gates
**Constraints**: Public Core CLI JSON only; fail closed on unknown schema; no
secret persistence; additive workspace compatibility; red/green TDD before
production edits; no version hand-edit
**Scale/Scope**: Four user stories across runtime selection/readiness, Core
outcome normalization, run/rerun lifecycle, and workflow persistence

## Constitution Check

### Pre-design gate

- **Public Core boundary — PASS**: The design consumes advertised operation
  schemas plus `verifysignal.error/v1`; no private package or report field is
  required.
- **Project-local workspace portability — PASS**: All persisted changes stay in
  existing `.verifysignal/` records and have legacy read rules.
- **Secret safety — PASS**: Normalization keeps only schema, status, blocker code,
  and execution classification. Canary and non-persistence tests are mandatory.
- **Agent-neutral interface — PASS**: CLI and both agent adapters consume the
  same preflight, readiness, and workflow-state projections.
- **Testable spec-driven delivery — PASS**: Prioritized stories, interface
  contracts, red/green tasks, migrations, and cross-repository validation are
  specified before implementation.

### Post-design gate

All five gates remain **PASS** after research and contract design. The additive
schema policy, unknown-schema fail-closed behavior, transient-artifact ownership,
and lazy migration rules are explicit in the contracts. No constitutional
exception or complexity waiver is needed.

## Project Structure

### Documentation (this feature)

```text
specs/028-entitlement-preflight-recovery/
├── diagnosis.md
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── runtime-mode-readiness.md
│   ├── core-outcome.md
│   ├── run-preflight-rerun.md
│   └── workflow-run.md
├── checklists/requirements.md
└── tasks.md
```

### Source Code (repository root)

```text
.dockerignore

src/verifysignal_spec/
├── commands/                 # init, validate, run, workflow command adapters
├── core/                     # public Core adapter, contracts, outcome normalizer
├── runtime/                  # resolution policy and managed readiness
├── workflows/                # shared run preflight, rerun policy, transitions
└── workspace/                # additive persisted models and repository operations

tests/
├── unit/                     # pure outcome, preflight, policy, transition tests
├── contract/                 # CLI/schema/backward-compatibility contracts
├── integration/              # workspace, Core invocation, and persistence journeys
└── fixtures/                 # production-shaped public Core outcomes/workspaces
```

**Structure Decision**: Keep the existing single-package architecture. Add
`core/outcomes.py`, `workflows/run_preflight.py`, and
`workflows/transitions.py` as pure policy boundaries; command modules remain
thin orchestration adapters. Extend existing model/repository modules rather
than introducing a second persistence system.

## Implementation Design

### 1. Runtime mode and layered readiness

- Stamp `managed-only` only when initialization creates a genuinely new
  workspace. Field-absent records that existed before the command remain
  `legacy-auto`; repeated init must not silently migrate them.
- Treat successful explicit `init --core-cmd` and `core setup --core-cmd` as an
  intentional `development-override`. Invocation failure must not persist the
  override.
- Keep managed-only resolution hermetic to verified managed candidates. Surface
  effective mode/source through current JSON projections.
- Extend `ReadinessSnapshot` v1 and runtime-readiness projections with the four
  additive fields in [runtime-mode-readiness.md](contracts/runtime-mode-readiness.md).
  Legacy missing fields decode conservatively as protected `not-checked`.
- Validation writes `protectedOperationStatus: passed` only after a schema-valid
  protected authoring check passes; any normalized blocker writes `blocked`.

### 2. Schema-aware Core outcome boundary

- Add `core/outcomes.py` with an operation-to-success-schema table and one
  `normalize_core_outcome(operation, response)` function. It returns a typed,
  redacted normalized outcome and never persists the raw response.
- Accept the exact operation success schema or `verifysignal.error/v1`. Read
  top-level `error.code` first and legacy `data.findings[].code` second. Anything
  else becomes `core.contract-invalid`.
- Preserve explicit Core execution classification. Missing metadata stays
  unknown; an error envelope is never eligible for browser-run persistence.
- Route validate and run through the normalizer before readiness, history,
  coverage, first-run, confirmation, repair, or WorkflowRun mutation.

### 3. One run preflight, one rerun authority

- Add a pure `workflows/run_preflight.py` decision builder used by both
  `workflow check run` and `commands.run`. It receives loaded metadata only and
  returns the contract in [run-preflight-rerun.md](contracts/run-preflight-rerun.md).
- Evaluate the decision before runtime resolution, environment loading,
  generated input resolution, prepared request creation, or Core invocation.
- Make `evaluate_rerun_decision()` classify the previous real outcome as
  no-commit, commit, or genuinely unknown and consume the corresponding policy
  branch. Eliminate the independent legacy unknown-status gate.
- Reconcile the active confirmation artifact from that same decision on every
  preflight/list projection: replace a changed gate, remove a resolved gate, and
  preserve supersede reviews separately.
- Persist browser-run state only for a schema-valid `verifysignal.run/v1`.
  Track whether the invocation created its exact prepared-request file and remove
  only that file after a Core error. Never change prior run/evidence/repair state
  for an error envelope.
- Persist a redacted `lastCoreAttempt` for Core errors. Explicit
  `started: false`/`sideEffectMayExist: false` records `not-started`; missing or
  unsafe execution metadata records `unknown`. The marker is not RunHistory but
  participates in the next rerun/confirmation decision and is cleared by a later
  valid run result.

### 4. WorkflowRun-authoritative transitions

- Add `workflows/transitions.py` with a single transition function that loads or
  lazily creates the active WorkflowRun, updates one stage, writes WorkflowRun
  as the authority, then derives the use-case reference and rendered state.
- Render stage state only from the updated WorkflowRun. Stage persistence must
  not call `state_document()` without a run.
- Use the transition boundary from authored-stage persistence, protected
  validation, and real run handling. Follow the transition table in
  [workflow-run.md](contracts/workflow-run.md).
- Lazy migration is triggered only during a mutating workflow persistence call,
  is idempotent, infers completed stages from durable documents, and copies any
  existing target confirmation into the new run.
- Multi-file projection is coordinated but not transactionally atomic. Every
  mutating transition compares projections with WorkflowRun and heals an
  interrupted update; read-only surfaces render from WorkflowRun without writes.

## Compatibility and Migration

- Do not rename or version-bump existing workspace schemas. New readiness fields
  are optional on read and always emitted on new writes.
- Preserve `legacy-auto` for an already-existing field-absent workspace.
  Distinguish it from a newly created record before writing defaults.
- Preserve older public Core errors without `execution`; classify execution as
  unknown and block without synthesizing a run.
- Preserve legacy findings mapping only when no top-level public error code is
  available. Top-level public data always wins.
- Preserve all previous real run history, evidence references, repair sessions,
  supersede reviews, and target confirmation through migrations and blocked
  outcomes. Core errors may update only `lastCoreAttempt` and its derived active
  confirmation gate.
- No data-wide migration command is required. WorkflowRun migration happens
  lazily at the next workflow write, and readiness fields upgrade at the next
  validation write.

## TDD and Delivery Sequence

1. Record baseline focused and full-suite results without changing production.
2. For each user story, add production-shaped regression tests and run them to
   the expected diagnosed failure; commit the red tests separately.
3. Implement the smallest coherent policy/model changes to make that story
   green; run adjacent regression tests before refactoring.
4. Run the full Spec suite, then pinned Docker verification and browser
   product-truth against the companion Core worktree.
5. Reproduce the localized-home case in an isolated workspace, including a
   forced entitlement-error control that must leave zero run artifacts.
6. Rebase and rerun before opening the PR. Windows remains a required CI gate.

The expected Spec release class is **patch**, declared by PR title
`fix: preserve protected preflight without synthetic runs`. Version files remain
untouched in the PR.

## Complexity Tracking

No constitution violations or avoidable architecture exceptions are required.
