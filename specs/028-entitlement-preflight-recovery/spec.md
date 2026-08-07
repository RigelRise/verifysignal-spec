# Feature Specification: Entitlement Preflight Recovery

**Feature Branch**: `028-entitlement-preflight-recovery`
**Created**: 2026-08-05
**Status**: Validation in progress
**Input**: Recover the Golden Path after a valid protected Core operation was
rejected before execution, without creating a synthetic browser run or false
write-risk state.

## Constitution Alignment

- **Public Core boundary**: Spec consumes only advertised public Core operation
  schemas and the public `verifysignal.error/v1` envelope. It does not inspect
  Core source, private packages, or report internals.
- **Project-local portability**: Runtime mode, readiness, run history,
  confirmation gates, and WorkflowRun state remain under `.verifysignal/` and
  work identically through the CLI, Codex, and Claude integrations.
- **Secret safety**: Normalized outcomes and persisted state contain only
  allowlisted public projections. One recursive scanner covers mappings,
  secret-named containers, and deeply nested lists before every affected write;
  receipt, key, signature, credential, and environment values remain
  excluded.
- **Agent-neutral interface**: Direct CLI execution and workflow prerequisite
  checks share the same decision contract instead of relying on an agent's
  narrative or inferred state.
- **Testable delivery**: Every priority story has a red/green regression path,
  public-contract coverage, workspace migration coverage, and an independently
  repeatable acceptance scenario.

## User Scenarios & Testing

### User Story 1 - Start with an intentional Core runtime (Priority: P1)

As a developer starting VerifySignal in a repository, I want a new workspace to
choose the managed Core deliberately, so an unrelated adjacent source checkout
cannot silently replace the supported runtime.

**Independent Test**: Create one new workspace and one legacy workspace while
workspace, environment, PATH, and ancestor-sibling Core candidates are all
discoverable. The new workspace uses managed-only resolution; the legacy
workspace preserves legacy automatic resolution; an explicit local-Core setup
enters development override mode.

**Acceptance Scenarios**:

1. Given a repository without `.verifysignal/workspace.yaml`, when initialization
   completes, then the workspace records `coreResolutionMode: managed-only`.
2. Given a pre-existing workspace whose record has no resolution-mode field,
   when it is loaded, then it retains legacy automatic resolution without an
   implicit migration.
3. Given a new managed-only workspace with local Core candidates in every
   supported discovery source, when Core is resolved, then none of those local
   candidates is selected.
4. Given an explicit `init --core-cmd` or `core setup --core-cmd`, when setup
   succeeds, then the workspace records `development-override` and the selected
   command intentionally.

---

### User Story 2 - Know what protected readiness actually proves (Priority: P1)

As a developer validating a use case, I want readiness and Core failures to
state exactly what was checked, so command compatibility is never mistaken for
a successful protected operation.

**Independent Test**: Exercise a compatible Core with ready trust inputs, first
with protected authoring validation without runtime-readiness proof and then
with `--runtime-readiness`, followed by a public entitlement error, a legacy
error without execution metadata, and an unknown schema. Verify each readiness
layer and recovery classification is truthful and deterministic.

**Acceptance Scenarios**:

1. Given a compatible command and available trust inputs but no protected call,
   when readiness is reported, then compatibility and trust are distinguished
   from protected-operation status and the protected status is `not-checked`.
2. Given validation invokes the entitlement-protected `authoring-check` with
   `--runtime-readiness` and it passes, when validation completes, then
   protected-operation readiness is `passed` and run may become available.
3. Given validation that invokes the entitlement-protected `authoring-check`
   without `--runtime-readiness`, when its authoring checks pass, then the
   protected runtime-readiness proof remains `not-checked` and run remains
   unavailable.
4. Given `run` returns `verifysignal.error/v1` with a top-level entitlement code
   and explicit pre-execution metadata, when Spec normalizes the response, then
   it reports a blocked, not-started outcome with the mapped blocker code.
5. Given `run` returns an older public Core error without execution metadata,
   when it is normalized, then execution remains unknown, the response is never
   treated as a browser run, and a redacted non-run attempt marker preserves
   that uncertainty.
6. Given a response whose schema is not valid for the invoked operation, when it
   is normalized, then Spec fails closed with `core.contract-invalid`.
7. Given a caller attempts to mutate Core's exported runtime-operation policy,
   when `run` is invoked afterward, then its protected classification and
   entitlement guard remain unchanged.

---

### User Story 3 - Block safely before a real run and rerun consistently (Priority: P1)

As a developer running a use case, I want direct run and workflow check to make
the same preflight decision, so blocked validation, a pre-execution Core error,
or stale risk state cannot create a fake run or an unnecessary confirmation.

**Independent Test**: Compare `workflow check run` and direct `run` over a table
of missing prerequisites, blocked validation, valid first run, no-commit prior
run, committed prior run, genuinely unknown write outcome, and stale active
confirmation. Inject failures before invocation, after the Core response, and
during authoritative run persistence. Assert Core invocation, write-ahead
intent, persistence, and confirmation lifecycle match the shared decision in
every row.

**Acceptance Scenarios**:

1. Given a use case that is not ready or lacks protected-operation readiness,
   when either run entry point is used, then both return the same blocker and
   Core is not resolved or invoked.
2. Given a valid Core run-result schema, when Core reports a real passed or
   failed browser run, then run history, gate coverage, evidence references, and
   repair state may be updated from that result.
3. Given any Core error envelope, when run returns, then no new run ID, run
   history, gate coverage, evidence, last-run, repair, or write-risk state is
   synthesized; the pre-invocation redacted non-run attempt marker is refined
   from the public outcome, and only a confirmation derived from genuine
   unknown write risk may also change.
4. Given a pre-execution outcome with explicit false side-effect evidence, or
   explicit false post-commit and side-effect-may-exist values, when rerun policy
   is evaluated, then `afterNoCommit` is used unless newer runtime evidence
   explicitly says `sideEffectMayExist: true`.
5. Given confirmed or inferred commit evidence, when rerun policy is evaluated,
   then `afterCommit` is used.
6. Given a genuinely indeterminate outcome for a write or external-notification
   use case, or public runtime evidence that a side effect may exist, when rerun
   policy is evaluated, then `afterUnknown` is used for a non-run attempt even
   if the authored class is `none` or a contradictory persisted execution label
   says `not-started`.
