# Quickstart: Entitlement Preflight Recovery

## 0. Rebase, then pin the local repository tuple

For merge-ready evidence, first rebase the Core and Spec feature branches on
their current `origin/main` and make both worktrees clean. Then run this
quickstart from the Spec feature worktree. The defaults name the four isolated
worktrees used by this feature; override a path before running the block if the
local checkout uses another name. Any later rebase or tuple movement invalidates
all evidence from sections 3 through 8 and requires those legs to be repeated.

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
- stage persistence resets projections instead of advancing WorkflowRun;
- Core's exported operation policy can be mutated to bypass the `run` receipt
  guard;
- authored class `none` overrides explicit runtime
  `sideEffectMayExist: true`;
- Core can be invoked before durable write-ahead intent, or a post-response
  failure can erase all attempt evidence;
- stage eligibility and target confirmation can resolve different WorkflowRuns;
- two same-alias runs can overwrite one shared marker or clear one another's
  attempt;
- wall-clock rollback can make a new attempt older than prior durable evidence;
- contract-invalid data can downgrade conservative side-effect risk;
- a corrupt alias-matching WorkflowRun can be skipped in favor of stale valid
  authority, and ordinary atomic replacement does not prove crash durability;
- Windows-device/trailing/control names are accepted on POSIX, or case-fold
  sibling collisions can make RunHistory/WorkflowRun authority host-dependent;
- an A,B,A RunHistory identity reuse replaces A or changes B's canonical
  `lastRun`, rather than failing before any later write;
- non-boolean, whitespace-padded/ambiguous, or cross-mapping contradictory risk
  authority can be coerced into a safe rerun branch;
- secret scalars inside secret-named/compound containers such as `apiToken` or
  nested lists, scheme-less/network-path/relative-query or prose-embedded
  credential URI references (including repeatedly encoded nested values),
  compound `*_token` or bracketed provider credential/signature query aliases,
  short Basic/Bearer credentials, base64/base64url content, punctuation after a
  Windows drive prefix, context-mismatched high-entropy public identifiers, or
  invalid/multi-primary public-container shapes, exact `credential` metadata
  leaves, numeric feature branches, or structured public `errorCode` values can
  bypass validation, false-positive, or raise;
- a sidecar-absent older YAML projection can hide a unique newer RunHistory, or
  a timestamp-less legacy run can be silently accepted by the first safety write.

## 3. Focused green suites

Run the feature suites after each implementation group:

```sh
verify_pins || exit 1
"$VS_SPEC_PYTHON" -m pytest -q \
  tests/unit/test_core_outcome_normalization.py \
  tests/unit/test_run_preflight.py \
  tests/unit/test_run_invocation_lock.py \
  tests/unit/test_rerun_policy.py \
  tests/unit/test_durable_run_persistence.py \
  tests/unit/test_canonical_run_authority.py \
  tests/unit/test_workspace_layout_portability.py \
  tests/unit/test_run_history_filename_portability.py \
  tests/unit/test_authority_path_safety.py \
  tests/unit/test_workflow_secret_safety.py \
  tests/unit/test_workflow_repository.py \
  tests/contract/test_entitlement_preflight_recovery_contract.py \
  tests/integration/test_fresh_workspace_runtime_mode.py \
  tests/integration/test_protected_readiness_scope.py \
  tests/integration/test_preexecution_run_lifecycle.py \
  tests/integration/test_prepared_request_error_cleanup.py \
  tests/integration/test_rerun_policy_authority.py \
  tests/integration/test_workflow_target_confirmation.py \
  tests/integration/test_workflow_run_authority_validation.py \
  tests/integration/test_workflow_run_state_authority.py \
  tests/integration/test_workflow_terminal_transition_ordering.py \
  tests/integration/test_managed_runtime_performance.py
verify_pins || exit 1
```

Run the companion Core immutability regression against the same pin:

```sh
verify_pins || exit 1
(
  cd "$VS_CORE_DIR"
  npm ci
  npm test -- \
    tests/unit/entitlement-guard.test.ts \
    tests/unit/runtime-trust-contract.test.ts
)
verify_pins || exit 1
```

