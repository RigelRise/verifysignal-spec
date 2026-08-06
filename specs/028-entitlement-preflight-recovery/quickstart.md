# Quickstart: Entitlement Preflight Recovery

## 0. Pin the local repository tuple

Run this quickstart from the Spec feature worktree. The defaults name the four
isolated worktrees used by this feature; override a path before running the block
if the local checkout uses another name.

```sh
set -eu

VS_SPEC_DIR="$(git rev-parse --show-toplevel)"
VS_WORKSPACE_DIR="$(dirname "$VS_SPEC_DIR")"
: "${VS_CORE_DIR:=$VS_WORKSPACE_DIR/verifysignal-entitlement-preflight-recovery}"
: "${VS_BACKEND_DIR:=$VS_WORKSPACE_DIR/verifysignal-be-entitlement-preflight-fixture}"
: "${VS_RIGEL_DIR:=$VS_WORKSPACE_DIR/rigel-rise-website-entitlement-preflight-acceptance}"

VS_CORE_DIR="$(cd "$VS_CORE_DIR" && pwd -P)"
VS_SPEC_DIR="$(cd "$VS_SPEC_DIR" && pwd -P)"
VS_BACKEND_DIR="$(cd "$VS_BACKEND_DIR" && pwd -P)"
VS_RIGEL_DIR="$(cd "$VS_RIGEL_DIR" && pwd -P)"
VS_SPEC_PYTHON="$VS_SPEC_DIR/.venv/bin/python"

test -x "$VS_SPEC_PYTHON" || exit 1
test -x "$VS_SPEC_DIR/.venv/bin/verifysignal" || exit 1
test "$(git -C "$VS_CORE_DIR" rev-parse --show-toplevel)" = "$VS_CORE_DIR" || exit 1
test "$(git -C "$VS_SPEC_DIR" rev-parse --show-toplevel)" = "$VS_SPEC_DIR" || exit 1
test "$(git -C "$VS_BACKEND_DIR" rev-parse --show-toplevel)" = "$VS_BACKEND_DIR" || exit 1
test "$(git -C "$VS_RIGEL_DIR" rev-parse --show-toplevel)" = "$VS_RIGEL_DIR" || exit 1
test -z "$(git -C "$VS_CORE_DIR" status --porcelain)" || exit 1
test -z "$(git -C "$VS_SPEC_DIR" status --porcelain)" || exit 1
test -z "$(git -C "$VS_BACKEND_DIR" status --porcelain)" || exit 1
test -z "$(git -C "$VS_RIGEL_DIR" status --porcelain)" || exit 1

VS_CORE_PIN="$(git -C "$VS_CORE_DIR" rev-parse HEAD)"
VS_SPEC_PIN="$(git -C "$VS_SPEC_DIR" rev-parse HEAD)"
VS_BACKEND_PIN="$(git -C "$VS_BACKEND_DIR" rev-parse HEAD)"
VS_RIGEL_PIN="$(git -C "$VS_RIGEL_DIR" rev-parse HEAD)"

verify_pins() {
  test "$(git -C "$VS_CORE_DIR" rev-parse HEAD)" = "$VS_CORE_PIN" || return 1
  test "$(git -C "$VS_SPEC_DIR" rev-parse HEAD)" = "$VS_SPEC_PIN" || return 1
  test "$(git -C "$VS_BACKEND_DIR" rev-parse HEAD)" = "$VS_BACKEND_PIN" || return 1
  test "$(git -C "$VS_RIGEL_DIR" rev-parse HEAD)" = "$VS_RIGEL_PIN" || return 1
  test -z "$(git -C "$VS_CORE_DIR" status --porcelain)" || return 1
  test -z "$(git -C "$VS_SPEC_DIR" status --porcelain)" || return 1
  test -z "$(git -C "$VS_BACKEND_DIR" status --porcelain)" || return 1
  test -z "$(git -C "$VS_RIGEL_DIR" status --porcelain)" || return 1
}

export VERIFYSIGNAL_CORE_DIR="$VS_CORE_DIR"
export VERIFYSIGNAL_SPEC_DIR="$VS_SPEC_DIR"
export VERIFYSIGNAL_BACKEND_DIR="$VS_BACKEND_DIR"
verify_pins || exit 1
```

