# Data Model: Entitlement Preflight Recovery

## WorkspaceRuntimePolicy

Represents the workspace's durable Core resolution intent.

| Field | Type | Required on new writes | Rules |
|---|---|---:|---|
| `coreResolutionMode` | `legacy-auto \| managed-only \| development-override` | Yes for new workspaces | Existing field-absent workspace reads as `legacy-auto`; a newly created workspace writes `managed-only` |
| `coreCommand` | string | Only for development override | Persist only after an explicit Core command is validated successfully |
| `managedRuntime` | existing object | No | Preserved; remains the verified managed runtime metadata |

### Transitions

```text
new workspace --------------------------> managed-only
legacy field absent --load only---------> legacy-auto
any mode --explicit successful setup----> development-override
any mode --core reset/update------------> managed-only
failed explicit setup ------------------> unchanged
```

## ReadinessSnapshot v1 additions

The existing `verifysignal-spec-readiness-snapshot/v1` schema remains unchanged
by identifier and gains optional fields on read, required fields on new writes.

| Field | Type | Legacy default | Validation |
|---|---|---|---|
| `commandCompatibilityStatus` | `not-checked \| passed \| blocked` | `not-checked` | Passed only after public version/operation compatibility passes |
| `trustMaterialStatus` | `not-checked \| ready \| blocked` | `not-checked` | Describes receipt/key inputs, not Core trust arming |
| `protectedOperationStatus` | `not-checked \| passed \| blocked` | `not-checked` | Passed only after `authoring-check --runtime-readiness` returns a schema-valid pass |
| `readinessScope` | `command-and-trust-inputs \| protected-operation` | `command-and-trust-inputs` | Protected scope requires a checked protected operation |

The existing aggregate `status` remains readable. On new writes:

- `ready` requires `readinessScope: protected-operation`, command compatibility
  and protected operation `passed`, and trust material `ready`;
- `blocked` is used when any attempted required component is blocked;
- `not-checked`, `stale`, and `needs-validate` retain existing invalidation
  semantics and cannot satisfy run preflight.

Validation still invokes the entitlement-protected `authoring-check` when
`--runtime-readiness` is absent, but that authoring-only result MUST keep
`protectedOperationStatus: not-checked` and
`readinessScope: command-and-trust-inputs`. It can report its authoring result,
but it cannot make the aggregate snapshot eligible for run preflight or advance
an authoritative WorkflowRun from `validate` to `run`.

## NormalizedCoreOutcome

An in-memory, redacted interpretation of one public Core response. It is not a
copy of the raw response and is not a new Core wire schema.

| Field | Type | Rules |
|---|---|---|
| `operation` | string | Operation requested by Spec; never trusted solely from response data |
| `kind` | `success \| core-error \| contract-invalid` | Determined by schema identity and operation contract |
| `schema` | string or null | Advertised public schema observed in the response; unrecognized values redact to null |
| `status` | `passed \| failed \| blocked \| error` | Normalized public status |
| `errorCode` | string or null | Top-level advertised public code first, legacy finding fallback second; unadvertised values reduce to `core.error` |
| `blockerCode` | string or null | Spec-safe mapped code such as `entitlement.unverifiable` or `core.contract-invalid` |
| `executionKnown` | boolean | True only when the public execution object is structurally valid |
| `executionStarted` | boolean or null | Null when unknown |
| `executionPhase` | string or null | Preserved only for an advertised public phase, including `pre-execution` |
| `sideEffectMayExist` | boolean or null | Null when unknown |
| `eligibleForRunPersistence` | boolean | True only for valid `verifysignal.run/v1` |

### Validation rules

- Expected success schema is selected by invoked operation.
- The companion Core's runtime-operation classification is deeply immutable for
  the process lifetime. An exported policy consumer cannot mutate the nested
  operation sets to reclassify `run` or bypass entitlement dispatch.
- Schema version must match the advertised operation version and `data` must be
  a mapping. A run additionally requires one unambiguous, non-empty path-safe
  identity. Current Core publishes it at `data.summary.runId`; legacy
  `data.runId` remains accepted. If both are present they must be equal, and an
  invalid value in either location fails the response closed. "Path-safe" here
  means the shared portable single-component grammar, including Windows device,
  control-character, and trailing-dot/space refusal.
