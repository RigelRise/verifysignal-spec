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
- [X] T008 Confirm the companion Core contract exposes additive `execution` metadata, keeps its entitlement operation policy deeply immutable, and requires no private-Core dependency in `specs/028-entitlement-preflight-recovery/contracts/core-outcome.md`

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

- [X] T019 [P] [US2] Add failing operation/schema, top-level-code precedence, exact entitlement-only pre-execution tuple, contradictory/non-entitlement execution-metadata, current `data.summary.runId`, legacy `data.runId`, conflicting-identity, and portable public-run-ID unit cases in `tests/unit/test_core_outcome_normalization.py` and `tests/unit/test_workspace_layout_portability.py`
- [X] T020 [P] [US2] Add failing layered readiness and legacy snapshot decoding cases in `tests/integration/test_protected_readiness_scope.py`
- [X] T021 [P] [US2] Add failing public schema, additive field, and `core.contract-invalid` assertions in `tests/contract/test_entitlement_preflight_recovery_contract.py`
- [X] T022 [P] [US2] Add failing normalized-output/readiness secret canaries and recursive secret-named/compound-container (including `apiToken`), nested-list/cycle/deep-input, scheme-less/network-path/relative-query/prose/repeatedly-encoded URI-reference, provider/bracketed query-key, multiline-prose, short Bearer/verified Basic, base64/base64url, and shape-validated public-container boundary cases in `tests/integration/test_runtime_secret_safety.py` and `tests/unit/test_workflow_secret_safety.py`
- [X] T023 [US2] Run the US2 focused tests, confirm the diagnosed red failures, and commit them before editing production files in `tests/unit/test_core_outcome_normalization.py`

### Implementation for User Story 2

- [X] T024 [US2] Implement the redacted operation-aware normalized outcome model, exact schema table, entitlement-only exact pre-execution proof, and unambiguous current/legacy run-identity parsing in `src/verifysignal_spec/core/outcomes.py`
- [X] T025 [US2] Route top-level error codes first, retain findings fallback, and centralize safe blocker mapping in `src/verifysignal_spec/core/contracts.py`
- [X] T026 [US2] Add readiness component fields with conservative legacy defaults in `src/verifysignal_spec/workspace/models.py` and `src/verifysignal_spec/workflows/models.py`
- [X] T027 [US2] Populate command, trust, protected, and scope states during runtime resolution in `src/verifysignal_spec/runtime/resolver.py`
- [X] T028 [US2] Normalize authoring-check before readiness/persistence and block unknown schemas in `src/verifysignal_spec/commands/validate.py`
- [X] T029 [US2] Replace onboarding language that conflates trust inputs with protected readiness in `src/verifysignal_spec/workflows/core_setup.py` and `src/verifysignal_spec/templates/agent_guidance.py`
- [X] T030 [US2] Run US2 tests to green and retain red/green SHAs using `tests/integration/test_protected_readiness_scope.py`
- [X] T031 [US2] Thread the effective entitlement API endpoint through every protected source-adapter receipt/public-key handoff, then run adjacent adapter, entitlement, readiness, and public-boundary suites in `tests/unit/test_core_adapter.py`, `tests/unit/test_runtime_readiness.py`, and `tests/contract/test_core_public_boundary_contract.py`

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
Same-alias concurrency, stale-attempt CAS, backward clocks, malformed responses,
and crash-durable write ordering are included in the matrix.

### Red tests for User Story 3