This records immutable revisions for the current run without embedding SHAs in
the reusable document. Call `verify_pins` before and after every composed leg;
any checkout movement or tracked/unignored worktree change fails the run. The
Backend and Rigel repositories are fixtures only: do not create feature branches
or edit their production code.

## 1. Establish the baseline

From the Spec worktree, with the tuple above still exported:

```sh
verify_pins || exit 1
"$VS_SPEC_PYTHON" -m pytest -q \
  tests/unit/test_core_adapter.py \
  tests/unit/test_runtime_resolver.py \
  tests/contract/test_core_entitlement_error_map_tracks_core.py \
  tests/contract/test_rerun_preflight_contract.py \
  tests/integration/test_core_update.py \
  tests/integration/test_managed_runtime_override_entitlement.py \
  tests/integration/test_workflow_run_preflight_alignment.py
verify_pins || exit 1
```

Expected outcome: the command exits zero, no cross-repository test skips, and
every Core lookup resolves through `VERIFYSIGNAL_CORE_DIR` rather than an
uncontrolled sibling name. Record the observed count outside this document. The
green baseline demonstrates the coverage gap; it does not disprove the diagnosis.

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
verify_pins || exit 1
"$VS_SPEC_PYTHON" -m pytest -q \
  tests/unit/test_core_outcome_normalization.py \
  tests/unit/test_run_preflight.py \
  tests/unit/test_rerun_policy.py \
  tests/unit/test_workflow_repository.py \
  tests/contract/test_entitlement_preflight_recovery_contract.py \
  tests/integration/test_fresh_workspace_runtime_mode.py \
  tests/integration/test_protected_readiness_scope.py \
  tests/integration/test_preexecution_run_lifecycle.py \
  tests/integration/test_rerun_policy_authority.py \
  tests/integration/test_workflow_run_state_authority.py \
  tests/integration/test_workflow_terminal_transition_ordering.py \
  tests/integration/test_managed_runtime_performance.py
verify_pins || exit 1
```

Expected outcome: every focused test passes, current envelopes remain
`not-started`, legacy envelopes remain `unknown`, and neither error path creates
RunHistory or browser evidence.

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
verify_pins || exit 1
"$VS_SPEC_PYTHON" -m pytest -q
verify_pins || exit 1
```

Secret-safety assertions scan command JSON and the entire generated
`.verifysignal/` tree. Expected outcome: pytest exits zero, pin-sensitive
cross-repository legs execute rather than skip for a missing sibling, and the
secret canary count is zero.

## 5. Pinned Docker composition

Both repositories mount their shared parent at `/w`, so derive explicit
container-side pins from the already verified host tuple:

```sh
test "$(dirname "$VS_CORE_DIR")" = "$(dirname "$VS_SPEC_DIR")" || exit 1
test "$(dirname "$VS_BACKEND_DIR")" = "$(dirname "$VS_SPEC_DIR")" || exit 1
VS_DOCKER_CORE_DIR="/w/$(basename "$VS_CORE_DIR")"
VS_DOCKER_SPEC_DIR="/w/$(basename "$VS_SPEC_DIR")"
VS_DOCKER_BACKEND_DIR="/w/$(basename "$VS_BACKEND_DIR")"

verify_pins || exit 1
(
  cd "$VS_SPEC_DIR"
  VERIFYSIGNAL_CORE_DIR="$VS_DOCKER_CORE_DIR" \
  VERIFYSIGNAL_SPEC_DIR="$VS_DOCKER_SPEC_DIR" \
  VERIFYSIGNAL_BACKEND_DIR="$VS_DOCKER_BACKEND_DIR" \
  scripts/verify-docker.sh
)
(
  cd "$VS_CORE_DIR"
  VERIFYSIGNAL_CORE_DIR="$VS_DOCKER_CORE_DIR" \
  VERIFYSIGNAL_SPEC_DIR="$VS_DOCKER_SPEC_DIR" \
  VERIFYSIGNAL_BACKEND_DIR="$VS_DOCKER_BACKEND_DIR" \
  scripts/verify-docker.sh
)
verify_pins || exit 1
```

Expected outcome: both scripts exit zero and every cross-repository leg executes
with the declared Core/Spec/Backend paths on `linux/amd64`, and Core dependencies
are installed in an isolated container path rather than a host `node_modules`.
A skipped cross-repository test is not a pass; record executed counts and any
unrelated skip reasons outside this file.

## 6. Browser product truth