Expected outcome: every focused test passes, current envelopes remain
`not-started`, legacy envelopes remain `unknown`, and neither error path creates
RunHistory or browser evidence.

The Core-error lifecycle suite must include both controls:

- current entitlement envelope: exact `started: false`,
  `phase: pre-execution`, `sideEffectMayExist: false` records a safe non-run
  `lastCoreAttempt`, creates no RunHistory, and requires no unknown-risk
  confirmation; the same tuple on a non-entitlement error or any contradictory
  entitlement tuple remains unknown;
- legacy envelope: execution metadata absent records an unknown non-run attempt,
  creates no RunHistory, and selects `afterUnknown` for the next write rerun.

It must also prove the write-ahead ordering boundary:

- conservative `lastCoreAttempt` exists before the Core adapter is called;
- marker persistence failure invokes Core zero times and cleans only the exact
  invocation-owned prepared request;
- adapter, normalizer, post-response interpretation, and `record_run` failures
  retain conservative unknown intent with side-effect risk;
- a valid run uses the marker timestamp as `startedAt`, records a strictly later
  `completedAt`, and clears the marker only after `record_run` succeeds;
- if marker clearing alone fails, the equal-start durable real run remains
  authoritative over the leftover marker.
- a new marker orders strictly after prior run completion and prior attempt
  evidence when the wall clock moves backward;
- refinement and clear reject a mismatched `attemptedAt` and preserve the marker
  owned by another attempt;
- a contract-invalid response retains unknown execution and
  `sideEffectMayExist: true`, including for authored class `none`.

The concurrency/durability suites must prove:

- one same-process and one cross-process holder exclude a second run for the
  same resolved project/alias, while another alias can acquire independently;
- workflow check and direct run expose `runtime.run-in-progress`, invoke Core
  zero times, and persist no attempt/run artifacts while the lease is held;
- the lease is reacquirable after explicit release and holder termination;
- unavailable trustworthy locking fails closed with
  `runtime.run-lock-unavailable`;
- POSIX uses a private no-follow per-user runtime lock file outside the mutable
  project and proves that replacing the project-local lock directory cannot
  admit another holder; its identity is project `st_dev`/`st_ino` plus
  `alias.casefold()`, while Windows uses normalized/case-normalized resolved path
  plus `alias.casefold()`; durable mutable writes observe file `fsync` → atomic
  replace → parent-directory `fsync`; Windows CI exercises the named mutex and
  write-through replacement path;
- marker, lastRun, and marker clear use durable replacement, while RunHistory
  uses native durable create-without-replacement; A,B,A reuse leaves A bytes and
  B canonical authority unchanged.
- `.verifysignal/use-cases/<alias>.run-authority.json` has exact schema/identity
  and overlays `lastCoreAttempt`/`lastRun` onto stale generic YAML, including
  null marker tombstones that cannot be resurrected by a provably stale writer;
- the exact canonical `lastRun` projection allowlist rejects unknown fields and
  recursively secret-looking nested values, including secret-named/compound
  containers, nested list scalars, credential-bearing URI references without a
  scheme, network/relative references, references embedded in prose,
  repeatedly encoded nested references, provider/bracketed query aliases,
  verified Bearer/Basic values, and base64/base64url/high-entropy content before
  generic public-field exemptions; multiline prose is not treated as one giant
  URI and public selector/token-policy exemptions require their documented
  value shape; cyclic or over-limit nested inputs return a blocking finding
  rather than raising or being skipped;
- canonical, legacy, and RunHistory risk authority rejects wrong types,
  whitespace-padded/ambiguous status tokens, and within-/cross-mapping
  contradictions before write; `commitStep.reached: true`, explicit true
  booleans, and strongly committed status remain conservative if an in-memory
  value also claims safety;
- base YAML or RunHistory that is temporally newer, conflicts in identity at the
  same timestamp, or diverges without a reconcilable order fails closed instead
  of being discarded or timestamp-merged;
- with no sidecar, a unique newer valid RunHistory is recovered before preflight;
  a timestamp-less generic `lastRun` with no matching history remains readable
  but the first canonical safety write rejects it as unorderable;