- `verifysignal.error/v1` is accepted as an error for a protected operation.
- A malformed response, operation/schema mismatch, or unexpected schema yields
  `kind: contract-invalid`, `blockerCode: core.contract-invalid`.
- No raw receipt, key, signature, token, environment value, or credential may be
  included.

## RunPreflightDecision

A pure decision shared by workflow check and direct run.

| Field | Type | Rules |
|---|---|---|
| `status` | `ready \| blocked` | `ready` only when every required gate passes |
| `canProceed` | boolean | Equivalent to `status == ready` |
| `blockers` | list of structured blockers | Stable codes, messages, and recovery commands; no secret values |
| `requiresConfirmation` | boolean | Derived from the authoritative rerun decision/current risk only |
| `confirmation` | active confirmation or null | Present only for the current blocking/approval gate |
| `rerunDecision` | EffectiveRerunDecision | Always included when a use case is loadable |
| `nextAction` | string | Same projection for workflow check and direct run |

Inputs are already-loaded workspace metadata only. The evaluator performs no
filesystem writes, environment reads, runtime resolution, or Core invocation.

## RunInvocationLease

An ephemeral, non-persisted admission authority for one canonical resolved
project and portable use-case alias.

| Concept | Rules |
|---|---|
| identity | POSIX digest/registry key uses the opened project directory's `st_dev`/`st_ino` plus `alias.casefold()`; Windows uses the normalized/case-normalized resolved absolute path plus `alias.casefold()`; no raw project path is persisted in workspace state |
| exclusivity | At most one holder for the same `(project, alias)`; different aliases are independent |
| POSIX backend | Exclusive non-blocking `flock` on a private no-follow regular file in a per-user runtime namespace outside the project, named only by the device/inode/alias digest, plus an in-process ownership registry |
| Windows backend | Global named mutex whose name contains the normalized-path/alias identity digest |
| lifetime | Direct run holds the lease through preflight, Core handling, persistence, and terminal workflow updates; OS ownership releases it on process termination |
| occupied | `runtime.run-in-progress`; no Core call or run-state mutation |
| unavailable | `runtime.run-lock-unavailable`; fail closed when trustworthy primitives cannot be established |

`workflow check run` probes this admission state and immediately releases a free
lease. The direct run acquisition is the final admission decision, closing the
race between a read-only probe and execution.

The project-local `.verifysignal/.run-locks/<alias>` directory is retained only
as compatibility/observability scaffolding. It is not the lock identity;
renaming or replacing it cannot admit a second holder. Runtime lock files are
also non-authoritative scaffolding: only the live OS lock proves ownership.

## RunSafetyAuthority v1

The canonical execution/rerun safety record is the JSON sibling
`.verifysignal/use-cases/<alias>.run-authority.json`. Its schema identifier is
`verifysignal-spec-run-authority/v1`.

| Field | Type | Rules |
|---|---|---|
| `schemaVersion` | exact string | Must equal `verifysignal-spec-run-authority/v1` |
| `useCaseAlias` | portable alias string | Must equal the alias encoded by the sibling filename and satisfy the shared component grammar |
| `lastCoreAttempt` | LastCoreAttempt or null | Canonical current attempt; null is an explicit clear tombstone |
| `lastRun` | allowlisted real-run projection or null | Canonical latest real run; null is an explicit never-run tombstone |

The top-level key set is exact. A present file with malformed JSON, an unknown
schema, wrong alias, extra/missing fields, invalid attempt/run identity or
timestamps, a non-regular type, or a redirected file/ancestor is invalid
authority. Loading fails closed and does not fall back to the generic use-case
YAML.

The canonical `lastRun` top-level allowlist is derived from `record_run` and
permits only:

- identity/outcome/time: `runId`, `status`, `startedAt`, `completedAt`,
  `coreStatus`, `coverageStatus`;
- execution profile/skill: `profile`, `profileSettings`, `selectedMainSkill`,
  `executedSkill`, `skillSelectionStatus`;
