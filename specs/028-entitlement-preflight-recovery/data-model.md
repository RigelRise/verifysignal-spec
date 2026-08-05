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
| `protectedOperationStatus` | `not-checked \| passed \| blocked` | `not-checked` | Passed only after a schema-valid protected authoring check passes |
| `readinessScope` | `command-and-trust-inputs \| protected-operation` | `command-and-trust-inputs` | Protected scope requires a checked protected operation |

The existing aggregate `status` remains readable. On new writes:

- `ready` requires `readinessScope: protected-operation`, command compatibility
  and protected operation `passed`, and trust material `ready`;
- `blocked` is used when any attempted required component is blocked;
- `not-checked`, `stale`, and `needs-validate` retain existing invalidation
  semantics and cannot satisfy run preflight.

## NormalizedCoreOutcome

An in-memory, redacted interpretation of one public Core response. It is not a
copy of the raw response and is not a new Core wire schema.

| Field | Type | Rules |
|---|---|---|
| `operation` | string | Operation requested by Spec; never trusted solely from response data |
| `kind` | `success \| core-error \| contract-invalid` | Determined by schema identity and operation contract |
| `schema` | string or null | Public schema observed in the response |
| `status` | `passed \| failed \| blocked \| error` | Normalized public status |
| `errorCode` | string or null | Top-level public code first, legacy finding fallback second |
| `blockerCode` | string or null | Spec-safe mapped code such as `entitlement.unverifiable` or `core.contract-invalid` |
| `executionKnown` | boolean | True only when the public execution object is structurally valid |
| `executionStarted` | boolean or null | Null when unknown |
| `executionPhase` | string or null | Preserved public phase, including `pre-execution` |
| `sideEffectMayExist` | boolean or null | Null when unknown |
| `eligibleForRunPersistence` | boolean | True only for valid `verifysignal.run/v1` |

### Validation rules

- Expected success schema is selected by invoked operation.
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

An additive optional field on `UseCaseRecord` that records the latest protected
Core error without asserting that a browser run exists.

| Field | Type | Rules |
|---|---|---|
| `attemptedAt` | UTC timestamp | Time Spec invoked the protected Core operation |
| `operation` | string | Public operation name, primarily `run` or `authoring-check` |
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

## PreviousRunClassification

An in-memory classification derived from a prior real `verifysignal.run/v1`
history entry and any later `lastCoreAttempt` for operation `run`.

| Classification | Evidence | Policy branch |
|---|---|---|
| `none` | No prior real run and no later run attempt | None; decision is `allowed` |
| `no-commit` | Not started, or explicit `postCommit: false` and `sideEffectMayExist: false` | `afterNoCommit` |
| `commit` | Confirmed/inferred commit or explicit side-effect-may-exist evidence | `afterCommit` |
| `unknown-write` | Write/external-notification execution occurred but commit/side effect cannot be determined | `afterUnknown` |

Historical explicit write evidence overrides a later metadata-only change to a
non-write class. A non-write class with explicit false evidence is `no-commit`,
not `unknown-write`. If `lastCoreAttempt.attemptedAt` is newer than the last real
run, `not-started` selects `no-commit`; `unknown` selects `unknown-write` only for
write/external-notification classes. Non-run operations do not override the
previous run classification.

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

### Lazy legacy migration

- Trigger: next workflow persistence for a use case with no loadable active
  WorkflowRun.
- Identity: deterministic run ID from alias plus migration timestamp/nonce using
  existing safe-ID utilities; persist once and then reuse reference.
- Stage inference: mark a stage completed only when its canonical durable stage
  document exists and parses; choose the first incomplete stage as current.
- Target confirmation: copy an existing valid confirmation into the run.
- Idempotence: a second transition loads the newly referenced run and creates no
  second migration run.
- Non-goal: do not synthesize discover evidence or task completion absent from
  durable documents.