- [X] T032 [P] [US3] Add failing direct-run/workflow-check decision parity and zero-Core-invocation cases in `tests/unit/test_run_preflight.py`
- [X] T033 [P] [US3] Add failing current/legacy Core error, write-ahead `lastCoreAttempt`, same-alias lease contention/recovery, exact-attempt CAS, backward-clock ordering, post-response/`record_run` failure, marker-clear ordering, immutable create-only RunHistory A,B,A reuse, canonical overlay/tombstone stale-writer recovery, sidecar-absent unique-newer-RunHistory recovery, timestamp-less-first-write refusal, newer/conflicting/unorderable base-or-RunHistory refusal, portable RunHistory identity/case-fold collision refusal, exact `lastRun` allowlist/recursive secret rejection, strict risk-field types/status tokens and intra-/cross-mapping contradiction refusal, corrupt/present-redirect authority refusal, zero-RunHistory, and prior-state preservation cases in `tests/integration/test_preexecution_run_lifecycle.py`, `tests/unit/test_canonical_run_authority.py`, `tests/unit/test_run_invocation_lock.py`, `tests/unit/test_durable_run_persistence.py`, `tests/unit/test_run_history_filename_portability.py`, and `tests/unit/test_authority_path_safety.py`
- [X] T034 [P] [US3] Add failing no-run, no-commit, commit, unknown-write, non-write, historical-write, explicit runtime-true-over-authored-none, explicit-runtime-true-over-contradictory-not-started, strongly-committed/reached-over-safe-claim, and unchanged-versus-exact-policy-change violation-reconciliation matrix cases in `tests/integration/test_rerun_policy_authority.py`, `tests/integration/test_read_only_policy_reconciliation.py`, and `tests/integration/test_guided_first_run_flow.py`
- [X] T035 [P] [US3] Add failing stale-create/replace/delete active confirmation cases in `tests/integration/test_confirmation_reconciliation.py`
- [X] T036 [P] [US3] Add failing exact-new-file cleanup, write-ahead-save failure before Core, contract-invalid conservative-true risk, neighbor preservation, outside-workspace refusal, handle-anchored pathname-replacement, and recursive/container/list/URI/public-exemption secret-canary cases in `tests/integration/test_prepared_request_error_cleanup.py` and `tests/unit/test_workflow_secret_safety.py`
- [X] T037 [US3] Run the US3 focused tests, confirm each diagnosed red failure, and commit them before production edits in `tests/integration/test_preexecution_run_lifecycle.py`

### Implementation for User Story 3