- coverage/diagnostics: `gateCoverage`, `missingRequiredGates`,
  `partialCoverage`, `runtimeContradictions`, `repairRecommendations`;
- safety/runtime projections: `sideEffectPolicy`, `sideEffects`,
  `runtimeOutputs`, `resolvedRuntimeInputs`, `postCommitInterpretation`,
  `rerunDecision`, `sideEffectLifecycle`;
- artifact references: `reportPath`, `evidenceDir`.

Unknown top-level fields are invalid; identity, type, and timestamp checks still
apply to allowlisted values. The entire nested value is recursively scanned for
secret-looking keys and values before it can become authority. Recursion covers
mappings, secret-named mapping/list containers, and scalar leaves inside nested
sequences while preserving secret-field context through those containers. The
iterative traversal fails closed on cycles or defensive depth/size limits.
URI and URI-reference userinfo and secret query/fragment parameters, including
scheme-less credentials, network paths, relative queries, and references
embedded in prose or bounded repeatedly encoded nested values, plus verified
Bearer/Basic credentials and opaque base64/base64url or other high-entropy
values, are rejected before generic public-metadata field exemptions. Secret
query-key matching includes compound `*_token` names and provider
credential/signature segments even when bracketed or array-shaped, without
matching public near-neighbors. A Windows drive-relative path remains public
only until a whitespace or punctuation boundary introduces a separately
scannable reference. A
whitespace-containing or multiline scalar is not parsed as one giant URI;
embedded references are scanned independently and the other detectors still
apply. Compound secret container names such as `apiToken` preserve secret-field
context through nested mappings/lists. A selector alias is exempt only inside a
documented selector collection with exactly one primary selector signal and
typed modifiers, and `tokenPolicy` is exempt only with its documented scalar
types and enum values. Malformed public-container candidates fail closed and
their descendants retain secret context. High-entropy branch names, public
identifiers, structured error codes, schema versions, and paths are exempt only
when both their field context and exact public shape agree. This includes
single-component numeric feature branches and Core's request-plus-epoch run ID
format. Structured public codes are recognized in the exact code fields, while
an exact `credential` leaf remains secret-bearing even when nested in runtime
output metadata. An opaque value in ordinary prose receives no slug or path
exemption. Only exact public
digest/reference shapes have narrow allowlists.

### Risk-authority coherence

Every risk-bearing mapping in `lastRun` is validated before RunHistory or
canonical/projection writes. Declared boolean fields and `commitStep.reached`
accept booleans only; declared text fields accept non-empty strings; and
safety-relevant status/rerun tokens must be unambiguous canonical values without
leading/trailing whitespace. Coherence is checked both within a mapping and
across the contributing mappings: for example, `commitStep.reached: true` or a
strongly committed status cannot coexist with `postCommit: false`, and a true
post-commit/side-effect fact cannot coexist with a safe status. Restrictive
status evidence includes both normalized `sideEffectStatus` and the public
`sideEffects.status` alias; both aliases accept only the same canonical status
vocabulary.

Malformed or contradictory persisted authority is invalid rather than coerced.
If an already-decoded in-memory value bypasses persistence validation, the
evaluator still treats `postCommit: true`, `sideEffectMayExist: true`,
`commitStep.reached: true`, and strongly committed status as the stronger
evidence. Public success `sideEffectMayExist: true` from either `execution` or
`data.sideEffects` is preserved in `postCommitInterpretation`, RunHistory, and
canonical `lastRun`; for a real run it selects `commit`/`afterCommit`, including
when the authored class is `none`.

`UseCaseRecord.lastCoreAttempt` and `UseCaseRecord.lastRun` remain readable and
writable projections for compatibility. When the canonical sibling exists,
`load_use_case()` first reconciles each slot and the newest evidence across both
slots with the generic record and RunHistory. An absent or identical projection
is compatible; canonical values override only projection evidence proven
strictly older. Explicit nulls override a demonstrably stale non-null marker, so
an old writer cannot erase a newer run/attempt or resurrect a marker after a
canonical clear. Newer temporal evidence, conflicting identity at an equal
timestamp, or divergence without a reconcilable order is invalid authority and
fails closed. When the sibling is absent, legacy generic values remain readable.
A unique newer valid RunHistory is recovered for preflight so an older
projection cannot authorize execution. A timestamp-less generic `lastRun`
without matching RunHistory remains readable but is unorderable and blocks the
first canonical safety write. This is lazy recovery at the safety boundary, not
a timestamp merge of competing canonical documents.

