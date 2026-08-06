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
- Schema version must match the advertised operation version and `data` must be
  a mapping. A run additionally requires one unambiguous, non-empty path-safe
  identity. Current Core publishes it at `data.summary.runId`; legacy
  `data.runId` remains accepted. If both are present they must be equal, and an
  invalid value in either location fails the response closed.
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

## LastCoreAttempt

An additive optional field on `UseCaseRecord` that records the latest Core error
returned by `run` without asserting that a browser run exists. Protected
authoring-check errors belong to validation/readiness state and do not create this
rerun-attempt marker.

| Field | Type | Rules |
|---|---|---|
| `attemptedAt` | UTC timestamp | Local time Spec invoked the protected Core operation, retained at nanosecond precision |
| `operation` | string | Public operation name; current writers emit `run` |
| `schema` | string or null | Public response schema only |
| `status` | string | Normalized Core status |
| `errorCode` | string or null | Public code; no raw message required |
| `executionState` | `not-started \| unknown` | `not-started` only for explicit `started: false` plus `sideEffectMayExist: false`; all other error cases are `unknown` |
| `sideEffectMayExist` | boolean or null | Exact public value or null when absent |

The marker MUST contain no command path, prepared-request path, report/evidence
path, receipt, key, signature, environment value, credential, raw stderr, or raw
Core response. A valid later `verifysignal.run/v1` clears it. A later safe
not-started error replaces an earlier unknown marker and allows active unknown
risk to be reconciled away.

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
| `no-commit` | Not started, or explicit `postCommit: false` and `sideEffectMayExist: false` | `afterNoCommit` |
| `commit` | Confirmed/inferred commit or explicit side-effect-may-exist evidence | `afterCommit` |
| `unknown-write` | Write/external-notification execution occurred but commit/side effect cannot be determined | `afterUnknown` |

Historical explicit write evidence, including legacy `postCommit` or
`sideEffectMayExist` truth and committed-status interpretation even when policy
snapshots are absent, overrides a later metadata-only change to a non-write
class. A non-write class with explicit false evidence is `no-commit`, not
`unknown-write`. If `lastCoreAttempt.attemptedAt` is strictly newer than the last
real run, `not-started` selects `no-commit`; `unknown` selects `unknown-write`
only for write/external-notification classes. Equal, missing, or invalid attempt
timestamps do not override a timestamped real run. Non-run operations do not
override the previous run classification.

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