- portable component validation rejects controls, trailing dot/space, and
  Windows device basenames case-insensitively, while RunHistory and WorkflowRun
  read/write reject sibling names that differ only by case before mutation;
- before Core, canonical marker precedes generic projection; a real result
  orders RunHistory → canonical `lastRun` plus still-owned marker → generic
  projection → canonical clear tombstone → generic projection;
- corrupt/non-regular run authority and direct or ancestral POSIX
  symlink/Windows junction/reparse paths fail closed without fallback or an
  external-target write.

The redirect cases above exercise components that are already redirected when
validation begins and the cooperating-process boundary. Do not report them as a
claim against adversarial same-user replacement between validation and ordinary
authority I/O. The prepared-request replacement cases are stronger by design:
retained directory/file handles must keep creation and cleanup anchored when a
pathname is renamed or replaced.

The rerun matrix must include authored `none` plus explicit runtime
`sideEffectMayExist: true` and select `afterUnknown` for the non-run attempt.
Contradictory `executionState: not-started` does not override that explicit true
boolean. It must also inject successful-run true evidence through both
`execution.sideEffectMayExist` and `data.sideEffects.sideEffectMayExist`, retain
it in `postCommitInterpretation`, RunHistory, and canonical `lastRun`, and select
`afterCommit`.

The prepared-request cleanup test must pre-create a neighboring and a user-owned
file, create exactly one transient file during invocation, and prove only that
exact newly created file is deleted after Core error.

### Native Windows safety gate

The PR's stable protected `spec` context must require all three CI results:

1. `spec-tests` — full pytest on Ubuntu;
2. `windows-safety` — Python 3.12 on `windows-latest`, running
   `tests/unit/test_run_invocation_lock.py` and
   `tests/unit/test_durable_run_persistence.py` plus
   `tests/unit/test_workspace_layout_portability.py`,
   `tests/unit/test_run_history_filename_portability.py`,
   `tests/unit/test_authority_path_safety.py` and
   `tests/unit/test_run_request_preparation.py` natively;
3. `windows-install` — the independent advertised installer/MCP customer path.

The native safety job must execute `CreateMutexW`/`WaitForSingleObject` for the
global per-alias mutex and `MoveFileExW` with replace-existing plus write-through
for durable mutable authority replacement, plus
`test_durable_create_is_native_no_replace_and_leaves_no_temporary_file` to prove
the no-replace RunHistory primitive. It must run
`tests/unit/test_workspace_layout_portability.py` and
`tests/unit/test_run_history_filename_portability.py` natively and exercise Windows
`FILE_ATTRIBUTE_REPARSE_POINT`/junction refusal. A mocked POSIX run or the
installer journey alone is not evidence for these primitives. The native job
also proves prepared-request creation, Core-compatible read sharing, and
cleanup by the retained Windows handle. The portable-name and case-fold
collision corpus must pass both here and in the full POSIX suite; a Windows-only
or simulated-only pass is insufficient.

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

Write-ahead failure-injection assertions:

- the initial marker is persisted before the adapter sees the request;
- response-interpretation and run-persistence failures retain the marker;
- successful `record_run` establishes ordered timestamps before marker clear;
- a marker-clear failure leaves a real run that outranks the equal-start marker.

Legacy-envelope write fixture assertions:

- `lastCoreAttempt.executionState` is `unknown`;
- no synthetic run exists;
- the next preflight selects `afterUnknown` and produces the configured decision.

Runtime-authority fixture assertion:

- explicit `sideEffectMayExist: true` selects `afterUnknown` even when authored
  side-effect class is `none` or authenticated-read.
- for a valid real run, true from either `execution` or `data.sideEffects`
  survives `postCommitInterpretation`, RunHistory, and canonical `lastRun` and
  selects `afterCommit`.
- contract-invalid run output retains conservative true risk rather than
  trusting malformed execution data.
- a contradictory `executionState: not-started` never downgrades an explicit
  runtime `sideEffectMayExist: true`; the attempt remains `afterUnknown`.
