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
Per-alias OS leases, exact-attempt CAS, logical nanosecond ordering,
crash-durable run authority writes, and strict WorkflowRun candidate validation
close the remaining concurrency and crash-recovery gaps. A dedicated canonical
run-safety authority overlays the legacy use-case projection with durable null
tombstones, while safe authority-path traversal and native Windows CI close
stale-writer, redirected-path, and platform-only gaps. A shared portable-name
boundary and case-fold sibling checks keep RunHistory/WorkflowRun authority
identical on POSIX and Windows, while one recursive secret scanner closes nested
container, list, URI, and public-field-exemption bypasses.

The implementation is additive for persisted v1 schemas and older Core error
envelopes. It intentionally changes only one earlier runtime behavior:
successful explicit `init --core-cmd` now persists development override, matching
explicit `core setup --core-cmd`. No dependency, backend production change,
manual version bump, or private Core access is introduced.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: Existing Typer, Rich, PyYAML, Pydantic, pathspec,
packaging, cryptography, and tomlkit dependencies; no new dependency
**Storage**: Project-local YAML/JSON/Markdown under `.verifysignal/`, including
canonical `.verifysignal/use-cases/<alias>.run-authority.json` safety authority
with crash-durable replacement and legacy YAML projections
**Testing**: pytest unit, contract, integration, Docker regression, and pinned
Core/Spec/backend product-truth journeys
**Target Platform**: Cross-platform CLI on Linux, macOS, and Windows
**Project Type**: Python CLI and coding-agent interface
**Performance Goals**: A blocked run preflight performs zero Core/runtime work;
existing list/readiness overhead remains within its 50 ms representative test
budget; entitlement checks retain existing Core-side performance gates
**Constraints**: Public Core CLI JSON only; fail closed on unknown schema;
single active run per resolved project/alias; exact-attempt CAS; no secret
persistence; additive workspace compatibility; fail-closed no-follow authority
paths; portable single-component authority names and fail-closed case-fold
collision detection; persisted-redirect/cooperating-process authority threat
model with handle-anchored prepared requests; red/green TDD before production
edits; no version hand-edit
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
  per-alias run lease, crash-durable authority ordering, strict WorkflowRun
  validation, canonical overlay/tombstone behavior, redirected-ancestor refusal,
  portable authority namespaces, recursive secret validation, native Windows
  safety gate, and lazy migration rules are explicit in the contracts. No
  constitutional exception or complexity waiver is needed.

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
├── workflows/                # shared preflight, run lease, rerun policy, transitions
└── workspace/                # models, canonical run authority, logical time, durable safe-path I/O