7. Given a class-`none` use case with explicit false no-side-effect evidence,
   when a prior error is inspected, then no `unknown-write-risk` confirmation
   is generated.
8. Given an active confirmation whose underlying requirement no longer exists,
   when preflight is recalculated, then the active artifact is removed or
   replaced while supersede reviews remain available for audit.
9. Given a run error without trusted execution metadata for a write use case,
   when the next preflight is evaluated, then the non-run attempt selects
   `afterUnknown`; only an advertised entitlement error with the exact
   `started: false`, `phase: pre-execution`, and
   `sideEffectMayExist: false` tuple selects `afterNoCommit` and clears any
   stale unknown-risk gate.
10. Given direct run has resolved prepared-request ownership, when it is ready to
    invoke Core, then it durably writes a conservative unknown `lastCoreAttempt`
    first; if that write fails, Core is not invoked and only an exact
    invocation-owned request is cleaned up.
11. Given a schema-valid real run, when post-response interpretation or
    `record_run` fails, then the conservative attempt remains; when `record_run`
    succeeds, its start time equals the attempt time, its completion time is
    strictly later, and only then may the attempt marker be cleared.
12. Given one run already holds the lease for a resolved project and alias, when
    workflow check or a second direct run is requested for that same tuple, then
    it returns `runtime.run-in-progress`, invokes Core zero times, and creates no
    attempt or run state; a different alias remains independently runnable.
13. Given the platform cannot establish its trustworthy run lease, when run
    admission is evaluated, then it fails closed with
    `runtime.run-lock-unavailable` before Core or workspace run-state mutation.
14. Given a stale invocation attempts to refine or clear a marker it no longer
    owns, when persistence compares attempt identity, then exact-attempt CAS
    rejects the write and preserves the newer marker. Given the wall clock moves
    backward, a new attempt still orders strictly after all prior run/attempt
    evidence.
15. Given a malformed or contract-invalid Core response, when the write-ahead
    marker is refined, then its side-effect uncertainty remains conservatively
    true even for an authored class of `none`.
16. Given a generic use-case projection is absent, identical, or demonstrably
    older than canonical run evidence, when the use case is loaded, then
    `.verifysignal/use-cases/<alias>.run-authority.json` overlays both
    `lastCoreAttempt` and `lastRun`; explicit null tombstones override only
    demonstrably stale projection values, so an old writer cannot erase or
    resurrect safety state.
17. Given the canonical run-authority document is malformed, has the wrong
    schema/alias/field shape, contains an unallowlisted or secret-looking
    `lastRun` value, is a symlink, or is reached through a symlink or Windows
    reparse-point ancestor, when run state is loaded or written, then the
    operation fails closed without falling back to the generic use-case
    projection or writing outside the project.
18. Given a valid browser result, when run state is persisted, then durable
    ordering is RunHistory first, canonical authority with the completed
    `lastRun` and still-owned marker second, generic use-case projection third,
    and the canonical marker tombstone only after those authorities are durable.
19. Given generic YAML or RunHistory contains strictly newer run evidence, an
    equal-time divergent identity or risk value, or safety evidence that cannot
    be ordered against canonical state, when the use case is loaded, then it
    fails closed rather than discarding, merging, or silently preferring either
    document; comparison covers each run-safety slot and the newest evidence
    across slots.
20. Given a public run ID, use-case alias, generated ID, RunHistory filename, or
    WorkflowRun filename that is valid on one supported host but not portable to
    another, or two authority siblings that differ only by case, when the value
    is decoded, selected, or written, then the operation fails closed before
    mutation instead of creating a Windows/POSIX-dependent authority.
21. Given RunHistory identities A and B have been durably recorded in that
    order, when another result attempts to reuse A, then persistence rejects the
    reuse before changing any authority or projection bytes: the original A
    document remains byte-identical and B remains the canonical `lastRun`.

---

### User Story 4 - Resume from one authoritative workflow state (Priority: P1)

As a developer resuming a staged workflow, I want the WorkflowRun, use-case
reference, and rendered workflow state to agree, so the next stage and completed
work are recoverable after any command or agent handoff.

**Independent Test**: Persist every authoring stage, validate once successfully
and once with a protected preflight blocker, complete one real run, fail one real
run, and load one legacy use case without a WorkflowRun. After every transition,
compare the three persisted projections.

**Acceptance Scenarios**:

1. Given an active WorkflowRun, when an authoring stage is persisted, then its
   stage state is completed and all three workflow projections advance together.
2. Given a successful protected validation from `validate`, `run`, or
   `repair`, when state is persisted, then later-stage state is reset as
   needed and the current stage becomes `run`; given blocked protected
   validation, it becomes `validate` with blockers.
3. Given validation invokes `authoring-check` without `--runtime-readiness`, when
   its result is persisted, then the WorkflowRun remains at `validate` and does
   not claim protected runtime readiness.
4. Given a valid passed run result, when state is persisted, then the workflow
   completes; given a valid failed run result, it advances to `repair`.
5. Given a pre-execution Core error, when state is persisted, then the workflow
   keeps `run` as the current stage, marks that stage blocked with the normalized
   blocker, and does not claim the run was executed or failed.
6. Given a successfully applied repair, when its workflow transition is
   persisted, then `repair` is completed, `validate` and `run` are reset
   to pending, and the current stage becomes `validate`.
7. Given a protected command at an ineligible workflow stage or an unreadable
   referenced WorkflowRun, when preflight is evaluated, then it returns
   `workflow.stage-out-of-order` or `workflow.authority-invalid` before
   resolving or invoking Core.
8. Given a legacy use case with no WorkflowRun, when the next stage is persisted,
   then one WorkflowRun is created from the furthest durable authored-stage
   evidence, earlier stages are backfilled, target confirmation is preserved,
   and no browser run or evidence is synthesized.
9. Given a stale use-case projection references an older confirmed WorkflowRun
   while authority recovery selects a newer unconfirmed WorkflowRun, when run
   preflight is evaluated, then both stage eligibility and target confirmation
   use that same newer authority and execution remains blocked.
10. Given an alias-matching WorkflowRun candidate violates any authority
    invariant, when active authority is resolved, then the candidate fails the
    command closed with `workflow.authority-invalid`; corruption belonging only
    to another alias does not displace the valid authority for this alias.