- persisted non-boolean, whitespace-padded/ambiguous, within-mapping, and
  cross-mapping contradictory risk is rejected before mutation; already-decoded
  true/reached/strongly committed evidence is never classified safe, and the
  raw public `sideEffects.status` alias rejects unknown tokens just like
  normalized `sideEffectStatus`.
- a `violated` result blocks an unchanged-policy rerun, while only an
  observation-mode violation without independent commit evidence or a later run
  attempt can use an exact semantic owner policy change for one new attempt;
  absent prior policy, notes-only edits, confirmed commit evidence, and later
  attempts remain blocked, and a clean result must become the latest evidence
  before strict pass.

These deterministic controls are repeatable without using the Rigel fixture:

```sh
verify_pins || exit 1
"$VS_SPEC_PYTHON" -m pytest -q \
  tests/unit/test_canonical_run_authority.py \
  tests/unit/test_run_invocation_lock.py \
  tests/unit/test_durable_run_persistence.py \
  tests/unit/test_workspace_layout_portability.py \
  tests/unit/test_run_history_filename_portability.py \
  tests/unit/test_authority_path_safety.py \
  tests/unit/test_workflow_secret_safety.py \
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
  tests/integration/test_workflow_target_confirmation.py \
  tests/integration/test_workflow_run_authority_validation.py \
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

Also create a stale use-case reference to an older confirmed WorkflowRun while
a unique newer active WorkflowRun remains unconfirmed. Both workflow check and
direct run must use the newer run for stage and target authority and must block
before Core resolution.

Run the strict authority corruption matrix. Every referenced or structured
alias-matching invalid document must return `workflow.authority-invalid` before
runtime resolution/Core invocation, including invalid schema/identity/enums,
invalid required workflow timestamps or invalid optional timestamps when
present, incomplete/duplicate stage states, malformed blockers or gate
decisions, completed status without `currentStage: run` or a completed `run`
state, non-completed status carrying workflow
`completedAt`, invalid predecessor state outside the exercised
repair/revalidation exceptions, invalid/secret target confirmation, and direct
or ancestral symlink/reparse authority. Also retain a positive legacy fixture
whose pending stages omit stage-level timestamps. A
corrupt different-alias candidate and an unreferenced unstructured file must not
displace the valid matching run. Verify that a one-nanosecond newer valid run is
selected and equal newest timestamps remain ambiguous even when one tied run is
referenced by the use-case projection. Rejected reads/writes must leave any
redirect target outside the project unchanged.

Add the portable authority namespace to that matrix: reject Windows device,
control, and trailing-dot/space aliases/run IDs, and reject `Run-A.yaml` plus
`run-a.yaml` for both WorkflowRun and RunHistory before read selection or write.
The same valid mixed-case public Core run ID must remain unchanged on both POSIX
and Windows.

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
  Core error metadata, older Core error without metadata, explicit runtime
  side-effect truth over authored class, contract-invalid conservative risk,
  write-ahead/CAS/durability ordering, same-alias lease contention/recovery,
  backward-clock logical ordering, strict WorkflowRun corruption handling, and
  stale WorkflowRun projection recovery, canonical run-authority
  overlay/tombstones, newer/conflicting/unorderable base or RunHistory refusal,
  sidecar-absent unique-newer-history recovery, timestamp-less-first-write
  refusal, explicitly unsupported pre-authority-binary downgrade after sidecar
  creation, canonical `lastRun` allowlist/recursive scanner ordering,
  immutable RunHistory A,B,A no-replace behavior, strict and cross-mapping risk
  authority, true preservation from both public success locations,
  portable-name/case-fold collision behavior on POSIX and Windows,
  persisted-redirect/cooperating-process threat scope versus handle-anchored
  prepared requests, and the required native Windows safety gate;
- no manual version-file changes.

After every item above is green, run `/speckit-analyze` and resolve all remaining
Critical/High findings. Only then open the PR. Do not move the final analysis
ahead of the rebase, tuple establishment, local/acceptance evidence, Docker, or
browser/localized-home legs.

The Spec PR title is `fix: preserve protected preflight without synthetic runs`.
Merge only after the companion Core patch release is available and the Spec
branch has been rebased and retested against it.