- [X] T038 [US3] Add redacted additive `LastCoreAttempt` parsing/serialization to `UseCaseRecord` in `src/verifysignal_spec/workspace/models.py`
- [X] T039 [US3] Add exact-attempt CAS, logical nanosecond ordering after prior evidence, canonical `.verifysignal/use-cases/<alias>.run-authority.json` overlay/null-tombstone semantics, sidecar-absent unique-newer-RunHistory recovery and timestamp-less-first-write refusal, exact `lastRun` allowlist plus iterative fail-closed compound-container/list/URI-reference (including embedded/repeatedly-encoded prose)/Bearer/Basic/base64 secret validation with shape-checked public exemptions, strict risk type/token (including raw `sideEffects.status`) and cross-mapping coherence validation, portable component validation and RunHistory case-fold sibling refusal, fail-closed reconciliation of newer/conflicting/unorderable base YAML or RunHistory, immutable native no-replace RunHistory creation, and crash-durable authority/history/projection/clear ordering in `src/verifysignal_spec/workspace/layout.py`, `src/verifysignal_spec/workspace/path_safety.py`, `src/verifysignal_spec/workspace/secret_safety.py`, `src/verifysignal_spec/workspace/repository.py`, `src/verifysignal_spec/workspace/time_ordering.py`, and `src/verifysignal_spec/workspace/textio.py`
- [X] T040 [US3] Implement the pure shared prerequisite decision in `src/verifysignal_spec/workflows/run_preflight.py`
- [X] T041 [US3] Delegate workflow run checks to the shared preflight decision and probe the per-alias run lease before durable prerequisite work in `src/verifysignal_spec/workflows/prerequisites.py`
- [X] T042 [US3] Classify newer non-run attempts, make explicit runtime `sideEffectMayExist: true`, `commitStep.reached: true`, and strongly committed status (including public `sideEffects.status`) outrank authored or contradictory safe claims, reject ambiguous/whitespace-padded status authority, constrain exact semantic policy-change reconciliation to observation-mode `violated` outcomes without confirmed commit/later-attempt evidence or missing/unchanged/notes-only policy, and select exactly one rerun-policy branch in `src/verifysignal_spec/workflows/write_safety.py`
- [X] T043 [US3] Reconcile create/replace/delete active gates exclusively from the authoritative decision in `src/verifysignal_spec/workspace/repository.py`
- [X] T044 [US3] Acquire and hold a crash-released lease keyed by POSIX project `st_dev`/`st_ino` plus case-folded alias or Windows normalized/case-normalized resolved path plus case-folded alias, keep project-local lock paths non-authoritative, invoke preflight before runtime/environment/preparation, normalize Core output before persistence, and consume only an unambiguous current `data.summary.runId` or compatible legacy `data.runId` in `src/verifysignal_spec/workflows/run_lock.py` and `src/verifysignal_spec/commands/run.py`
- [X] T045 [US3] Persist conservative write-ahead `lastCoreAttempt` in canonical authority before Core/YAML projection, retain conservative true risk for contract-invalid outcomes, preserve public `sideEffectMayExist: true` from `execution` or `data.sideEffects` through `postCommitInterpretation`, RunHistory, and canonical `lastRun`, enforce exact-attempt refinement/clear, retain the marker through outcome interpretation and immutable crash-durable RunHistory → canonical lastRun+marker → generic projection ordering, clear it with a canonical null tombstone only afterward, and preserve all prior real state in `src/verifysignal_spec/commands/run.py`
- [X] T046 [US3] Return exact prepared-request ownership and delete only a newly created project-owned file on Core error in `src/verifysignal_spec/commands/run_request_preparation.py` and `src/verifysignal_spec/commands/run.py`
- [X] T047 [US3] Project the authoritative rerun/confirmation decision in `src/verifysignal_spec/workspace/repository.py` without trusting stale files; retain `src/verifysignal_spec/commands/list.py` as the unchanged consumer
- [X] T048 [US3] Run US3 tests to green and retain red/green SHAs using `tests/integration/test_rerun_policy_authority.py`
- [X] T049 [US3] Run adjacent CLI run, run-lock/CAS, canonical overlay/tombstone/reconciliation/allowlist, durable-persistence, authority-path safety, run-record/replay, write-safety, policy migration, workspace-validation, and confirmation contract suites in `tests/unit/test_canonical_run_authority.py`, `tests/unit/test_run_invocation_lock.py`, `tests/unit/test_durable_run_persistence.py`, `tests/unit/test_authority_path_safety.py`, `tests/contract/test_cli_run_contract.py`, `tests/integration/test_run_record_replay.py`, and `tests/integration/test_write_flow_rerun_guardrails.py`

**Checkpoint**: Current pre-execution errors are safe no-commit attempts; legacy
unknown write attempts require the configured `afterUnknown` decision without
becoming browser runs.

---

## Phase 6: User Story 4 - WorkflowRun-Authoritative Recovery (Priority: P1)

**Goal**: Every stage update derives projections from WorkflowRun, legacy state
migrates lazily, and interrupted multi-file projection writes heal on the next
mutating transition while read-only surfaces remain non-mutating.

**Independent Test**: Persist and block every relevant stage, simulate stale or
missing projections after a newer WorkflowRun, inject the strict authority
corruption matrix, and assert projections heal without losing completed stages
or target confirmation while alias-matching corruption fails closed.

### Red tests for User Story 4