11. Given a WorkflowRun claims completion without `currentStage: run`, a
    completion timestamp, and a completed `run` state; a non-completed workflow
    carries `completedAt`; or a current stage has an incomplete predecessor,
    when it is loaded or selected, then strict validation rejects it before any
    projection or Core action is used. The exercised repair path permits a
    failed `run` immediately before `repair`, and revalidation after repair may
    retain completed repair history while `validate` and `run` are pending.
    Legacy stage-level `startedAt`/`completedAt` remain optional and are
    validated only when present.
12. Given two matching WorkflowRuns share the newest exact nanosecond timestamp,
    when one is referenced by the use-case projection, then the tie remains
    ambiguous and fails closed; a mutable reference cannot break an authority
    tie. A WorkflowRun file or any authority ancestor that redirects through a
    symlink/reparse point is rejected on both read and write.
13. Given `Run-A.yaml` and `run-a.yaml` coexist or a new WorkflowRun would collide
    with an existing sibling after Unicode-independent ASCII case folding, when
    authority is selected or saved, then it fails closed rather than allowing a
    case-sensitive host to create state that collapses on a default Windows
    filesystem.

## Requirements

### Functional Requirements

#### Runtime selection and readiness

- **FR-001**: A genuinely new workspace MUST persist
  `coreResolutionMode: managed-only` during initialization.
- **FR-002**: A pre-existing workspace without `coreResolutionMode` MUST remain
  valid and MUST continue to resolve as `legacy-auto` until an explicit runtime
  selection command changes it.
- **FR-003**: Managed-only resolution MUST ignore workspace local commands,
  environment overrides, PATH candidates, and ancestor-sibling candidates.
- **FR-004**: Successful explicit `init --core-cmd` and
  `core setup --core-cmd` operations MUST persist `development-override`.
- **FR-005**: Runtime selection output MUST expose the effective resolution mode
  and selected source without exposing command secrets or trust material.
- **FR-006**: Readiness schema v1 MUST add
  `commandCompatibilityStatus`, `trustMaterialStatus`,
  `protectedOperationStatus`, and `readinessScope` without changing its schema
  identifier.
- **FR-007**: Command compatibility and protected-operation statuses MUST be one
  of `not-checked`, `passed`, or `blocked`; trust-material status MUST be one of
  `not-checked`, `ready`, or `blocked`.
- **FR-008**: `readinessScope` MUST be either `command-and-trust-inputs` or
  `protected-operation`.
- **FR-009**: Command compatibility and trust-material availability MUST NOT be
  described as protected-operation readiness.
- **FR-010**: Run readiness MUST require a current readiness snapshot whose
  protected-operation scope and status are both passed.
- **FR-011**: Legacy readiness snapshots without the additive fields MUST load
  safely as command-and-trust-input readiness with protected status not checked.
  Every source-runtime protected invocation MUST load cached public verification
  keys from the same effective entitlement API endpoint used to select its
  receipt; an endpoint override MUST NOT fall back to the default endpoint's
  key cache.

#### Public Core outcomes

- **FR-012**: Spec MUST normalize each protected Core response at one shared,
  schema-aware boundary before any command interprets or persists it. The
  companion Core runtime-operation classification used by the entitlement guard
  MUST be immutable for the process lifetime: mutating an exported policy view
  MUST NOT reclassify `run` or bypass its receipt requirement.
- **FR-013**: A successful protected response MUST match the exact advertised
  public schema and schema version for the operation that was invoked, contain
  mapping-shaped public data, and, for `run`, contain one unambiguous,
  non-empty portable public run ID satisfying FR-057 before it is eligible for
  persistence.
  Current Core identity at `data.summary.runId` is authoritative;
  legacy `data.runId` remains accepted, but when both locations are present
  they MUST be equal and valid or the response is contract-invalid.
- **FR-014**: `verifysignal.error/v1.error.code` MUST be the primary public Core
  error-code source.
- **FR-015**: `data.findings[].code` MUST remain supported only as a legacy
  fallback when a top-level public error code is absent.
- **FR-016**: An unexpected or malformed schema or envelope MUST normalize to
  `core.contract-invalid`, redact unadvertised schema/error identifiers, direct
  the user to Core/Spec compatibility recovery, and fail closed. Its persisted
  run-attempt refinement MUST retain `sideEffectMayExist: true`; untrusted or
  missing execution metadata MUST NOT downgrade write-ahead risk.
- **FR-017**: Successful outcomes MAY preserve a complete public execution unit.
  For an error outcome, Spec MUST classify execution as known-not-started only
  when the public code is an advertised entitlement error and the complete unit
  is exactly `started: false`, `phase: pre-execution`, and
  `sideEffectMayExist: false`. A non-entitlement error, incomplete unit,
  contradictory value, or unadvertised phase MUST normalize all execution
  fields to unknown.
- **FR-018**: Missing or untrusted public execution metadata MUST remain
  unknown; Spec MUST NOT infer browser execution from an error envelope and
  MUST preserve the uncertainty in a redacted non-run attempt marker.
- **FR-019**: Normalized output and every affected persisted authority MUST NOT
  contain raw receipts, signatures, verification keys, environment values, or
  credentials. The shared secret scanner MUST recurse through mappings,
  secret-named mapping/list containers, and nested sequences iteratively while
  preserving secret-field context to scalar leaves. Cycles, excessive depth, or
  excessive node counts MUST return a blocking secret-safety finding rather
  than raise or silently skip content. For every scalar it MUST
  reject credential-bearing URI or URI-reference userinfo and secret
  query/fragment parameters, including scheme-less credential references,
  network-path references, relative query references, and secret-bearing
  references embedded in prose, including bounded repeatedly encoded nested
  references, plus real Bearer/Basic credentials and opaque base64/base64url or
  other high-entropy values, before applying generic public-metadata field
  exemptions. A high-entropy branch, identifier, structured code,
  schema-version, Core run ID, or path MAY be exempt only in its matching field
  context and only when it has the exact public shape. Slash-separated and
  numeric single-component feature branches are public branch shapes. Exact
  structured Core/error codes are public only in the documented code fields.
  An exact `credential` leaf MUST remain secret-bearing, including below
  runtime-output metadata, without invalidating validated public
  `credentialRefs` key-name structures; ordinary prose MUST receive no generic
  slug/path exemption. Secret query keys include compound `*_token`
  names and provider credential/signature segments in bracketed/array forms
  while public near-matches remain allowed. A Windows drive-relative value MUST
  be rescanned after a whitespace or punctuation boundary.
  Whitespace-containing or multiline prose MUST NOT be parsed as one URI
  reference; its embedded references MUST be scanned independently, and all
  other field-name, credential, and entropy detectors still apply. Compound
  secret container aliases such as `apiToken` MUST preserve secret-field context
  through nested mappings/lists unless an exact documented public container
  shape is validated. Selector aliases are public only inside documented
  selector collections with exactly one primary signal and typed modifiers;
  `tokenPolicy` is public only with its documented scalar types and enum values.
  Malformed public-container candidates MUST fail closed without raising and
  MUST retain secret context for descendants. Only exact public
  digest/reference shapes MAY use narrower allowlists, and validation MUST
  complete before any affected write.

