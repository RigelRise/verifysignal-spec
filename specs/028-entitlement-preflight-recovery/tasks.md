# Tasks: Entitlement Preflight Recovery

**Input**: Design documents from `specs/028-entitlement-preflight-recovery/`
**Prerequisites**: `spec.md`, `plan.md`, `research.md`, `data-model.md`, and all
files under `contracts/`
**Tests**: Required. Every story uses red/green TDD and must retain the failing
red checkpoint before production changes.

**Organization**: Tasks are grouped by independently testable user story. The
companion Core PR supplies current-envelope execution metadata; this repository
must remain compatible with older envelopes that omit it.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel because it touches different files and has no
  dependency on an unfinished task.
- **[Story]**: Maps the task to a user story in `spec.md`.
- Every task names the exact file or directory it changes or validates.

## Phase 1: Setup and Baseline

**Purpose**: Preserve diagnostic evidence and establish the pre-change baseline.

- [X] T001 Create/verify Python/Docker exclusions in `.dockerignore`, run the focused baseline commands, and retain counts for PR evidence using `specs/028-entitlement-preflight-recovery/quickstart.md`
- [X] T002 [P] Add current, legacy, malformed, and operation-mismatched public Core response modes in `tests/fixtures/verifysignal-core/fake_verifysignal.py`
- [X] T003 [P] Add fresh/legacy workspace, protected-readiness, and side-effect-policy builders in `tests/fixtures/workflows/entitlement_preflight_recovery.py`
- [X] T004 [P] Add exact path-ownership and full-workspace secret-canary helpers in `tests/helpers.py`
- [X] T005 Validate fixture outputs contain public codes and metadata but no raw receipt, key, signature, credential, or environment values in `tests/fixtures/verifysignal-core/fake_verifysignal.py`

---

## Phase 2: Documentation and Contract Gate

**Purpose**: Block implementation until the approved artifacts are internally
consistent.

- [X] T006 Run `/speckit-analyze` across `specs/028-entitlement-preflight-recovery/spec.md`, `plan.md`, `contracts/`, and `tasks.md`
- [X] T007 Resolve every Critical or High analysis finding without expanding the exclusions in `specs/028-entitlement-preflight-recovery/spec.md`
- [X] T008 Confirm the companion Core contract exposes additive `execution` metadata and no private-Core dependency is assumed in `specs/028-entitlement-preflight-recovery/contracts/core-outcome.md`

**Checkpoint**: No Critical/High artifact finding remains; production code is
still unchanged.

---

## Phase 3: User Story 1 - Intentional Runtime Selection (Priority: P1) 🎯 MVP

**Goal**: New workspaces are managed-only, legacy absence remains legacy, and
explicit local setup persists development override.

**Independent Test**: With local Core candidates in every discovery source, a
new workspace ignores them, a pre-existing field-absent workspace retains
legacy-auto, and successful explicit setup persists development-override.

### Red tests for User Story 1

- [X] T009 [P] [US1] Add failing fresh-versus-legacy initialization cases in `tests/integration/test_fresh_workspace_runtime_mode.py`
- [X] T010 [P] [US1] Add failing managed-only candidate-exclusion cases in `tests/unit/test_runtime_resolver.py`
- [X] T011 [P] [US1] Add failing explicit `init --core-cmd` persistence and setup-failure preservation cases in `tests/contract/test_cli_init_check_contract.py`
- [X] T012 [US1] Run the US1 focused tests, confirm the diagnosed red failures, and commit the failing assertions before production edits in `tests/integration/test_fresh_workspace_runtime_mode.py`

### Implementation for User Story 1

- [X] T013 [US1] Distinguish new creation from existing field absence and stamp managed-only only for new workspaces in `src/verifysignal_spec/workspace/repository.py`
- [X] T014 [US1] Persist development override only after successful explicit init Core setup in `src/verifysignal_spec/commands/init.py`
- [X] T015 [US1] Align explicit setup persistence and failure rollback with init semantics in `src/verifysignal_spec/commands/core_setup.py`
- [X] T016 [US1] Enforce managed-only exclusion for workspace, environment, PATH, and ancestor-sibling candidates in `src/verifysignal_spec/runtime/resolver.py`
- [X] T017 [US1] Run US1 tests to green and retain red/green SHAs using `tests/integration/test_fresh_workspace_runtime_mode.py`
- [X] T018 [US1] Run adjacent reset/update/setup and legacy compatibility regression suites in `tests/integration/test_core_update.py` and `tests/integration/test_core_setup.py`

**Checkpoint**: User Story 1 passes independently without a protected Core call.

---