- [X] T050 [P] [US4] Add failing authored-stage, authoring-check-without-runtime-readiness, runtime-readiness pass/block and later-stage revalidation, applied-repair reset, real-run pass/fail, Core-error, stage-guard, and same-run stage/target authority cases in `tests/integration/test_workflow_run_state_authority.py`, `tests/integration/test_workflow_terminal_transition_ordering.py`, and `tests/integration/test_workflow_target_confirmation.py`
- [X] T051 [P] [US4] Add failing lazy migration, canonical/dangling/symlink evidence, non-synthesis, idempotence, target-confirmation preservation, interrupted-projection healing, nanosecond newest ordering, equal-newest ambiguity despite a reference, portable WorkflowRun identity and case-fold sibling ambiguity, completed/current-stage/run-state/predecessor coherence with exercised repair/revalidation exceptions, optional legacy stage-timestamp compatibility, malformed blocker/gate decisions, direct/ancestral present-redirect refusal, and strict referenced/alias-matching corruption cases in `tests/unit/test_workflow_repository.py`, `tests/unit/test_authority_path_safety.py`, `tests/integration/test_workflow_terminal_transition_ordering.py`, and `tests/integration/test_workflow_run_authority_validation.py`
- [X] T052 [US4] Run the US4 focused tests, confirm the all-pending/divergent-state red failures, and commit them before production edits in `tests/integration/test_workflow_run_state_authority.py`

### Implementation for User Story 4

- [X] T053 [US4] Implement authoritative stage transitions, exact active-WorkflowRun return for downstream gates, later-stage resets, stage guards, canonical safe-file lazy migration, and projection healing in `src/verifysignal_spec/workflows/transitions.py`
- [X] T054 [US4] Strictly validate WorkflowRun schema/portable filename-and-alias identity/stages/required workflow and present optional timestamps/completed-currentStage-runState-predecessor coherence with exercised repair/revalidation exceptions/typed blockers/gates/confirmation/recursive secrets and direct/ancestral present-redirect safety before alias-matching selection, reject case-fold sibling collisions before read/write, preserve absent legacy stage timestamps, keep equal-newest candidates ambiguous even when referenced, preserve nanosecond logical ordering, render state only from a loaded/updated authority, and expose projection comparison helpers in `src/verifysignal_spec/workflows/repository.py`
- [X] T055 [US4] Route specify/clarify/plan/tasks/implement persistence through the transition boundary in `src/verifysignal_spec/workflows/stage_persistence.py`
- [X] T056 [US4] Keep authoring-check without `--runtime-readiness` at `validate`, route runtime-readiness validation pass/block and later-stage revalidation through reset-aware WorkflowRun transitions, and apply stage/authority guards before Core in `src/verifysignal_spec/commands/validate.py`
- [X] T057 [US4] Apply run stage/authority guards before Core, thread the same active WorkflowRun through target confirmation, route only valid real run pass/fail through executed-run transitions, and keep Core errors at a blocked, unexecuted `run` stage in `src/verifysignal_spec/commands/run.py`
- [X] T058 [US4] Run US4 tests to green and retain red/green SHAs using `tests/integration/test_workflow_run_state_authority.py`
- [X] T059 [US4] Run canonical persistence, strict WorkflowRun corruption/coherence/ambiguity, authority-path safety, stage contract, target confirmation, applied-repair reset, terminal ordering, and agent handoff regressions in `tests/integration/test_workflow_canonical_persistence.py`, `tests/integration/test_workflow_run_authority_validation.py`, `tests/unit/test_authority_path_safety.py`, `tests/contract/test_workflow_stage_persistence_contract.py`, `tests/integration/test_workflow_target_confirmation.py`, `tests/integration/test_workflow_run_state_authority.py`, and `tests/integration/test_workflow_terminal_transition_ordering.py`

**Checkpoint**: WorkflowRun is authoritative and projection recovery is
explicitly healable, not falsely described as crash-atomic.

---

## Phase 7: Full Regression and PR Evidence

**Purpose**: Prove the two-repository recovery without hidden sibling selection,
secret leakage, or platform regression.