#### Run preflight and result lifecycle

- **FR-020**: After the shared concurrency admission gate, `workflow check run`
  and direct `run` MUST use one pure durable-state preflight decision and expose
  equivalent blockers, confirmation requirements, rerun decisions, and recovery
  actions.
- **FR-021**: Run preflight MUST complete before runtime resolution, environment
  input loading, prepared-request creation, or Core invocation.
- **FR-022**: Preflight MUST evaluate target confirmation, required artifacts,
  use-case readiness, protected-operation readiness, side-effect policy, and
  rerun policy.
- **FR-023**: A blocked preflight MUST invoke Core zero times and MUST create no
  run, evidence, prepared-request, repair, or active confirmation side effects
  beyond reconciling the current confirmation gate. Internal lock directories
  and per-user runtime lock files created while establishing an OS-owned lease
  are coordination scaffolding, not run state or persistent ownership evidence.
- **FR-024**: Only a valid `verifysignal.run/v1` response MAY create or update
  run history, last run, gate coverage, evidence/report references, repair
  recommendations, or first-run execution state.
- **FR-025**: A Core error response during run MUST return a blocked/not-started
  or blocked/execution-unknown result with the normalized Core code and execution
  classification.
- **FR-026**: Invocation-created prepared artifacts MUST be removed after a Core
  error by deleting only the exact file created by that invocation; user-authored,
  pre-existing, or merely adjacent prepared artifacts MUST be preserved. File
  creation and cleanup MUST remain anchored either to a no-follow project
  directory descriptor or, on Windows, to locked non-reparse ancestor handles
  plus the exact created-file handle, so replacing a pathname cannot redirect
  deletion; a platform without either safe primitive set MUST fail closed.
- **FR-027**: Immediately before Core invocation, and after prepared-request
  ownership resolution, direct run MUST durably write a conservative
  `lastCoreAttempt` with unknown execution and `sideEffectMayExist: true`. If
  that write fails, Core MUST be invoked zero times and only the exact
  invocation-owned prepared request MAY be cleaned up. A Core error or
  unclassifiable response MUST refine the same marker while preserving all
  prior run history, evidence, repair sessions, readiness snapshots, and
  last-run state unchanged. For a managed workflow it MUST also persist the
  normalized blocker on the authoritative `run` stage and its derived workflow
  projections without recording the attempt as executed or failed.
- **FR-028**: `lastCoreAttempt` MUST contain only attempted time, operation,
  public schema/status/error code, `not-started` or `unknown` execution state,
  and allowlisted side-effect uncertainty; its write-ahead form uses status
  `unknown`, null schema/error code, execution `unknown`, and
  `sideEffectMayExist: true`. It MUST contain no paths or secret values. The
  local timestamp MUST retain nanosecond precision, and attempt-scoped
  confirmation identity MUST be derived from all of these allowlisted fields
  without adding another persisted identifier.
- **FR-029**: The write-ahead marker MUST remain durable through Core response
  normalization, post-response interpretation, and authoritative `record_run`.
  A schema-valid run MUST use the marker's `attemptedAt` as `startedAt`, persist
  a `completedAt` strictly later even if the wall clock does not advance, and
  clear the marker only after `record_run` succeeds. If clearing then fails, the
  equal-start real run MUST remain authoritative over the marker. If
  `record_run` fails after a real `lastRun` becomes durable, that equal-start
  real run MUST likewise outrank the retained marker. A public error MUST refine
  the same attempt timestamp, and explicit not-started evidence MUST replace its
  conservative unknown classification.

#### Rerun and confirmation authority

- **FR-030**: One rerun evaluator MUST be authoritative for workflow checks,
  direct run, list/status presentation, and confirmation generation.
- **FR-031**: With no prior real run or later run attempt, the evaluator MUST
  return `allowed`.
- **FR-032**: Explicit not-started together with explicit false side-effect
  evidence, or explicit no-commit/no-side-effect evidence, MUST select
  `afterNoCommit` only when no newer explicit runtime true boolean applies.
- **FR-033**: Confirmed or inferred commit evidence, including a side-effect
  policy `violated` outcome, MUST select `afterCommit`. A blind rerun under the
  unchanged policy MUST remain blocked. The existing owner-reconciliation path
  MAY permit one new attempt only when the violated run used observation mode,
  contains no independent reached/post-commit/committed-status evidence, has no
  later run attempt, and the owner made an exact semantic policy change. A
  missing prior policy, unchanged policy, notes-only edit, confirmed commit, or
  later run attempt MUST NOT qualify, and the prior classification MUST remain
  in history until a newer real run becomes authoritative.
- **FR-034**: A newer `lastCoreAttempt` with unknown execution for a write or
  external-notification run MUST select `afterUnknown` without becoming run
  history. "Newer" is a strict temporal comparison; an equal or unparseable
  timestamp cannot override a timestamped real run.
- **FR-035**: Only a genuinely indeterminate write/external-notification outcome
  or explicit public `sideEffectMayExist: true` evidence MUST select
  `afterUnknown` for a non-run attempt. The runtime boolean is itself write-risk
  evidence and MUST outrank an authored class of `none` or authenticated-read
  and any contradictory `executionState: not-started` projection.
- **FR-036**: A class-`none` or authenticated-read use case with explicit false
  side-effect evidence MUST NOT generate `unknown-write-risk`; prior evidence of
  a real write, including explicit public `sideEffectMayExist: true`, MUST remain
  conservatively classified.
- **FR-037**: Active confirmation persistence MUST be reconciled from the current
  authoritative decision: replace a changed gate and delete a gate that is no
  longer required, while preserving supersede reviews as historical audit data.
  Approval and supersede commands MUST perform this reconciliation before they
  return.

