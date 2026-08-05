# Quickstart: Entitlement Preflight Recovery

## Repositories

Use clean worktrees and pin every repository explicitly:

```text
Core:    ../verifysignal-entitlement-preflight-recovery
Spec:    ../verifysignal-spec-entitlement-preflight-recovery
Backend: ../verifysignal-be
```

Backend is an integration fixture only. Do not create a backend feature branch
or edit backend production code for this recovery.

## 1. Establish the baseline

From the Spec worktree:

```sh
python -m pytest -q \
  tests/unit/test_core_adapter.py \
  tests/unit/test_runtime_resolver.py \
  tests/contract/test_core_entitlement_error_map_tracks_core.py \
  tests/contract/test_rerun_preflight_contract.py \
  tests/integration/test_core_update.py \
  tests/integration/test_managed_runtime_override_entitlement.py \
  tests/integration/test_workflow_run_preflight_alignment.py
```

Record the passing baseline count. The current green baseline demonstrates the
coverage gap; it does not disprove the diagnosis.

## 2. Follow red/green by story

For each story:

1. add production-shaped regression fixtures and assertions;
2. run only the new/focused tests and confirm they fail for the diagnosed reason;
3. commit the red tests before editing production code;
4. implement the smallest coherent change;
5. rerun the focused tests to green;
6. refactor only while the focused and adjacent suites remain green.

Required red evidence:

- a fresh workspace selects an ancestor sibling instead of managed-only;
- a top-level public Core error is not normalized and readiness overstates proof;
- direct run bypasses validation and persists a pseudo-run;
- `afterUnknown` is not selected and stale confirmation survives;
- stage persistence resets projections instead of advancing WorkflowRun.

## 3. Focused green suites

Run the feature suites after each implementation group:

```sh
python -m pytest -q \
  tests/unit/test_core_outcome_normalization.py \
  tests/unit/test_run_preflight.py \
  tests/unit/test_rerun_policy.py \
  tests/unit/test_workflow_repository.py \
  tests/contract/test_entitlement_preflight_recovery_contract.py \
  tests/integration/test_fresh_workspace_runtime_mode.py \
  tests/integration/test_protected_readiness_scope.py \
  tests/integration/test_preexecution_run_lifecycle.py \
  tests/integration/test_rerun_policy_authority.py \
  tests/integration/test_workflow_run_state_authority.py
```

The Core-error lifecycle suite must include both controls:

- current envelope: `started: false`, `sideEffectMayExist: false` records a safe
  non-run `lastCoreAttempt`, creates no RunHistory, and requires no unknown-risk
  confirmation;
- legacy envelope: execution metadata absent records an unknown non-run attempt,
  creates no RunHistory, and selects `afterUnknown` for the next write rerun.

The prepared-request cleanup test must pre-create a neighboring and a user-owned
file, create exactly one transient file during invocation, and prove only that
exact newly created file is deleted after Core error.

## 4. Full local Spec regression

```sh
python -m pytest -q
```

Secret-safety assertions scan command JSON and the entire generated
`.verifysignal/` tree. The canary count must be zero.

## 5. Pinned Docker composition

From the Spec worktree, use container-side `/w` paths:

```sh
VERIFYSIGNAL_CORE_DIR=/w/verifysignal-entitlement-preflight-recovery \
VERIFYSIGNAL_SPEC_DIR=/w/verifysignal-spec-entitlement-preflight-recovery \
VERIFYSIGNAL_BACKEND_DIR=/w/verifysignal-be \
scripts/verify-docker.sh
```

Run the companion Core Docker suite with the same three pins. A skipped
cross-repository test is not a pass; record executed test counts and skip reasons.

## 6. Browser product truth

From the Core worktree:

```sh
VERIFYSIGNAL_CORE_DIR="$PWD" \
VERIFYSIGNAL_SPEC_DIR="../verifysignal-spec-entitlement-preflight-recovery" \
VERIFYSIGNAL_BACKEND_DIR="../verifysignal-be" \
npm run product-truth:browser-smoke
```

Then run the repository's full product-truth/customer-journey commands with the
same pins, including its Supabase/backend fixture leg. Do not accept automatic
sibling scanning in the final evidence.

## 7. Localized-home acceptance

Use an isolated copy/workspace of the Rigel Rise website so incident state does
not affect the result.

Positive path acceptance:

- the workspace persists `managed-only` unless an explicit development Core is
  chosen;
- protected authoring check passes with valid trust material;
- the real browser run writes a Core report and evidence directory;
- all four required gates are covered;
- the class-`none` use case requires no `--confirm-risk`.

Forced-error control:

- return `verifysignal.error/v1` before execution;
- command output is blocked with the exact normalized entitlement code;
- `lastCoreAttempt.executionState` is `not-started` for the current envelope;
- no new run ID, RunHistory, lastRun, coverage, evidence, report, repair session,
  or unknown-write-risk confirmation exists;
- only the exact invocation-created prepared request is removed.

Repeat the forced error without `execution` metadata for a write fixture:

- `lastCoreAttempt.executionState` is `unknown`;
- no synthetic run exists;
- the next preflight selects `afterUnknown` and produces the configured decision.

## 8. Workflow recovery acceptance

Exercise every transition from understand through run. After each write, compare
WorkflowRun, the use-case reference, and rendered state. Simulate interruption by
leaving one projection stale after a newer WorkflowRun; the next mutating
workflow transition must heal the projection and retain completed stages and
target confirmation. A read-only inspection must render the authoritative run
without mutating the project.

Do not describe the three-file update as transactionally atomic. Each file uses
atomic replacement; WorkflowRun is the authority used for recovery.

## 9. Merge-ready evidence

Before opening the Spec PR, record:

- red and green commit SHAs for each behavior group;
- focused and full pytest counts;
- pinned Docker/Core/Spec/backend results with no hidden skips;
- browser smoke and localized-home evidence;
- zero secret-canary occurrences;
- compatibility matrix for new workspace, field-absent legacy workspace, current
  Core error metadata, and older Core error without metadata;
- no manual version-file changes.

The Spec PR title is `fix: preserve protected preflight without synthetic runs`.
Merge only after the companion Core patch release is available and the Spec
branch has been rebased and retested against it.