After this sibling exists, protected execution through a Spec binary that
predates `RunSafetyAuthority` is an unsupported downgrade. A current reader can
fail closed on or reconcile observable generic YAML/RunHistory footprints, but
cannot recover an older execution that invoked Core and crashed before writing
any evidence.

## LastCoreAttempt

An additive optional run-safety value canonically stored in
`RunSafetyAuthority` and projected into `UseCaseRecord`. It records conservative
run intent without asserting that a browser run exists. Direct run writes it
after resolving prepared-request ownership and immediately before invoking Core.
The marker is then refined from an error outcome or retained until a valid real
run is durably recorded. Protected authoring-check errors belong to
validation/readiness state and do not create this rerun-attempt marker.

| Field | Type | Rules |
|---|---|---|
| `attemptedAt` | UTC timestamp | Canonical nanosecond UTC identity persisted before Core, strictly after parseable prior run/attempt evidence and reused for every refinement of that attempt |
| `operation` | string | Public operation name; current writers emit `run` |
| `schema` | string or null | Public response schema only |
| `status` | string | `unknown` in the write-ahead form; normalized Core status after a classifiable error |
| `errorCode` | string or null | Public code; no raw message required |
| `executionState` | `not-started \| unknown` | `not-started` only for an advertised entitlement error with exact `started: false`, `phase: pre-execution`, and `sideEffectMayExist: false`; all other error cases are `unknown`, and this label never overrides a contradictory explicit true boolean |
| `sideEffectMayExist` | boolean or null | Conservative `true` in the write-ahead form and after contract-invalid output; exact public value or null after a valid public error |

The write-ahead form is exactly `operation: run`, `schema: null`,
`status: unknown`, `errorCode: null`, `executionState: unknown`, and
`sideEffectMayExist: true`. Refinement changes only the public outcome fields;
it retains `attemptedAt`. A contract-invalid response is not trustworthy enough
to weaken this initial boolean, so its refined marker remains unknown with
`sideEffectMayExist: true`.

For rerun classification, explicit `sideEffectMayExist: true` is the stronger
fact even if malformed or legacy persisted state also says
`executionState: not-started`; that contradiction remains unknown write risk and
selects `afterUnknown` for the non-run attempt.

The marker MUST contain no command path, prepared-request path, report/evidence
path, receipt, key, signature, environment value, credential, raw stderr, or raw
Core response. If the initial marker write fails, Core is not invoked and only
the exact invocation-owned prepared request is eligible for cleanup. Adapter,
normalization, interpretation, and `record_run` failures leave conservative
intent durable. A public error refines the same marker timestamp; safe
not-started evidence replaces the initial unknown classification and allows
active unknown risk to be reconciled away.

Every marker mutation uses exact-attempt compare-and-swap semantics. Initial
creation requires the prior marker timestamp (or absence) observed by the
invocation. Refinement and clear require the invocation's own `attemptedAt`.
Ownership mismatch raises an error and preserves the marker currently on disk.

A valid `verifysignal.run/v1` reuses `attemptedAt` as the real run's `startedAt`.
Its `completedAt` is generated at nanosecond precision and forced to be strictly
later than `startedAt`, including when the wall clock is equal or moves
backward. The marker is cleared only after `record_run` succeeds. If clearing
fails, the remaining marker has the same start timestamp as the durable real run
and therefore cannot override it as a newer attempt. A new invocation chooses
`attemptedAt` strictly after every parseable prior `lastRun.startedAt`,
`lastRun.completedAt`, and `lastCoreAttempt.attemptedAt`, even if the wall clock
is equal or earlier.

### Crash-durable authority sequence

Safety-authority writes use file flush plus `fsync`, same-directory atomic
replacement, and durable replacement metadata (`fsync` of the containing
directory, including a newly created directory entry, on POSIX or write-through
replacement on Windows). The ordered phases are:

1. before Core, write canonical authority with the new/refined marker, then its
   generic use-case projection;
2. for a valid result, write RunHistory;
3. write canonical authority with the completed `lastRun` and still-owned
   marker, then its generic use-case projection;
4. after real-run authority is durable, write canonical authority with a null
   marker tombstone, then its generic use-case projection.

RunHistory phase 2 is an immutable create, not a replacement. Its identity is
the portable `(alias, runId)` pair. POSIX uses a native link/create no-replace
operation and Windows uses a write-through move without a replace flag. If the
identity already exists or another writer wins the create, persistence fails
before phases 3–4. Thus an A,B,A reuse preserves A byte-for-byte and leaves B as
the canonical `lastRun`.

The sequence is deliberately not a multi-file transaction. A crash before the
real-run authority leaves conservative attempt intent; a crash after it leaves
an equal-start real run that outranks the marker; only a durably ordered
canonical tombstone removes it. Derived registry/output and workflow projections
cannot displace this authority.

Attempt-scoped confirmation identity is a one-way digest of every allowlisted
marker field. It is not stored on the marker. This prevents a same-second later
attempt with different public evidence from reusing an approval while keeping
the persistence allowlist unchanged. Legacy timestamp-scoped reviews are
accepted only when their recorded prior classification exactly matches the
current marker and the review is strictly later.

## PreviousRunClassification

An in-memory classification derived from a prior real `verifysignal.run/v1`
history entry and any later `lastCoreAttempt` for operation `run`.

| Classification | Evidence | Policy branch |
|---|---|---|
| `none` | No prior real run and no later run attempt | None; decision is `allowed` |
| `no-commit` | Not started with explicit false side-effect evidence, or explicit `postCommit: false` and `sideEffectMayExist: false` | `afterNoCommit` |
| `commit` | Confirmed/inferred commit or explicit side-effect-may-exist evidence | `afterCommit` |
| `unknown-write` | Write/external-notification execution is indeterminate, or a non-run attempt explicitly says a side effect may exist | `afterUnknown` |

Historical explicit write evidence, including legacy `postCommit` or
`sideEffectMayExist` truth and committed-status interpretation even when policy
snapshots are absent, overrides a later metadata-only change to a non-write
class. Explicit runtime `sideEffectMayExist: true` is itself write-risk evidence:
on a real run it selects `commit`/`afterCommit`, and on a newer non-run attempt it
selects `unknown-write`/`afterUnknown`, regardless of an authored class of
`none` or authenticated-read or a contradictory `not-started` execution label. A
non-write class with explicit false evidence is
`no-commit`, not `unknown-write`. If `lastCoreAttempt.attemptedAt` is strictly
newer than the last real run, `not-started` selects `no-commit`; unknown evidence
without an explicit true boolean selects `unknown-write` only for
write/external-notification classes. Equal, missing, or invalid attempt
timestamps do not override a timestamped real run. Non-run operations do not
override the previous run classification.

`violated` is conservative `commit` evidence. An exact semantic owner policy
change may authorize one new reconciliation run only when the prior violation
used observation mode, no independent reached/post-commit/committed-status
evidence exists, and no later run attempt exists. Absent prior policy, an
unchanged policy, notes-only edits, confirmed commit evidence, and later run
attempts do not authorize it. A newer real run then becomes the latest evidence.

## EffectiveRerunDecision

| Field | Type | Rules |
|---|---|---|
| `decision` | `allowed \| allowed-with-new-inputs \| requires-confirmation \| blocked` | Combined once from Core/public evidence and the selected Spec policy branch |
| `outcomeClass` | `none \| no-commit \| commit \| unknown-write` | Makes branch selection auditable |
| `policyBranch` | `none \| afterNoCommit \| afterCommit \| afterUnknown` | Exactly one branch |
| `sourceRunId` | string or null | Only a real prior run ID |
| `confirmationId` | string or null | Present only for requires-confirmation |
| `reason` | string | Explains evidence and selected branch without secret values |
| `refreshRuntimeInputs` | list of names | Existing declared names only; no values |
| `nextAction` | string | Guided command or proceed instruction |