#### Workflow state authority

- **FR-038**: WorkflowRun MUST be the authoritative workflow-stage state for an
  active use case.
- **FR-039**: Each stage transition MUST update the WorkflowRun first and derive
  its use-case reference and rendered state from that authority. Because the
  files are not transactionally atomic as a group, the next mutating workflow
  transition MUST detect and heal an interrupted projection update from the
  WorkflowRun. Read-only surfaces MUST render from WorkflowRun without mutation.
- **FR-040**: Only validation that invokes `authoring-check` with
  `--runtime-readiness` and receives a normalized passing response MAY complete
  `validate` and advance to `run`. Validation without that flag MUST leave the
  authoritative workflow at `validate` without minting protected runtime
  readiness. Runtime-readiness revalidation MUST be permitted from `validate`,
  `run`, or `repair`, reset later-stage state before recording the new result,
  and return to `run` only on a pass; a blocker MUST remain at `validate` with
  structured blockers.
- **FR-041**: A valid passed run MUST complete the workflow; a valid failed run
  MUST advance to `repair`; a Core error MUST keep the `run` stage blocked with
  normalized blockers and MUST NOT record it as executed or failed.
- **FR-042**: Stage rendering MUST preserve existing stage statuses and MUST NOT
  reconstruct an all-pending stage list when a WorkflowRun exists.
- **FR-043**: On the next workflow persistence only, a legacy use case without a
  WorkflowRun MUST receive one lazy, idempotent migration. Migration MUST select
  the furthest authored stage supported by valid canonical documents, compatible
  durable workflow references, or project-relative executable references that
  resolve to actual regular non-symlink files, then backfill every earlier
  authored stage. It MUST preserve target confirmation and MUST NOT synthesize a
  browser run, RunHistory, Core result, discover/gate/evidence artifacts, task
  execution status, or repair result.
- **FR-044**: A successfully applied repair at `repair` MUST complete that stage,
  reset `validate` and `run` to pending, and advance to `validate`
  without claiming that revalidation or rerun has passed.
- **FR-045**: Protected command stage checks MUST occur before runtime resolution
  or Core invocation. An active workflow MUST use WorkflowRun authority. A
  stage resolver MUST return the exact active WorkflowRun it used, and target
  confirmation for that preflight MUST be evaluated from that same instance,
  never from a second lookup through a stale use-case projection. A
  legacy staged use case with no WorkflowRun MAY derive this one pre-migration
  decision only from the validated durable evidence permitted by FR-043; its
  next workflow persistence MUST create the authority. An ineligible current
  stage MUST return `workflow.stage-out-of-order` with current/requested stages
  and a recovery command.
- **FR-046**: An on-disk referenced WorkflowRun that exists but cannot be
  decoded or pass strict authority validation, any alias-matching corrupt
  candidate, or ambiguous newest matching authorities MUST fail closed with
  `workflow.authority-invalid` and MUST NOT fall back to use-case or
  rendered-state projections, resolve Core, or invoke Core. Validation MUST
  cover exact schema/workflow/path identity, portable FR-057 alias/run identity,
  enumerated workflow
  and stage states, complete unique stage coverage, required workflow
  start/update timestamps, and the validity of optional workflow/stage
  timestamps when present. Stage-level `startedAt`/`completedAt` MUST remain
  optional for legacy compatibility; pending stages MUST NOT be rejected merely
  because they omit temporal evidence. A
  completed workflow MUST have `currentStage: run`, `completedAt`, and a
  completed `run` state; every non-completed workflow MUST have null
  `completedAt`; and every predecessor of the current stage MUST be completed or
  skipped, except that the exercised repair transition permits a failed `run`
  immediately before `repair` and post-repair revalidation may retain completed
  repair history while `validate` and `run` are reset. Validation MUST also
  cover typed blocker and gate-decision structure, target-confirmation
  shape/source, secret safety, and direct or ancestral symlink/reparse-point
  refusal. Equal newest timestamps MUST remain ambiguous even when one candidate
  is named by a mutable use-case reference.
  Unreferenced unstructured files and unreferenced candidates whose declared
  alias differs from the requested alias MUST NOT displace a valid matching
  authority; an explicitly referenced wrong-alias document remains invalid
  authority.

#### Run concurrency, ownership, and durability

- **FR-047**: Direct run MUST acquire one non-blocking, crash-released lease for
  the canonical resolved `(project, alias)` before stage/preflight evaluation and
  MUST hold it through Core handling, authoritative persistence, and terminal
  workflow updates. At most one direct run for that tuple MAY be active; another
  alias uses an independent lease.
- **FR-048**: On POSIX, the lease MUST use an exclusive non-blocking `flock` on
  a private, no-follow regular file in a per-user runtime namespace outside the
  mutable project, keyed by a digest of the opened project directory's
  `st_dev`/`st_ino` identity plus the portable alias after case folding, plus an
  in-process ownership registry. A project-local
  `.verifysignal/.run-locks/<alias>` directory MAY remain as non-authoritative
  compatibility/observability scaffolding; replacing it MUST NOT mint a second
  lease. On Windows, the lease MUST use a global named mutex derived from the
  normalized/case-normalized resolved absolute project path plus the
  case-folded alias. Process termination MUST release either lease.
  Unsupported or unsafe primitives MUST fail closed rather than trust a stale
  lock/PID file.
- **FR-049**: An occupied lease MUST produce `runtime.run-in-progress`; inability
  to establish a trustworthy lease MUST produce
  `runtime.run-lock-unavailable`. Direct run and `workflow check run` MUST expose
  the same current admission blocker, invoke Core zero times, and create no
  prepared request, `lastCoreAttempt`, RunHistory, or lastRun. Workflow check MAY
  probe and immediately release a free lease; direct run remains the final
  admission authority.
- **FR-050**: Initial marker creation MUST compare against the exact prior
  `attemptedAt` or absence observed by that invocation. Every refinement and
  clear MUST compare against that invocation's exact `attemptedAt`. A mismatch
  MUST fail without overwriting or clearing the marker currently on disk.