## Phase 4: User Story 2 - Truthful Protected Readiness (Priority: P1)

**Goal**: Readiness states what it proves and all protected Core outcomes cross
one schema-aware, secret-safe boundary.

**Independent Test**: Current error, older error without execution metadata,
legacy findings, wrong schema, protected pass, and protected block each produce
the exact layered readiness and normalized outcome defined by the contracts.

### Red tests for User Story 2

- [X] T019 [P] [US2] Add failing operation/schema, top-level-code precedence, legacy fallback, and execution-metadata unit cases in `tests/unit/test_core_outcome_normalization.py`
- [X] T020 [P] [US2] Add failing layered readiness and legacy snapshot decoding cases in `tests/integration/test_protected_readiness_scope.py`
- [X] T021 [P] [US2] Add failing public schema, additive field, and `core.contract-invalid` assertions in `tests/contract/test_entitlement_preflight_recovery_contract.py`
- [X] T022 [P] [US2] Add failing normalized-output and readiness secret-canary cases in `tests/integration/test_runtime_secret_safety.py`
- [X] T023 [US2] Run the US2 focused tests, confirm the diagnosed red failures, and commit them before editing production files in `tests/unit/test_core_outcome_normalization.py`

### Implementation for User Story 2

- [X] T024 [US2] Implement the redacted operation-aware normalized outcome model and exact schema table in `src/verifysignal_spec/core/outcomes.py`
- [X] T025 [US2] Route top-level error codes first, retain findings fallback, and centralize safe blocker mapping in `src/verifysignal_spec/core/contracts.py`
- [X] T026 [US2] Add readiness component fields with conservative legacy defaults in `src/verifysignal_spec/workspace/models.py` and `src/verifysignal_spec/workflows/models.py`
- [X] T027 [US2] Populate command, trust, protected, and scope states during runtime resolution in `src/verifysignal_spec/runtime/resolver.py`
- [X] T028 [US2] Normalize authoring-check before readiness/persistence and block unknown schemas in `src/verifysignal_spec/commands/validate.py`
- [X] T029 [US2] Replace onboarding language that conflates trust inputs with protected readiness in `src/verifysignal_spec/workflows/core_setup.py` and `src/verifysignal_spec/templates/agent_guidance.py`
- [X] T030 [US2] Run US2 tests to green and retain red/green SHAs using `tests/integration/test_protected_readiness_scope.py`
- [X] T031 [US2] Run adjacent adapter, entitlement, readiness, and public-boundary suites in `tests/unit/test_core_adapter.py`, `tests/unit/test_runtime_readiness.py`, and `tests/contract/test_core_public_boundary_contract.py`

**Checkpoint**: A protected pass is distinguishable from compatible inputs, and
no Core error is eligible for run persistence.

---

## Phase 5: User Story 3 - Safe Run and Authoritative Rerun (Priority: P1)

**Goal**: Workflow check and direct run agree before runtime work; only real run
schemas create run history; unknown legacy attempts remain non-run state but
conservatively drive `afterUnknown` for write reruns.

**Independent Test**: The prerequisite/rerun matrix yields the same decision
from both entry points, invokes Core only when ready, and proves current and
legacy error envelopes create no synthetic run or collateral file deletion.

### Red tests for User Story 3

- [X] T032 [P] [US3] Add failing direct-run/workflow-check decision parity and zero-Core-invocation cases in `tests/unit/test_run_preflight.py`
- [X] T033 [P] [US3] Add failing current/legacy Core error, `lastCoreAttempt`, zero-RunHistory, and prior-state preservation cases in `tests/integration/test_preexecution_run_lifecycle.py`
- [X] T034 [P] [US3] Add failing no-run, no-commit, commit, unknown-write, non-write, and historical-write matrix cases in `tests/integration/test_rerun_policy_authority.py`
- [X] T035 [P] [US3] Add failing stale-create/replace/delete active confirmation cases in `tests/integration/test_confirmation_reconciliation.py`
- [X] T036 [P] [US3] Add failing exact-new-file cleanup, neighbor preservation, outside-workspace refusal, and secret-canary cases in `tests/integration/test_prepared_request_error_cleanup.py`
- [X] T037 [US3] Run the US3 focused tests, confirm each diagnosed red failure, and commit them before production edits in `tests/integration/test_preexecution_run_lifecycle.py`

### Implementation for User Story 3