tests/
├── unit/                     # pure outcome, preflight, policy, transition tests
├── contract/                 # CLI/schema/backward-compatibility contracts
├── integration/              # workspace, Core invocation, and persistence journeys
└── fixtures/                 # production-shaped public Core outcomes/workspaces
```

**Structure Decision**: Keep the existing single-package architecture. Add
`core/outcomes.py`, `workflows/run_preflight.py`,
`workflows/run_lock.py`, `workflows/transitions.py`, and
`workspace/time_ordering.py` as focused boundaries; command modules remain thin
orchestration adapters. Extend existing model/repository/text-I/O modules rather
than introducing a second persistence system or runtime service.

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
- Validation writes `protectedOperationStatus: passed` only when the
  entitlement-protected `authoring-check` is invoked with `--runtime-readiness`
  and returns a schema-valid pass; any normalized runtime-readiness blocker
  writes `blocked`. Authoring-check without that flag keeps the protected proof
  `not-checked` and cannot advance WorkflowRun from `validate` to `run`.
- Resolve one effective entitlement API endpoint per protected command and
  thread it to both receipt selection and the source-runtime adapter's cached
  public-key lookup. A custom endpoint never reads the default endpoint cache.

### 2. Schema-aware Core outcome boundary

- Add `core/outcomes.py` with an operation-to-success-schema table and one
  `normalize_core_outcome(operation, response)` function. It returns a typed,
  redacted normalized outcome and never persists the raw response.
- Require the companion Core's entitlement dispatch to read a deeply immutable
  runtime-operation policy. An exported policy view cannot be mutated to move
  `run` into a compatibility-only class or bypass receipt verification.
- Accept the exact operation success schema or `verifysignal.error/v1`. Read
  top-level `error.code` first and legacy `data.findings[].code` second. Anything
  else becomes `core.contract-invalid`.
- For run success, read current Core identity from `data.summary.runId` and
  retain `data.runId` only as legacy compatibility. Require every present
  identity to satisfy the full portable single-component grammar and require
  both locations to agree when both exist; reject a missing, invalid, or
  conflicting identity before persistence.
- Preserve successful execution classification. For error envelopes, accept
  known-not-started only for an advertised entitlement code with the exact
  `false`/`pre-execution`/`false` execution tuple; non-entitlement,
  incomplete, or contradictory error metadata stays wholly unknown. An error
  envelope is never eligible for browser-run persistence.
- Route validate and run through the normalizer before readiness, history,
  coverage, first-run, confirmation, repair, or WorkflowRun mutation.

### 3. One run preflight, one rerun authority

- Wrap direct run in one non-blocking lease for the canonical resolved project
  plus portable alias before stage/preflight work. Hold it until all run and
  terminal-workflow handling exits. `workflow check run` probes the same lease
  without retaining a free lease; direct run remains the admission authority.
- Use `flock` on a private no-follow regular file in a per-user runtime
  namespace outside the mutable project plus an in-process key registry on
  POSIX, keyed by the opened project directory's `st_dev`/`st_ino` identity and
  case-folded alias. Use a global named mutex derived from the
  normalized/case-normalized resolved absolute path and case-folded alias on
  Windows. Both are crash-released. A project-local alias directory is
  compatibility scaffolding only and cannot define lease identity. Return
  `runtime.run-in-progress` for contention and
  `runtime.run-lock-unavailable` when trustworthy primitives cannot be
  established; neither path may resolve/invoke Core or create run state.
- Add a pure `workflows/run_preflight.py` decision builder used by both
  `workflow check run` and `commands.run`. It receives loaded metadata only and
  returns the contract in [run-preflight-rerun.md](contracts/run-preflight-rerun.md).
- Evaluate the decision before runtime resolution, environment loading,
  generated input resolution, prepared request creation, or Core invocation.
- Make `evaluate_rerun_decision()` classify the previous real outcome as
  no-commit, commit, or genuinely unknown and consume the corresponding policy
  branch. Explicit public `sideEffectMayExist: true` is runtime write-risk
  evidence and outranks an authored class of `none` or authenticated-read and a
  contradictory `executionState: not-started`; explicit false evidence remains
  safe only when no explicit runtime true boolean applies. Eliminate the
  independent legacy unknown-status gate.
- Preserve the existing violation-reconciliation path without weakening the
  conservative classification: `violated` remains `commit`/`afterCommit` and
  blocks an unchanged-policy rerun, while an observation-mode violation with no
  independent reached/post-commit/committed-status evidence or later run attempt
  may use an exact semantic owner policy change for one new attempt. Missing
  prior policy, unchanged policy, notes-only edits, confirmed commit evidence,
  and later attempts do not qualify; the next real run must provide clean latest
  evidence for strict pass.
- Validate risk authority before persistence across each contributing mapping,
  not only within one object. Boolean/text/`commitStep.reached` types are exact;
  text statuses are trimmed canonical tokens rather than whitespace-padded or
  ambiguous claims; and cross-mapping `commitStep.reached: true` cannot coexist
  with `postCommit: false`. Reject malformed or contradictory persisted state,
  while an already-decoded true/reached/strongly committed fact is evaluated
  conservatively and never downgraded by a safe claim.
- Reconcile the active confirmation artifact from that same decision on every
  preflight/list projection: replace a changed gate, remove a resolved gate, and
  preserve supersede reviews separately.
- Persist browser-run state only for a schema-valid `verifysignal.run/v1`.
  Track whether the invocation created its exact prepared-request file and remove
  only that file after a Core error. Never change prior run/evidence/repair state
  for an error envelope.
- After prepared-request ownership is resolved, persist a redacted,
  conservative write-ahead `lastCoreAttempt` immediately before Core invocation.
  Its initial state is unknown with `sideEffectMayExist: true`; a failed marker
  write prevents Core invocation and cleans only the invocation-owned request.
- Generate its identity at nanosecond precision strictly after all parseable
  prior attempt and last-run start/completion evidence, not merely after the
  current wall clock. This preserves newest-evidence ordering across equal or
  backward clock readings.
- Treat marker creation, refinement, and clear as exact-attempt CAS. Initial
  creation compares the prior observed marker identity/absence; later writes
  compare the invocation's `attemptedAt`. Ownership mismatch preserves the
  foreign marker and fails the stale invocation.
- Refine that same marker from public Core errors. Only an advertised
  entitlement error carrying exact `started: false`, `phase: pre-execution`,
  and `sideEffectMayExist: false` records `not-started`; missing,
  non-entitlement, or contradictory execution metadata remains `unknown`.
  Contract-invalid outcomes retain
  conservative `sideEffectMayExist: true` rather than trusting an absent/null
  execution projection. Adapter, normalization,
  post-response interpretation, and `record_run` failures retain conservative
  intent. A real run reuses `attemptedAt` as `startedAt`, receives a strictly
  later nanosecond `completedAt`, and clears the marker only after authoritative
  run persistence. If marker clearing fails afterward, the equal-start real run
  remains authoritative. The marker is not RunHistory but participates in the
  next rerun/confirmation decision.
- Make marker create/refine/clear, RunHistory creation, and lastRun update
  crash-durable. Flush the temporary file, atomically replace mutable authority,
  and durably order directory metadata on POSIX or use write-through replacement
  on Windows. Create RunHistory with the platform's native no-replace primitive;
  `(alias, runId)` is immutable and A,B,A reuse fails before any later
  authority/projection write.
  Preserve recoverable authority-before-projection ordering for marker writes,
  then RunHistory → canonical lastRun+marker → generic projection → canonical
  marker tombstone → generic projection for a real result; do not claim the
  multi-file chain is transactional.
- Persist run-safety state in the exact additive JSON authority
  `.verifysignal/use-cases/<alias>.run-authority.json` using schema
  `verifysignal-spec-run-authority/v1`. Keep only schema, alias,
  `lastCoreAttempt`, and `lastRun`; keep the same fields in `<alias>.yaml` as
  backward-compatible projections. Validate `lastRun` against the exact
  canonical projection allowlist. Apply one recursive secret scanner to
  mappings, secret-named containers, and nested lists with an iterative bounded
  traversal whose cycle/depth/size limits fail closed; reject
  credential-bearing URI and URI-reference userinfo/query/fragment, including
  scheme-less, network-path, relative-query, embedded prose, and bounded
  repeatedly encoded nested references, plus real Bearer/Basic or
  base64/base64url/high-entropy values before generic public-field exemptions.
  Apply high-entropy exemptions only when an exact public branch, identifier,
  structured code, schema-version, Core run ID, or path shape appears in its
  matching field context; accept both slash-separated and numeric
  single-component feature branches, and do not treat human-looking slugs in
  arbitrary prose as public. Treat an exact `credential` metadata leaf as
  secret-bearing without propagating that rule through validated public
  `credentialRefs` key-name structures.
  Do not parse an entire whitespace-containing/multiline prose scalar as one
  URI; scan its embedded references independently. Compound secret container
  names such as `apiToken` retain secret context through nested mappings/lists.
  Match compound `*_token` and bracketed provider query segments, scan content
  after Windows drive-prefix punctuation boundaries, and exempt only validated
  documented selector shapes with exactly one primary signal and typed
  token-policy shapes.
- Overlay canonical `lastCoreAttempt` and `lastRun` on every use-case load.
  Accept an absent/identical generic projection and let canonical state override
  only evidence proven older. Treat explicit nulls as durable tombstones rather
  than missing values when the projected marker is demonstrably stale, so an
  old generic writer cannot erase a newer run/attempt or resurrect a cleared
  marker. A base YAML or RunHistory entry with newer temporal evidence,
  conflicting identity at the same timestamp, or divergence with no
  reconcilable order fails closed; never timestamp-merge the documents. When no
  canonical file exists, retain legacy generic fields without an eager
  migration, but recover a unique newer valid RunHistory before preflight. A
  timestamp-less generic `lastRun` with no matching history remains readable and
  blocks the first canonical safety write as unorderable.
- Refine the durability sequence within each phase: write canonical marker then
  generic projection before Core; after a valid result write RunHistory,
  canonical authority containing the real `lastRun` plus the still-owned
  marker, then the generic projection; clear by writing the canonical null
  tombstone before the generic projection. Registry/output projection and
  WorkflowRun transition happen only after their preceding authority is safe.

### 4. WorkflowRun-authoritative transitions

- Add `workflows/transitions.py` with a single transition function that loads or
  lazily creates the active WorkflowRun, updates one stage, writes WorkflowRun
  as the authority, then derives the use-case reference and rendered state.
- Render stage state only from the updated WorkflowRun. Stage persistence must
  not call `state_document()` without a run.
- Use the transition boundary from authored-stage persistence, protected
  validation, and real run handling. Follow the transition table in
  [workflow-run.md](contracts/workflow-run.md).
- Guard protected commands before runtime resolution. Active workflows use
  WorkflowRun; the stage resolver returns the exact active WorkflowRun and that
  same instance supplies target confirmation for the rest of preflight, so a
  stale use-case reference cannot authorize a newer unconfirmed run. Validation
  is allowed from `validate`, `run`, or `repair`, and run only from `run`. A
  legacy staged use case with no WorkflowRun may derive
  only this pre-migration decision from the validated durable evidence accepted
  by lazy migration; the next workflow persistence creates WorkflowRun. Return
  `workflow.stage-out-of-order` for a valid position at the wrong stage and
  `workflow.authority-invalid` for an on-disk referenced authority that cannot
  be decoded or validated, without trusting mutable projections; ambiguous
  newest matching authorities receive the same fail-closed blocker.
- Validate every WorkflowRun authority before model decoding or newest selection:
  exact schema/workflow/path identity, portable alias/run ID, supported workflow/stage
  enums, exactly one state for every stage, required comparable workflow
  start/update timestamps, optional workflow/stage timestamps validated when
  present, structured blockers/gate decisions, exact safe target-confirmation
  shape, and secret/symlink rejection. Keep stage-level timestamps optional for
  legacy records, including pending stages. Any corrupt candidate declaring the
  requested alias fails authority resolution closed, even when a stale reference
  names an older valid run; unrelated-alias corruption does not displace the
  valid authority.
- Enforce the same bounded portable filename-component grammar for aliases,
  generated IDs, public run IDs, RunHistory, and WorkflowRun identities. Reject
  controls, trailing dot/space, and Windows device basenames case-insensitively,
  including before an extension. Scan RunHistory and WorkflowRun sibling
  namespaces before read/selection/write and fail closed when names differ only
  by case or the scan is unavailable.
- Require a completed workflow to have `currentStage: run`, `completedAt`, and a
  completed `run` state; require non-completed workflows to have null
  `completedAt`. Every predecessor of the current stage must be completed or
  skipped, except that the exercised repair path permits a failed `run`
  immediately before `repair`, and post-repair revalidation may retain completed
  repair history while `validate` and `run` are reset. Also enforce
  blocker/gate value types and the unique complete stage set. An equal-newest
  timestamp remains ambiguous even when the use-case projection references one
  tied candidate; the projection is not a tie-breaker.
- Generate each WorkflowRun `updatedAt` strictly after its prior timestamps and
  all parseable persisted workflow-run timestamps so one-nanosecond ordering is
  retained when the wall clock is equal or moves backward.
- Allow protected revalidation from later stages to reset future state before
  recording the new result. A successfully applied repair completes `repair`,
  resets `validate` and `run` to pending, and returns to `validate`
  without claiming either follow-up passed.
- Lazy migration is triggered only during a mutating workflow persistence call,
  is idempotent, selects the furthest authored stage from valid canonical
  documents, exact-schema plan/task projections with the same use-case alias,
  compatible durable workflow references, and executable references that
  resolve to actual project files, then backfills earlier authored stages.
  It copies any existing target confirmation into the new WorkflowRun without
  synthesizing a browser run, RunHistory, Core result, or evidence.
- Multi-file projection is coordinated but not transactionally atomic. Every
  mutating transition compares projections with WorkflowRun and heals an
  interrupted update; read-only surfaces render from WorkflowRun without writes.
- Resolve every canonical use-case/run-safety/WorkflowRun path without following
  redirects. Reject the file or any `.verifysignal/` ancestor that is a POSIX
  symlink or Windows junction/reparse point on reads and writes, fail closed on
  malformed/non-regular canonical authority, and never mutate an outside target.
  This ordinary authority guarantee covers redirects present at validation and
  cooperating Spec processes. Adversarial same-user component replacement
  between validation and ordinary authority I/O is outside the local-worktree
  threat model; prepared-request creation/cleanup remains handle-anchored against
  pathname replacement.

## Compatibility and Migration

- Do not rename or version-bump existing workspace schemas. New readiness fields
  are optional on read and always emitted on new writes.
- Preserve `legacy-auto` for an already-existing field-absent workspace.
  Distinguish it from a newly created record before writing defaults.
- Preserve older public Core errors without `execution`; classify execution as
  unknown and block without synthesizing a run. The conservative write-ahead
  marker exists before the call and is refined without changing its attempt
  timestamp.
- Preserve malformed/unknown Core compatibility conservatively: a
  contract-invalid run response cannot downgrade the write-ahead marker's
  `sideEffectMayExist: true` from untrusted execution data.
- Preserve legacy findings mapping only when no top-level public error code is
  available. Top-level public data always wins.
- Preserve all previous real run history, evidence references, repair sessions,
  readiness snapshots, supersede reviews, and target confirmation through
  migrations and blocked outcomes. Among execution-history and risk projections,
  an attempted `run` first writes `lastCoreAttempt`; Core errors refine it and
  its derived active confirmation gate, while a valid real run clears it only
  after `record_run`. Managed workflows additionally persist the normalized
  `run`-stage blocker and derived workflow projections.
  Authoring-check errors update validation, readiness, and workflow blockers
  without creating a rerun-attempt marker.
- Preserve old workspaces without a run-authority JSON file by reading their
  generic `lastCoreAttempt`/`lastRun` fields. The first new run-safety write
  creates the additive authority; from then on its values, including null
  tombstones against proven-stale state, override the YAML projections. A
  present invalid authority, a newer/conflicting/unorderable base or RunHistory
  projection, or an unallowlisted/secret `lastRun` is an error, never permission
  to fall back or merge.
- Treat protected execution by a pre-authority Spec binary after the canonical
  sidecar exists as an unsupported downgrade. A current reader reconciles only
  observable generic YAML/RunHistory footprints; it cannot recover an older
  process that invoked Core and persisted no evidence.
- Preserve stale projection compatibility without trusting it as authority:
  stage position and target confirmation for one protected preflight are both
  evaluated from the same resolved active WorkflowRun.
- The `.run-locks/<alias>` directory and per-user runtime lock file are internal
  coordination scaffolding, not workspace schema or persistent ownership
  claims. The live OS lock/mutex controls admission and is released on process
  termination.
- Existing `lastCoreAttempt` records remain readable. New writers add no field;
  they enforce exact-attempt ownership and logical timestamp ordering around the
  existing allowlist.
- No data-wide migration command is required. WorkflowRun migration happens
  lazily at the next workflow write. It infers the furthest durable legacy
  authored stage and backfills earlier stages, but never rebuilds an on-disk
  referenced authority that cannot be decoded or validated, or invents browser
  execution/evidence.
  Readiness fields upgrade at the next validation write, and only a protected
  validation attempt may upgrade protected readiness.

## TDD and Delivery Sequence

1. Record baseline focused and full-suite results without changing production.
2. For each user story, add production-shaped regression tests and run them to
   the expected diagnosed failure; commit the red tests separately.
3. Implement the smallest coherent policy/model changes to make that story
   green; run adjacent regression tests before refactoring.
4. Rebase on the current `origin/main` and establish the immutable repository
   tuple before final evidence.
5. Against that tuple, rerun the focused/full Spec suites, every acceptance row,
   and the Ubuntu/native-Windows portability and safety gates. The Windows gate
   runs the native durable-create no-replace regression and both portable
   workspace-layout and RunHistory-filename modules in addition to the mutex,
   redirected-path, and prepared-handle suites.
6. Run pinned Docker verification and browser product-truth against the
   companion Core worktree, then reproduce the localized-home positive browser
   path in an isolated workspace and run deterministic fake-Core current/legacy
   error controls separately.
7. Run `/speckit-analyze` only after all final evidence is green and resolve every
   remaining Critical/High finding.
8. Repeat every affected gate if any tuple revision moves before opening the PR.
   The stable `spec` context must require
   the Ubuntu suite, native `windows-safety`
   mutex/write-through/authority-path/portable-name tests, including native
   `test_durable_create_is_native_no_replace_and_leaves_no_temporary_file` plus
   `test_workspace_layout_portability.py` and
   `test_run_history_filename_portability.py`, and the independent Windows
   installer journey. Open the PR only after that final analysis.

The expected Spec release class is **patch**, declared by PR title
`fix: preserve protected preflight without synthetic runs`. Version files remain
untouched in the PR.

## Complexity Tracking

No constitution violations or avoidable architecture exceptions are required.