Run browser smoke with the same immutable tuple and an explicit Spec interpreter:

```sh
verify_pins || exit 1
(
  cd "$VS_CORE_DIR"
  npm ci
  npm run build
  VERIFYSIGNAL_CORE_DIR="$VS_CORE_DIR" \
  VERIFYSIGNAL_SPEC_DIR="$VS_SPEC_DIR" \
  VERIFYSIGNAL_SPEC_REPOSITORY="$VS_SPEC_DIR" \
  VERIFYSIGNAL_SPEC_PYTHON="$VS_SPEC_PYTHON" \
  VERIFYSIGNAL_BACKEND_DIR="$VS_BACKEND_DIR" \
  npm run product-truth:browser-smoke
)
verify_pins || exit 1
```

Expected outcome: the command prints `[product-truth-browser-smoke] passed`; the
authenticated dogfood test executes and does not report a missing sibling.

For the fixture-trust customer journey, mirror the local prerequisites declared
by Core's `.github/workflows/product-truth.yml` without installing Codex globally:

```sh
VS_CODEX_PREFIX="$(mktemp -d "${TMPDIR:-/tmp}/verifysignal-codex.XXXXXX")"
npm install --prefix "$VS_CODEX_PREFIX" @openai/codex@0.145.0
(
  cd "$VS_CORE_DIR"
  unset VERIFYSIGNAL_RUNTIME_SIGNING_KEY_ID
  unset VERIFYSIGNAL_RUNTIME_SIGNING_PRIVATE_KEY_PEM
  export VERIFYSIGNAL_ALLOW_TEST_RELEASE_KEYS=1
  npm run runtime:package -- --platform current --out-dir dist/runtime-journey
)
(
  cd "$VS_BACKEND_DIR"
  npm ci
  supabase start
  VERIFYSIGNAL_RUNTIME_STORAGE_BUCKET=verifysignal-runtimes \
    npm run test:integration
  npm run build
)
verify_pins || exit 1
(
  cd "$VS_SPEC_DIR"
  PATH="$VS_CODEX_PREFIX/node_modules/.bin:$PATH" \
  VERIFYSIGNAL_CORE_DIR="$VS_CORE_DIR" \
  VERIFYSIGNAL_SPEC_DIR="$VS_SPEC_DIR" \
  VERIFYSIGNAL_BACKEND_DIR="$VS_BACKEND_DIR" \
  "$VS_SPEC_PYTHON" scripts/ci/customer_journey.py
)
verify_pins || exit 1
```

Expected outcome: the final JSON has `status: green`; its protected validation,
repair recovery, committed write, record, crystallize, offline replay, and
lifecycle-identity gates are all `passed`. Do not accept automatic sibling
scanning in the final evidence.

## 7. Localized-home acceptance

Create the acceptance workspace from the recorded Rigel revision rather than
reusing prior incident state:

```sh
verify_pins || exit 1
VS_CLAUDE_PREFIX="$(mktemp -d "${TMPDIR:-/tmp}/verifysignal-claude.XXXXXX")"
npm install --prefix "$VS_CLAUDE_PREFIX" @anthropic-ai/claude-code@2.1.220
VS_RIGEL_RUN_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/verifysignal-rigel.XXXXXX")"
VS_RIGEL_RUN_DIR="$VS_RIGEL_RUN_ROOT/repository"
git clone --quiet --no-local "$VS_RIGEL_DIR" "$VS_RIGEL_RUN_DIR"
git -C "$VS_RIGEL_RUN_DIR" switch --detach "$VS_RIGEL_PIN"
test "$(git -C "$VS_RIGEL_RUN_DIR" rev-parse HEAD)" = "$VS_RIGEL_PIN" || exit 1
test -z "$(git -C "$VS_RIGEL_RUN_DIR" status --porcelain)" || exit 1
(
  cd "$VS_RIGEL_RUN_DIR"
  export PATH="$VS_SPEC_DIR/.venv/bin:$VS_CLAUDE_PREFIX/node_modules/.bin:$PATH"
  export VERIFYSIGNAL_RUNTIME_CACHE_DIR="$VS_RIGEL_RUN_ROOT/runtime-cache"
  unset VERIFYSIGNAL_ENTITLEMENT_RECEIPT
  unset VERIFYSIGNAL_ENTITLEMENT_RECEIPT_PATH
  unset VERIFYSIGNAL_ENTITLEMENT_PUBLIC_KEYS_JSON
  unset VERIFYSIGNAL_ENTITLEMENT_TRUST_CONTEXT
  unset VERIFYSIGNAL_ALLOW_FIXTURE_ENTITLEMENT_KEYS
  unset VERIFYSIGNAL_EMAIL
  unset VERIFYSIGNAL_EMAIL_UNLOCK_TOKEN
  unset VERIFYSIGNAL_API_BASE_URL
  unset VERIFYSIGNAL_CORE_CMD
  unset VERIFYSIGNAL_RUNTIME_PACKAGE
  unset VERIFYSIGNAL_RUNTIME_SIGNING_KEY_ID
  unset VERIFYSIGNAL_RUNTIME_SIGNING_PRIVATE_KEY_PEM
  unset VERIFYSIGNAL_ALLOW_TEST_RELEASE_KEYS
  unset NODE_ENV
  test "$(command -v verifysignal)" = "$VS_SPEC_DIR/.venv/bin/verifysignal" || exit 1
  verifysignal init \
    --here \
    --integration claude \
    --core-cmd "$VS_CORE_DIR" \
    --json
  node "$VS_CORE_DIR/scripts/examples/with-example-entitlement.mjs" claude
)
verify_pins || exit 1
```