- **FR-051**: New attempt identity MUST be a canonical nanosecond UTC timestamp
  strictly later than every parseable prior `lastRun.startedAt`,
  `lastRun.completedAt`, and `lastCoreAttempt.attemptedAt`, even when the system
  clock is equal or moves backward. Run completion MUST be strictly later than
  its start. WorkflowRun update ordering MUST retain nanosecond precision and
  advance beyond prior persisted workflow timestamps.
- **FR-052**: Marker creation/refinement, lastRun update, and marker clear MUST
  use crash-durable atomic replacement. RunHistory MUST instead use a
  crash-durable native create-without-replacement primitive: an existing
  `(alias, runId)` identity is immutable, and a losing concurrent create or
  later A,B,A reuse MUST fail before any authority/projection mutation. The
  writer MUST flush file contents before replacement or create and durably
  order directory metadata (`fsync` of the parent directory on POSIX;
  write-through replacement/create on Windows). The durable order MUST remain
  canonical marker then generic
  projection before Core; for a valid result, RunHistory then canonical
  authority containing `lastRun` plus the still-owned marker, then generic
  use-case projection, and only afterward the canonical marker tombstone plus
  its generic projection. This ordered sequence is recoverable but MUST NOT be
  described as a transaction across multiple files.
- **FR-053**: New run-safety writes MUST create
  `.verifysignal/use-cases/<alias>.run-authority.json` with exact schema
  `verifysignal-spec-run-authority/v1`, the matching portable FR-057 alias, and only
  `lastCoreAttempt` and `lastRun` in addition to schema/identity. The generic
  `<alias>.yaml` fields remain compatibility projections, not safety authority.
  `lastRun` MUST use the fixed real-run projection allowlist produced by
  `record_run`; unknown fields, invalid identity/types/timestamps, and
  recursively secret-looking values MUST invalidate the authority.
- **FR-054**: When canonical run authority exists, every use-case load MUST
  compare its two safety slots with generic YAML and RunHistory by attempt
  timestamp, run completion timestamp falling back to run start, identity/risk
  content, and the newest evidence across both slots. Canonical values MUST
  accept an absent or identical projection and override only strictly older
  evidence. Explicit nulls MUST act as tombstones only against demonstrably
  stale projected values. Strictly newer evidence, equal-time divergent
  identity/risk, or divergence without a reconcilable order MUST fail closed
  rather than be discarded or timestamp-merged. A stale generic writer MUST NOT
  erase a newer marker/real run or resurrect a cleared marker. Absence of the
  new authority file MAY retain the legacy generic fields without requiring
  eager migration. Before preflight, a sidecar-absent reader MUST recover a
  unique newer valid RunHistory so an older generic projection cannot authorize
  a rerun. A timestamp-less generic `lastRun` with no matching history remains
  readable, but the first canonical safety write MUST reject it as unorderable.
  Once the canonical sidecar exists, executing a protected mutation with a Spec
  binary that predates this authority is an unsupported downgrade; a current
  reader MAY reconcile only observable generic YAML/RunHistory footprints and
  cannot recover an older execution that persisted no evidence.
- **FR-055**: A present canonical run-authority file that is malformed,
  unsupported, identity-mismatched, non-regular, or redirected by its file or
  any project-relative ancestor MUST fail closed; readers MUST NOT fall back to
  the generic use-case projection. Reads and writes of use-case, run-authority,
  and WorkflowRun authority MUST reject POSIX symlinks and Windows
  junction/reparse points present at validation across every traversed component
  and MUST NOT mutate that redirect target outside the project.
- **FR-056**: The protected `spec` CI context MUST depend on the full Ubuntu
  suite, the existing Windows installer journey, and a native `windows-latest`
  safety job. That native job MUST execute the Windows named-mutex and durable
  write-through authority suites, including native durable RunHistory
  create-without-replacement coverage, plus authority-path
  symlink/junction/reparse safety, the portable workspace-layout and
  RunHistory-filename suites, and the native prepared-request handle chain. The
  same portable-name and collision corpus MUST also run on POSIX; the protected
  context MUST fail unless all three jobs succeed.
- **FR-057**: Every use-case alias, generated workspace ID, public Core run ID,
  RunHistory ID, and WorkflowRun ID used as a filename component MUST be one
  bounded single component accepted by the full portable-name grammar: aliases
  are lowercase `[a-z0-9][a-z0-9._-]{0,79}`, generated lowercase IDs are at most
  200 characters in that alphabet, and run/WorkflowRun IDs are
  `[A-Za-z0-9][A-Za-z0-9._-]{0,199}`. It MUST reject control characters,
  trailing dot/space, and the Windows device
  basenames `CON`, `PRN`, `AUX`, `NUL`, `COM1`-`COM9`, and `LPT1`-`LPT9`
  case-insensitively, including before an extension. RunHistory and WorkflowRun
  reads, selection, and writes MUST scan their sibling namespace and fail closed
  on names that differ only by case or when collision verification is
  unavailable; a mutable projection MUST NOT break that ambiguity.
- **FR-058**: Canonical, legacy, and RunHistory risk-authority fields MUST use
  their declared boolean, text, and `commitStep.reached` types and MUST reject
  empty, whitespace-padded, or ambiguous safety status/rerun tokens and
  contradictory combinations within or across contributing mappings, including
  `commitStep.reached: true` or committed evidence paired with
  `postCommit: false`, true post-commit/side-effect claims paired with safe
  status, and `postCommit: true` paired with `sideEffectMayExist: false`, before
  any write. Evaluation of an already-decoded in-memory value MUST remain
  conservative: explicit `postCommit: true`, `sideEffectMayExist: true`, or a
  strongly committed status outranks a contradictory safe claim. A public
  `sideEffectMayExist: true` from either `execution` or `data.sideEffects` MUST
  be preserved through `postCommitInterpretation`, RunHistory, and canonical
  `lastRun`, and MUST select real-run `commit`/`afterCommit` even when the
  authored side-effect class is `none`.

### Quality and Operability Requirements

- **NFR-001**: The change MUST add no runtime dependency.
- **NFR-002**: Existing workspace, readiness, WorkflowRun, use-case, run-history,
  and confirmation schema identifiers MUST remain readable.
- **NFR-003**: Existing public CLI commands and arguments MUST remain available;
  the explicit persistence semantics of `init --core-cmd` are the only intended
  behavior change to the feature 026 runtime-mode contract.
- **NFR-004**: Every behavior group MUST follow red/green TDD: the product-shaped
  regression must fail for the diagnosed reason before production code changes
  and pass afterward.