## ActiveConfirmationGate

The existing confirmation artifact is treated as the current derived gate.

| Field | Rule |
|---|---|
| `id`, `scope`, `sourceRunId` | Must match the current EffectiveRerunDecision |
| `riskClass`, `reason`, `recommendedAction` | Recomputed from current evidence |
| `blocksExecution` | True only while the current decision requires it |
| lifecycle | Create/replace when required; delete when no current gate exists |

`SupersedeReview` remains separate, append-only audit evidence and is never
deleted by active-gate reconciliation.

## WorkflowRun authority and projections

`WorkflowRun` remains `verifysignal-spec-workflow-run/v1` and is the authority.
`UseCaseWorkflowReference` and `verifysignal-spec-workflow-state/v1` are derived
projections.

### Authoritative fields

- `runId`, `useCaseAlias`, `status`, `currentStage`;
- `stageStates[]` including status, document path, timestamps, blockers, and
  next command;
- `targetEnvironmentConfirmation`;
- `nextCommand`, `resumeCommand`, and completion timestamps.

### Authority validation and selection

Before decoding or selection, each referenced or alias-matching authority must
validate all of the following:

- mapping document, exact `verifysignal-spec-workflow-run/v1` schema, workflow
  identity, portable run/alias identity, and path/run-ID agreement;
- supported workflow status and current stage/integration, required valid
  nanosecond-preserving UTC workflow start/update timestamps, and valid optional
  workflow/stage completion or start timestamps when present;
- exactly one structured state for every workflow stage, with supported status,
  valid optional timestamps, and structured blocker codes;
- typed blocker optional fields and structured gate decisions with supported
  stage/decision, typed optional reason, and valid timestamp;
- exact target-confirmation fields, direct-user/explicit-command source, valid
  timestamp, and no secret-looking values;
- when status is `completed`, `currentStage: run`, a workflow `completedAt`, and
  a completed `run` state; when status is not completed, null `completedAt`;
- completed-or-skipped predecessors of the current stage, except that the
  exercised repair transition permits a failed `run` immediately before
  `repair`, and post-repair revalidation may retain completed repair history
  while `validate` and `run` are pending;
- regular authority path with no direct or ancestral POSIX symlink or Windows
  junction/reparse-point redirection.

Stage-level `startedAt` and `completedAt` remain optional for legacy
compatibility. In particular, a pending stage is not invalid merely because it
has no timestamps; the boundary validates the type/format of temporal evidence
that is actually present.

A structured candidate declaring the requested alias is security-relevant before
full decoding. If it fails validation, authority resolution fails closed rather
than skipping it and reviving an older valid run. An unreferenced corrupt
candidate declaring another alias and an unreferenced unstructured or
non-candidate file do not displace the requested alias's valid authority; an
explicitly referenced wrong-alias document is invalid. Equal newest timestamps
remain ambiguous even when a use-case projection references one tied run; the
projection cannot break an authority tie. WorkflowRun writes assign `updatedAt`
strictly after the run's prior timestamps and all parseable persisted
WorkflowRun update timestamps, preserving one-nanosecond ordering through
wall-clock rollback.

Before reading, selecting, or writing a RunHistory or WorkflowRun, the repository
scans its sibling namespace. Two `.yaml` authority names that differ only by
case are invalid even on a case-sensitive host, and inability to verify siblings
fails closed. This prevents POSIX from creating an authority set that collapses
on default case-insensitive Windows filesystems. The shared component grammar is
bounded and full-match: aliases are lowercase and at most 80 characters;
generated lowercase IDs and mixed-case run IDs are at most 200 characters; all
start alphanumeric and otherwise use only alphanumeric, dot, underscore, or
hyphen. It rejects controls, trailing dot/space, and `CON`,
`PRN`, `AUX`, `NUL`, `COM1`-`COM9`, and `LPT1`-`LPT9` case-insensitively,
including before an extension.

### Coordinated, healable transition result

One transition produces three documents from the same in-memory run:

1. WorkflowRun at `.verifysignal/workflows/runs/`;
2. use-case `workflow` reference with matching stage/status/run ID;
3. rendered state at `.verifysignal/workflows/use-cases/<alias>/state.yaml`.

Validation completes before persistence. Each individual file continues to use
the repository's atomic replacement primitive, but the three-file group is not a
transaction. WorkflowRun is written first as authority; the next mutating
transition compares its stage/run identity to both projections and rewrites
either stale or missing projection. Read-only surfaces render from WorkflowRun
without writing. No contract may claim crash-atomic multi-file persistence.

Authority path resolution applies the same no-redirect rule to the canonical
use-case YAML, its run-authority sibling, and WorkflowRun files on both read and
write. Rejecting an ancestor redirect occurs before opening or replacing the
target, so an external directory/file remains byte-for-byte unchanged.

This ordinary authority guarantee covers direct or ancestral redirects present
at validation and cooperating VerifySignal processes. Adversarial same-user
replacement of a component between validation and ordinary authority I/O is
outside the local-worktree threat model. Prepared-request creation and cleanup
are different: retained directory/file handles anchor those operations against
pathname replacement on both supported primitive sets.

### Protected transition eligibility

- Authoring-check without `--runtime-readiness` leaves the authoritative
  `validate` state pending; only runtime-readiness validation can complete or
  block that stage.
- Runtime-readiness validation can run from `validate`, `run`, or `repair`. Revalidation
  from a later stage resets later-stage state before recording the new validate
  result; a pass returns the workflow to `run`, while a blocker keeps it at
  `validate`.
- A successfully applied repair completes `repair`, resets `validate` and `run`
  to pending, and moves the workflow to `validate`. The repair does not itself
  claim revalidation or rerun success.
- A protected command outside its allowed source stage fails before runtime
  resolution with `workflow.stage-out-of-order`.
- Protected preflight resolves active WorkflowRun authority once. The same
  in-memory run supplies both the stage decision and target confirmation; a
  second lookup through `UseCase.workflow.lastWorkflowRunId` is not an allowed
  authority source.
- An on-disk referenced WorkflowRun that cannot be decoded or validated, or an
  ambiguous newest authority, fails closed with
  `workflow.authority-invalid`; mutable use-case or rendered-state projections
  are not used as fallback authority.

### Lazy legacy migration

- Trigger: next workflow persistence when the authority loader finds no active
  WorkflowRun after first attempting to recover a unique newest matching run.
  An on-disk referenced WorkflowRun that exists but cannot be decoded or
  validated, or ambiguous newest matching authorities, fail closed instead of
  migrating from projections.
- Identity: deterministic run ID from alias plus a fingerprint nonce derived
  from the durable migration evidence using existing safe-ID utilities; persist
  once and then reuse the reference.
- Evidence: inspect valid canonical authored-stage documents; `plan.yaml` and
  `tasks.yaml` only when each is a project-owned regular file with the exact
  `verifysignal-spec-workflow-artifact-plan/v1` or
  `verifysignal-spec-workflow-tasks/v1` schema and matching `useCaseAlias`;
  compatible durable workflow references; and project-relative executable references (`runRequest`,
  `mainSkill`, `skills`, and `sourceOnlySkills`) that resolve to actual regular,
  non-symlink files. Executable references are implement-stage evidence; a path
  string without an on-disk artifact is not evidence.
- Stage inference: select the furthest authored stage supported by that durable
  evidence, then backfill every earlier authored stage as completed. Do not stop
  at an earlier documentation gap when a valid later artifact proves that the
  legacy workflow had already advanced.
- Terminal authoring state: after `implement` evidence, choose `run` only when a
  current protected-operation readiness snapshot is valid; otherwise choose
  `validate`. With no authored evidence, choose `understand`.
- Target confirmation: copy an existing valid confirmation into the run.
- Idempotence: a second transition loads the newly referenced run and creates no
  second migration run.
- Non-goal: migration creates WorkflowRun as the only new authority/entity, then
  derives the use-case reference and rendered state projections from it. It does
  not synthesize a browser run or RunHistory entry, Core execution result,
  discover evidence, gate/evidence artifacts, task execution statuses, or
  repair result.