- [X] T038 [US3] Add redacted additive `LastCoreAttempt` parsing/serialization to `UseCaseRecord` in `src/verifysignal_spec/workspace/models.py`
- [X] T039 [US3] Add safe save/replace/clear helpers for `lastCoreAttempt` and active confirmations in `src/verifysignal_spec/workspace/repository.py`
- [X] T040 [US3] Implement the pure shared prerequisite decision in `src/verifysignal_spec/workflows/run_preflight.py`
- [X] T041 [US3] Delegate workflow run checks to the shared preflight decision in `src/verifysignal_spec/workflows/prerequisites.py`
- [X] T042 [US3] Classify newer non-run attempts and select exactly one rerun-policy branch in `src/verifysignal_spec/workflows/write_safety.py`
- [X] T043 [US3] Reconcile create/replace/delete active gates exclusively from the authoritative decision in `src/verifysignal_spec/workspace/repository.py`
- [X] T044 [US3] Invoke preflight before runtime/environment/preparation and normalize Core output before persistence in `src/verifysignal_spec/commands/run.py`
- [X] T045 [US3] Persist/clear `lastCoreAttempt`, permit RunHistory only for valid `verifysignal.run/v1`, and preserve all prior real state in `src/verifysignal_spec/commands/run.py`
- [X] T046 [US3] Return exact prepared-request ownership and delete only a newly created project-owned file on Core error in `src/verifysignal_spec/commands/run_request_preparation.py` and `src/verifysignal_spec/commands/run.py`
- [X] T047 [US3] Project the authoritative rerun/confirmation decision in `src/verifysignal_spec/workspace/repository.py` without trusting stale files; retain `src/verifysignal_spec/commands/list.py` as the unchanged consumer
- [X] T048 [US3] Run US3 tests to green and retain red/green SHAs using `tests/integration/test_rerun_policy_authority.py`
- [X] T049 [US3] Run adjacent CLI run, run-record/replay, write-safety, policy migration, and confirmation contract suites in `tests/contract/test_cli_run_contract.py`, `tests/integration/test_run_record_replay.py`, and `tests/integration/test_write_flow_rerun_guardrails.py`

**Checkpoint**: Current pre-execution errors are safe no-commit attempts; legacy
unknown write attempts require the configured `afterUnknown` decision without
becoming browser runs.

---

## Phase 6: User Story 4 - WorkflowRun-Authoritative Recovery (Priority: P1)

**Goal**: Every stage update derives projections from WorkflowRun, legacy state
migrates lazily, and interrupted multi-file projection writes heal on the next
mutating transition while read-only surfaces remain non-mutating.

**Independent Test**: Persist and block every relevant stage, simulate stale or
missing projections after a newer WorkflowRun, and assert all projections heal
without losing completed stages or target confirmation.

### Red tests for User Story 4

- [ ] T050 [P] [US4] Add failing authored-stage, validate-pass/block, real-run-pass/fail, and Core-error transition cases in `tests/integration/test_workflow_run_state_authority.py`
- [ ] T051 [P] [US4] Add failing lazy migration, idempotence, target-confirmation preservation, and interrupted-projection healing cases in `tests/unit/test_workflow_repository.py`
- [ ] T052 [US4] Run the US4 focused tests, confirm the all-pending/divergent-state red failures, and commit them before production edits in `tests/integration/test_workflow_run_state_authority.py`

### Implementation for User Story 4

- [ ] T053 [US4] Implement authoritative stage transitions, lazy migration, and projection healing in `src/verifysignal_spec/workflows/transitions.py`
- [ ] T054 [US4] Render state only from a loaded/updated WorkflowRun and expose projection comparison helpers in `src/verifysignal_spec/workflows/repository.py`
- [ ] T055 [US4] Route specify/clarify/plan/tasks/implement persistence through the transition boundary in `src/verifysignal_spec/workflows/stage_persistence.py`
- [ ] T056 [US4] Route protected validation pass/block through WorkflowRun transitions in `src/verifysignal_spec/commands/validate.py`
- [ ] T057 [US4] Route only valid real run pass/fail through executed-run transitions and keep Core errors at a blocked, unexecuted `run` stage in `src/verifysignal_spec/commands/run.py`
- [ ] T058 [US4] Run US4 tests to green and retain red/green SHAs using `tests/integration/test_workflow_run_state_authority.py`
- [ ] T059 [US4] Run canonical persistence, stage contract, target confirmation, repair, and agent handoff regressions in `tests/integration/test_workflow_canonical_persistence.py`, `tests/contract/test_workflow_stage_persistence_contract.py`, and `tests/integration/test_workflow_target_confirmation.py`

**Checkpoint**: WorkflowRun is authoritative and projection recovery is
explicitly healable, not falsely described as crash-atomic.

---

## Phase 7: Full Regression and PR Evidence

**Purpose**: Prove the two-repository recovery without hidden sibling selection,
secret leakage, or platform regression.