- [X] T061 [P] Run secret-canary, representative list-performance, exact missing-runtime blocker, automatic-source scan exclusion, and sub-second runtime-readiness regressions in `tests/integration/test_runtime_secret_safety.py`, `tests/integration/test_list_performance.py`, and `tests/integration/test_managed_runtime_performance.py`
- [ ] T069 Rebase on current `origin/main` before every remaining evidence task, establish the final repository tuple, and repeat T060/T062-T067 from the beginning if any later rebase or tuple revision changes HEAD; record the final base and tuple SHAs without making the reusable `specs/028-entitlement-preflight-recovery/quickstart.md` stale
- [ ] T060 Run the complete local Spec suite, including native no-replace/A,B,A RunHistory, strict and cross-mapping risk coherence, explicit runtime true preservation, POSIX portable-name/RunHistory/WorkflowRun case-fold collision, and recursive URI-reference/compound-container secret-scanner corpora, with `.venv/bin/python -m pytest -q` from the repository root against the T069 tuple
- [ ] T062 Execute every acceptance row and capture non-sensitive evidence, including sidecar-absent unique-newer-history recovery, timestamp-less-first-write refusal, immutable A,B,A RunHistory identity, unsupported post-sidecar old-binary downgrade documentation, strict/contradictory risk authority, explicit-runtime-true preservation/precedence, prose-embedded URI and compound-container secret refusal, portable-name/case-fold behavior, and the persisted-redirect versus prepared-handle threat boundary, using `specs/028-entitlement-preflight-recovery/quickstart.md`
- [ ] T063 Run the Spec Docker suite with explicit Core, Spec, and backend pins, isolated Core dependencies, and the pinned `linux/amd64` platform using `scripts/verify-docker.sh`
- [ ] T064 Run the companion Core Docker and full local gates using `../verifysignal-entitlement-preflight-recovery/scripts/verify-docker.sh`
- [ ] T065 Run pinned browser smoke and customer-journey composition using `../verifysignal-entitlement-preflight-recovery/package.json`
- [ ] T066 Re-run the localized-home positive browser path in an isolated Rigel Rise workspace and separately run deterministic fake-Core current/legacy error-envelope controls using `specs/028-entitlement-preflight-recovery/quickstart.md`
- [ ] T067 Confirm the stable protected `spec` CI context requires the Ubuntu `spec-tests`, native `windows-safety`, and separate `windows-install` jobs; verify `windows-safety` executes `test_durable_create_is_native_no_replace_and_leaves_no_temporary_file` from `tests/unit/test_durable_run_persistence.py`, both `tests/unit/test_workspace_layout_portability.py` and `tests/unit/test_run_history_filename_portability.py`, and the named-mutex, redirected-ancestor, and prepared-handle suites on `windows-latest`, while the same portability corpus passes on POSIX, in `.github/workflows/ci.yml`
- [ ] T068 Re-run `/speckit-analyze` only after T069 then T060/T062-T067 are green, and resolve all Critical/High findings in `specs/028-entitlement-preflight-recovery/`
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
  Its strict serial gate is T069 (rebase/tuple) → T060 and T062-T067 (all final
  evidence) → T068 (final artifact analysis) → T070 (PR). Any tuple movement
  after T069 invalidates the evidence and restarts at T060.

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
- Do not replace the OS-owned run lease with a stale PID/path ownership file, or
  weaken exact-attempt CAS when the lease is held.
- Do not describe atomic replacement alone as crash durability; preserve the
  file flush and platform-specific replacement-metadata ordering.
- Do not treat generic `<alias>.yaml` run fields as authority after the canonical
  run-authority sibling exists, omit explicit null tombstones, accept
  unallowlisted/secret `lastRun`, discard newer/conflicting/unorderable base YAML
  or RunHistory, perform a timestamp merge, or follow any authority-path
  redirect.
- Do not let a mutable WorkflowRun reference break an equal-newest authority
  tie or accept incoherent completed/current-stage/run-state/predecessor state
  outside the exercised repair/revalidation exceptions.
- Do not call the WorkflowRun/projection update transactionally atomic; prove
  authority and healing instead.