- **NFR-005**: The complete local suite, pinned cross-repository Docker checks,
  browser product-truth smoke, and the localized-home regression MUST pass
  before merge.
- **NFR-006**: Secret canaries, including nested-container, nested-list,
  compound secret-container, scheme-less/network-path/relative-query and
  prose-embedded/repeatedly-encoded credential URI references, provider and
  bracketed query aliases, verified Bearer/Basic, base64/base64url,
  high-entropy, cyclic/over-limit input, and invalid public-container shape
  cases, MUST occur zero
  times in command output, normalized outcomes, and all `.verifysignal/`
  artifacts.
- **NFR-007**: Windows compatibility checks MUST remain mandatory in CI, with
  native execution of Windows-only run-safety primitives rather than mocked
  POSIX coverage or the installer journey alone.
- **NFR-008**: On the representative local fixtures, list/readiness projection
  MUST complete in less than 50 ms and missing-runtime blocker classification
  MUST complete in less than one second.
- **NFR-009**: Run admission, exact-attempt ownership, logical timestamping, and
  crash durability MUST use standard-library/platform primitives only and add no
  runtime service or dependency.
- **NFR-010**: Authority-path guarantees cover persisted redirects and
  cooperating VerifySignal processes. Adversarial same-user replacement of a
  filesystem component in the interval between validation and ordinary
  authority I/O is outside the local-worktree threat model; prepared-request
  creation/cleanup remains handle-anchored and resistant to pathname replacement.

## Edge Cases

- Initialization is repeated on an existing field-absent workspace.
- A user supplies `--core-cmd` for an explicit setup while environmental local
  candidates point somewhere else.
- A legacy readiness snapshot says `ready` but has no protected-operation fields.
- Core exits nonzero with valid JSON on stdout and diagnostics on stderr.
- Core returns an error during run without execution metadata; the attempt is
  non-run state but must conservatively gate the next write rerun.
- Core attaches a false/pre-execution/false tuple to a non-entitlement error, or
  a contradictory tuple to an entitlement error; neither can prove no commit.
- A custom entitlement endpoint has a matching receipt/key cache while the
  default endpoint has different keys; the selected source runtime receives
  only the custom endpoint's public keys.
- A process fails after Core returns or during `record_run`; the write-ahead
  marker remains conservative and no partial result is mistaken for a run.
- A marker-clear failure follows successful `record_run`; equal `startedAt` and
  strictly later `completedAt` keep the durable real run authoritative.
- Two processes request the same project/alias, or one process re-enters it;
  only the lease holder can proceed, and an abandoned lease is recoverable after
  process termination.
- A stale invocation tries to refine or clear a marker replaced by another
  attempt; exact-attempt comparison preserves the replacement.
- The system clock moves backward behind a prior run or attempt; logical
  nanosecond ordering still makes the new attempt strictly newer.
- A contract-invalid envelope omits trustworthy execution metadata; it cannot
  replace conservative write-ahead `sideEffectMayExist: true` with null/false.
- A stale generic `<alias>.yaml` write races after canonical marker creation,
  real-run persistence, or marker clear; canonical overlay and null tombstones
  preserve demonstrably newer safety state. A strictly newer or equal-time
  divergent generic projection instead fails closed rather than being hidden.
- A canonical run-authority document is malformed or redirected through the
  authority file, `use-cases`, or another project ancestor; loading fails closed
  instead of trusting the stale generic projection or touching the redirect.
- A canonical `lastRun` contains an unexpected top-level field or a recursively
  secret-looking value; load and workspace validation reject it before the
  value can reach list, preflight, output, or logs.
- A secret-looking scalar is nested inside a secret-named container or list, or
  compound alias such as `apiToken`, or appears as credentials in a non-HTTP or
  scheme-less URI reference, an embedded reference in multiline prose,
  Bearer/Basic text, or an exempt public-looking path field; validation rejects
  it before the first write without treating all prose as one URI.
- A legacy workspace has no sidecar, an older generic `lastRun`, and one unique
  newer valid RunHistory; preflight recovers the history. A timestamp-less
  generic run with no matching history remains readable but blocks the first
  canonical write. Running an older pre-sidecar binary after authority creation
  is not a supported downgrade path.
- Core returns an entitlement finding both top-level and in a legacy findings
  list; the top-level code wins.
- Core returns a valid error schema whose operation field disagrees with the
  operation invoked.
- Core returns `verifysignal.run/v1` with a real failed browser outcome and no
  evidence directory; it remains a real run but reports incomplete evidence.
- A prepared artifact existed before invocation and has the same path as a
  transient prepared artifact.
- Current side-effect class is `none`, but the prior real run contains explicit
  historical write evidence.
- Current side-effect class is `none`, but public runtime evidence explicitly
  says `sideEffectMayExist: true`; runtime evidence controls the safety branch.
- An active confirmation exists for an earlier source run after a supersede
  review changes the effective classification.
- Two stage persistence attempts target the same WorkflowRun; the second must
  load and transition the latest stored state rather than reset it.
- Authoring-only validation passes while the authoritative stage is `validate`;
  readiness and workflow state must not advance to `run`.
- Protected validation is repeated from `run` or `repair` after stale or
  repaired artifacts; later-stage state must be reset before the new result is
  trusted.
- A protected command is requested from the wrong managed stage, or the
  referenced WorkflowRun has an unknown schema; neither case may resolve Core or
  trust mutable projections.
- A stale use-case reference points to an older confirmed WorkflowRun while a
  unique newer active WorkflowRun is unconfirmed; one authority resolution must
  control both stage and target gates.
- A newer alias-matching WorkflowRun is structurally corrupt while the stale
  reference names an older valid run; corruption fails closed instead of
  authorizing the older run. A corrupt different-alias candidate is irrelevant.
- Two valid alias-matching WorkflowRuns have the same newest nanosecond
  timestamp while one is referenced; the tie is still ambiguous. A completed
  workflow with a pending `run` state, a non-completed workflow carrying
  `completedAt`, or a current stage with an invalid predecessor is rejected;
  repair and post-repair revalidation retain only their exercised exceptions.
- A use-case or WorkflowRun file is regular but one of its ancestors is a POSIX
  symlink or Windows junction/reparse point; both reads and writes fail closed.
- A Windows-reserved device basename is used before an extension, or two
  RunHistory/WorkflowRun siblings differ only by case; validation fails on both
  POSIX and Windows before selecting or replacing either authority.