- [ ] T060 Run the complete local Spec suite with `python -m pytest -q` from the repository root
- [ ] T061 [P] Run secret-canary, representative list-performance, and runtime-readiness performance regressions in `tests/integration/test_runtime_secret_safety.py`, `tests/integration/test_list_performance.py`, and `tests/integration/test_managed_runtime_performance.py`
- [ ] T062 Execute every acceptance row and capture non-sensitive evidence using `specs/028-entitlement-preflight-recovery/quickstart.md`
- [ ] T063 Run the Spec Docker suite with explicit Core, Spec, and backend pins using `scripts/verify-docker.sh`
- [ ] T064 Run the companion Core Docker and full local gates using `../verifysignal-entitlement-preflight-recovery/scripts/verify-docker.sh`
- [ ] T065 Run pinned browser smoke and customer-journey composition using `../verifysignal-entitlement-preflight-recovery/package.json`
- [ ] T066 Re-run the localized-home positive path and current/legacy forced-error controls in an isolated Rigel Rise workspace using `specs/028-entitlement-preflight-recovery/quickstart.md`
- [ ] T067 Confirm Windows remains a required green CI job in `.github/workflows/ci.yml`
- [ ] T068 Re-run `/speckit-analyze` and resolve all Critical/High findings in `specs/028-entitlement-preflight-recovery/`
- [ ] T069 Rebase on current `origin/main`, rerun focused and full suites, and record the final base SHA in the pull-request evidence without making the reusable `specs/028-entitlement-preflight-recovery/quickstart.md` stale
- [ ] T070 Open the cross-linked `fix: preserve protected preflight without synthetic runs` PR with red/green SHAs, test counts, compatibility matrix, and journey evidence using `.github/pull_request_template.md`

---

## Dependencies & Execution Order

### Phase dependencies

- **Setup (Phase 1)**: Starts immediately.
- **Contract gate (Phase 2)**: Depends on Phase 1 and blocks production edits.
- **US1 and US2 (Phases 3–4)**: May start in parallel after Phase 2 because their
  primary production files differ, but both must preserve the shared workspace
  compatibility rules.
- **US3 (Phase 5)**: Depends on US2's normalized outcome/readiness model; its
  runtime-selection regressions also run against US1.
- **US4 (Phase 6)**: Depends on US3's distinction between real run and non-run
  attempt.
- **Regression/PR (Phase 7)**: Depends on every selected story being green.

### Within each story

1. Fixture support may be prepared.
2. Product-shaped tests are written and run red.
3. The red assertions are committed before production code.
4. Minimum implementation turns the focused suite green.
5. Adjacent regression runs before refactor or story completion.

## Parallel Opportunities

- T002, T003, and T004 can run concurrently.
- US1 test files T009–T011 can be authored concurrently.
- US2 test files T019–T022 can be authored concurrently.
- US3 test files T032–T036 can be authored concurrently before T037.
- US4 transition and migration tests T050–T051 can be authored concurrently.
- Final secret/performance checks can run alongside independent documentation
  evidence collection, but Docker/browser jobs should be serialized if they
  share ports or managed runtime caches.

## Parallel Example: User Story 3

```text
Task T032: direct-run/workflow-check parity tests
Task T033: current/legacy Core error and lastCoreAttempt tests
Task T034: rerun-policy authority matrix
Task T035: confirmation reconciliation tests
Task T036: exact prepared-request cleanup and secret tests
```

Merge these red tests first; then execute T038–T047 in dependency order.

## Implementation Strategy

### Safe incremental delivery

1. Deliver US1 runtime intent and verify legacy compatibility.
2. Deliver US2 outcome/readiness truth and verify public-boundary safety.
3. Deliver US3 shared preflight, attempt marker, rerun authority, and real-run-only
   persistence.
4. Deliver US4 WorkflowRun authority and healing.
5. Run full pinned composition and open the PR only after all checkpoints pass.

### Merge sequence

1. Merge the companion Core PR first after its CI and patch release.
2. Rebase Spec on current main and test against the published Core.
3. Merge Spec only after Spec CI, Windows, sibling dispatch, and composed
   product-truth are green.

## Notes

- Do not hand-edit `pyproject.toml`, `src/verifysignal_spec/__init__.py`, or
  `CHANGELOG.md`; the `fix:` PR title declares patch release intent.
- Do not create a backend branch or production-code change.
- Do not weaken existing assertions to obtain green results.
- Do not persist raw Core responses or paths in `lastCoreAttempt`.
- Do not call the WorkflowRun/projection update transactionally atomic; prove
  authority and healing instead.