In that Claude session, invoke `/verifysignal`, choose the multiple-languages
scenario, and confirm `https://www.rigelrise.io` as the target. The explicit
`--core-cmd` makes this acceptance a `development-override`; a separate fresh
init without explicit Core setup must remain `managed-only`.

Positive path acceptance:

- this explicit-Core acceptance workspace persists `development-override`;
- a separate clean init without `--core-cmd` persists `managed-only`;
- protected authoring check passes with valid trust material;
- the real browser run writes a Core report and evidence directory;
- all four required gates are covered;
- the class-`none` use case requires no `--confirm-risk`.

Expected outcome: `authoring-check` and run pass, the browser opens, and the run
envelope points to an existing Core report and evidence directory.

### Deterministic non-Rigel error-envelope controls

The live Rigel session above is the positive browser acceptance. It does not
inject synthetic Core responses. Run the fixture-backed suites below separately
to prove the current and legacy error-envelope behavior without changing or
claiming negative browser evidence for the Rigel fixture.

Current-envelope fixture assertions:

- return `verifysignal.error/v1` before execution;
- command output is blocked with the exact normalized entitlement code;
- `lastCoreAttempt.executionState` is `not-started` for the current envelope;
- no new run ID, RunHistory, lastRun, coverage, evidence, report, repair session,
  or unknown-write-risk confirmation exists;
- only the exact invocation-created prepared request is removed.

Legacy-envelope write fixture assertions:

- `lastCoreAttempt.executionState` is `unknown`;
- no synthetic run exists;
- the next preflight selects `afterUnknown` and produces the configured decision.

These deterministic controls are repeatable without using the Rigel fixture:

```sh
verify_pins || exit 1
"$VS_SPEC_PYTHON" -m pytest -q \
  tests/integration/test_preexecution_run_lifecycle.py \
  tests/integration/test_rerun_policy_authority.py \
  tests/integration/test_prepared_request_error_cleanup.py
verify_pins || exit 1
```

Expected outcome: the command exits zero and the assertions prove the two
execution classifications, zero synthetic runs, exact-file cleanup, and
`afterUnknown` selection. Record this as deterministic fake-Core evidence, not
as a Rigel browser run.

## 8. Workflow recovery acceptance

Run the authoritative transition, interrupted-projection healing, and read-only
non-mutation regressions explicitly:

```sh
verify_pins || exit 1
"$VS_SPEC_PYTHON" -m pytest -q \
  tests/unit/test_workflow_repository.py \
  tests/integration/test_workflow_run_state_authority.py \
  tests/integration/test_workflow_terminal_transition_ordering.py
verify_pins || exit 1
```

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
- browser smoke and localized-home positive-path evidence;
- separately labelled deterministic fake-Core current/legacy control evidence;
- zero secret-canary occurrences;
- compatibility matrix for new workspace, field-absent legacy workspace, current
  Core error metadata, and older Core error without metadata;
- no manual version-file changes.

The Spec PR title is `fix: preserve protected preflight without synthetic runs`.
Merge only after the companion Core patch release is available and the Spec
branch has been rebased and retested against it.