- RunHistory A is recorded, B becomes current, and a later result reuses A; the
  create-only write fails while A's bytes and B's canonical `lastRun` remain
  unchanged.
- Persisted risk evidence uses a non-boolean flag or contradicts a committed
  status; persistence rejects it before mutation, while an unvalidated
  in-memory strongly committed value is never classified safe.
- Runtime success reports `sideEffectMayExist: true` under either `execution`
  or `data.sideEffects` for an authored class-`none` use case; the true value is
  retained in every real-run authority and controls `afterCommit`.
- A process stops after writing WorkflowRun but before one or both projections;
  the next mutating workflow transition heals the projections from the
  authoritative run.
- A legacy use case has a later executable artifact but a gap in earlier
  canonical stage documents; the furthest durable evidence controls backfill,
  while a referenced path with no actual file does not count.

## Success Criteria

- **SC-001**: In the fresh-workspace candidate matrix, 100% of local Core
  candidates are ignored unless the user explicitly selects development mode.
- **SC-002**: A compatible source Core with valid allowed trust handoff completes
  the protected authoring check, while stable contexts continue to reject
  disallowed handoff material.
- **SC-003**: 100% of supported public Core entitlement codes and malformed-schema
  fixtures produce deterministic normalized blocker codes.
- **SC-004**: Across every preflight and Core-error fixture, zero synthetic run
  IDs, history entries, gate results, evidence directories, or repair sessions
  are created.
- **SC-005**: Direct run and workflow check return the same proceed/block decision
  for every prerequisite and rerun-policy matrix row.
- **SC-006**: `afterNoCommit`, `afterCommit`, and `afterUnknown` are each selected
  by at least one independent regression scenario, with zero false
  `unknown-write-risk` results when runtime side-effect evidence is explicitly
  false.
- **SC-007**: After every tested stage transition, WorkflowRun, use-case reference,
  and rendered state agree on current stage and status in 100% of assertions.
- **SC-008**: Secret canary values occur zero times in all outputs and persisted
  artifacts generated by the recovery tests.
- **SC-009**: The complete Spec suite, pinned cross-repository regression, browser
  smoke, and localized-home journey finish green before either recovery PR is
  considered merge-ready.
- **SC-010**: The representative performance regressions enforce less than 50 ms
  for list/readiness projection and less than one second for missing-runtime
  blocker classification.
- **SC-011**: In same-process and cross-process concurrency tests, 100% of second
  same-alias admissions return `runtime.run-in-progress`, execute Core zero
  times, and persist zero run-attempt artifacts; the lease is reacquirable after
  normal release or holder termination.
- **SC-012**: Every stale refine/clear fixture preserves the foreign marker, and
  every backward-clock fixture produces attempt/completion/workflow timestamps
  that remain strictly ordered at nanosecond precision.
- **SC-013**: Every malformed or contract-invalid run fixture retains
  conservative `sideEffectMayExist: true` and produces zero synthetic runs,
  including for class-`none` use cases.
- **SC-014**: The full WorkflowRun corruption matrix fails closed for every
  alias-matching invalid authority and permits zero runtime/Core calls, while a
  corrupt different-alias candidate leaves the valid matching authority usable.
- **SC-015**: Durability tests observe file flush before atomic replacement and
  platform-appropriate durable replacement metadata for marker, lastRun, and
  clear writes, plus native create-without-replacement behavior for immutable
  RunHistory identities.
- **SC-016**: In stale-writer and crash-point fixtures, 100% of absent,
  identical, or strictly older YAML/RunHistory projections derive
  `lastCoreAttempt`/`lastRun` from canonical authority, null tombstones resurrect
  zero demonstrably stale attempts, and every
  newer/equal-divergent/unorderable projection fails closed without a merge.
- **SC-017**: Every malformed, schema/alias-mismatched, non-regular, direct-link,
  ancestral-link, unallowlisted-field, and secret-looking authority fixture
  fails closed with zero external-target writes and zero Core calls.
- **SC-018**: WorkflowRun completion/current-stage/run-state/predecessor
  coherence and equal-newest-timestamp fixtures reject 100% of inconsistent or
  ambiguous authorities, including when a mutable projection references one
  member of the tie.
- **SC-019**: The stable protected `spec` CI context is green only when Ubuntu
  tests, native Windows mutex/write-through/authority-path tests, and the
  Windows installer journey all succeed.
- **SC-020**: The shared portable-name corpus rejects 100% of control,
  trailing-dot/space, Windows-device, and case-fold-collision fixtures on POSIX
  and native Windows, while preserving every valid mixed-case Core run ID and
  creating zero ambiguous RunHistory or WorkflowRun writes.
- **SC-021**: Every A,B,A RunHistory identity-reuse fixture fails before any
  authority/projection byte changes, every malformed or contradictory persisted
  risk fixture—including whitespace/ambiguity and cross-mapping commit
  contradictions—fails before write, every compound-container/prose-embedded
  URI canary is rejected, and explicit runtime true evidence from both supported
  public locations survives canonical persistence and selects `afterCommit`.

## Assumptions

- The companion Core change adds trustworthy pre-execution metadata to current
  `verifysignal.error/v1` entitlement failures without changing that schema ID,
  and makes the guard's runtime-operation classification immutable.
- Older compatible Core versions can return public errors without execution
  metadata and must remain safely consumable.
- Managed Core distribution, receipt issuance, and cached verification material
  are already correct; VerifySignal backend production code is not part of this
  feature.
- Existing supersede reviews are the durable audit record; active confirmation
  artifacts are gates, not an immutable event log.
- Cross-repository acceptance pins Core, Spec, and backend paths explicitly so
  sibling auto-discovery cannot produce a false pass.
- Concurrent Spec runners for one project share the same host/OS lock domain;
  cross-host distributed admission is outside this local CLI feature.

## Out of Scope

- Backend production-code or entitlement-issuance changes.
- Manual version edits; release classification remains automated from the PR
  title.
- General discover-result persistence, task-status completion, or understanding
  summary fidelity described as P2 in the diagnosis.
- New runtime-identity UI or broad recovery-guidance redesign beyond truthful
  normalized blocker and next-action output.
- Core receipt format, browser adapter, run-request format, skill format, or CLI
  argument removals.
- A networked/distributed lock service for runners on different hosts.
