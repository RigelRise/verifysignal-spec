# Feature Specification: Entitlement Preflight Recovery

**Feature Branch**: `028-entitlement-preflight-recovery`
**Created**: 2026-08-05
**Status**: Ready for implementation
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
- **Secret safety**: Normalized outcomes and persisted state contain codes and
  execution classification only; receipt, key, signature, credential, and
  environment values remain excluded.
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
with a protected authoring check that passes, then with a public entitlement
error, a legacy error without execution metadata, and an unknown schema. Verify
each readiness layer and recovery classification is truthful and deterministic.

**Acceptance Scenarios**:

1. Given a compatible command and available trust inputs but no protected call,
   when readiness is reported, then compatibility and trust are distinguished
   from protected-operation status and the protected status is `not-checked`.
2. Given a protected authoring check that passes, when validation completes,
   then protected-operation readiness is `passed` and run may become available.
3. Given `verifysignal.error/v1` with a top-level entitlement code and explicit
   pre-execution metadata, when Spec normalizes the response, then it reports a
   blocked, not-started outcome with the mapped blocker code.
4. Given an older public Core error without execution metadata, when it is
   normalized, then execution remains unknown, the response is never treated as
   a browser run, and a redacted non-run attempt marker preserves that uncertainty.
5. Given a response whose schema is not valid for the invoked operation, when it
   is normalized, then Spec fails closed with `core.contract-invalid`.

---

### User Story 3 - Block safely before a real run and rerun consistently (Priority: P1)

As a developer running a use case, I want direct run and workflow check to make
the same preflight decision, so blocked validation, a pre-execution Core error,
or stale risk state cannot create a fake run or an unnecessary confirmation.

**Independent Test**: Compare `workflow check run` and direct `run` over a table
of missing prerequisites, blocked validation, valid first run, no-commit prior
run, committed prior run, genuinely unknown write outcome, and stale active
confirmation. Assert Core invocation, persistence, and confirmation lifecycle
match the shared decision in every row.

**Acceptance Scenarios**:

1. Given a use case that is not ready or lacks protected-operation readiness,
   when either run entry point is used, then both return the same blocker and
   Core is not resolved or invoked.
2. Given a valid Core run-result schema, when Core reports a real passed or
   failed browser run, then run history, gate coverage, evidence references, and
   repair state may be updated from that result.
3. Given any Core error envelope, when run returns, then no new run ID, run
   history, gate coverage, evidence, last-run, repair, or write-risk state is
   synthesized; only the redacted non-run attempt marker and a confirmation
   derived from genuine unknown write risk may change.
4. Given a pre-execution outcome or explicit false post-commit and
   side-effect-may-exist values, when rerun policy is evaluated, then
   `afterNoCommit` is used.
5. Given confirmed or inferred commit evidence, when rerun policy is evaluated,
   then `afterCommit` is used.
6. Given a genuinely indeterminate outcome for a write or external-notification
   use case, when rerun policy is evaluated, then `afterUnknown` is used.
7. Given a class-`none` use case with explicit no-side-effect evidence, when a
   prior error is inspected, then no `unknown-write-risk` confirmation is
   generated.
8. Given an active confirmation whose underlying requirement no longer exists,
   when preflight is recalculated, then the active artifact is removed or
   replaced while supersede reviews remain available for audit.
9. Given a run error without execution metadata for a write use case, when the
   next preflight is evaluated, then the non-run attempt selects `afterUnknown`;
   given explicit `started: false` and `sideEffectMayExist: false`, it selects
   `afterNoCommit` and clears any stale unknown-risk gate.

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
2. Given successful validation, when state is persisted, then the current stage
   becomes `run`; given blocked validation, it remains `validate` with blockers.
3. Given a valid passed run result, when state is persisted, then the workflow
   completes; given a valid failed run result, it advances to `repair`.
4. Given a pre-execution Core error, when state is persisted, then the workflow
   keeps `run` as the current stage, marks that stage blocked with the normalized
   blocker, and does not claim the run was executed or failed.
5. Given a legacy use case with no WorkflowRun, when the next stage is persisted,
   then one WorkflowRun is created from existing documents without losing target
   confirmation or resetting completed stages.

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

#### Public Core outcomes

- **FR-012**: Spec MUST normalize each protected Core response at one shared,
  schema-aware boundary before any command interprets or persists it.
- **FR-013**: A successful protected response MUST match the exact advertised
  public schema for the operation that was invoked.
- **FR-014**: `verifysignal.error/v1.error.code` MUST be the primary public Core
  error-code source.
- **FR-015**: `data.findings[].code` MUST remain supported only as a legacy
  fallback when a top-level public error code is absent.
- **FR-016**: An unexpected or malformed schema MUST normalize to
  `core.contract-invalid` and fail closed.
- **FR-017**: When present, Core `execution.started`, `execution.phase`, and
  `execution.sideEffectMayExist` MUST be preserved in the normalized outcome.
- **FR-018**: Absence of public execution metadata MUST remain unknown; Spec MUST
  NOT infer browser execution from an error envelope and MUST preserve the
  uncertainty in a redacted non-run attempt marker.
- **FR-019**: Normalized output and persisted readiness MUST NOT contain raw
  receipts, signatures, verification keys, environment values, or credentials.

#### Run preflight and result lifecycle

- **FR-020**: `workflow check run` and direct `run` MUST use one pure preflight
  decision and expose equivalent blockers, confirmation requirements, rerun
  decisions, and recovery actions.
- **FR-021**: Run preflight MUST complete before runtime resolution, environment
  input loading, prepared-request creation, or Core invocation.
- **FR-022**: Preflight MUST evaluate target confirmation, required artifacts,
  use-case readiness, protected-operation readiness, side-effect policy, and
  rerun policy.
- **FR-023**: A blocked preflight MUST invoke Core zero times and MUST create no
  run, evidence, prepared-request, repair, or active confirmation side effects
  beyond reconciling the current confirmation gate.
- **FR-024**: Only a valid `verifysignal.run/v1` response MAY create or update
  run history, last run, gate coverage, evidence/report references, repair
  recommendations, or first-run execution state.
- **FR-025**: A Core error response during run MUST return a blocked/not-started
  or blocked/execution-unknown result with the normalized Core code and execution
  classification.
- **FR-026**: Invocation-created prepared artifacts MUST be removed after a Core
  error by deleting only the exact file created by that invocation; user-authored,
  pre-existing, or merely adjacent prepared artifacts MUST be preserved.
- **FR-027**: A Core error MUST preserve all prior run history, evidence,
  repair sessions, and last-run state unchanged. It MUST update only a redacted
  `lastCoreAttempt` marker and reconcile the active confirmation from that marker.
- **FR-028**: `lastCoreAttempt` MUST contain only attempted time, operation,
  public schema/status/error code, `not-started` or `unknown` execution state,
  and public side-effect uncertainty; it MUST contain no paths or secret values.
- **FR-029**: A later valid run result MUST clear the superseded non-run attempt;
  a later explicit not-started error MUST replace an earlier unknown attempt.

#### Rerun and confirmation authority

- **FR-030**: One rerun evaluator MUST be authoritative for workflow checks,
  direct run, list/status presentation, and confirmation generation.
- **FR-031**: With no prior real run or later run attempt, the evaluator MUST
  return `allowed`.
- **FR-032**: Explicit not-started or explicit no-commit/no-side-effect evidence
  MUST select `afterNoCommit`.
- **FR-033**: Confirmed or inferred commit evidence MUST select `afterCommit`.
- **FR-034**: A newer `lastCoreAttempt` with unknown execution for a write or
  external-notification run MUST select `afterUnknown` without becoming run
  history.
- **FR-035**: Only a genuinely indeterminate write or external-notification
  outcome MUST select `afterUnknown`.
- **FR-036**: A class-`none` or authenticated-read use case with explicit false
  side-effect evidence MUST NOT generate `unknown-write-risk`; prior evidence of
  a real write MUST remain conservatively classified.
- **FR-037**: Active confirmation persistence MUST be reconciled from the current
  authoritative decision: replace a changed gate and delete a gate that is no
  longer required, while preserving supersede reviews as historical audit data.

#### Workflow state authority

- **FR-038**: WorkflowRun MUST be the authoritative workflow-stage state for an
  active use case.
- **FR-039**: Each stage transition MUST update the WorkflowRun first and derive
  its use-case reference and rendered state from that authority. Because the
  files are not transactionally atomic as a group, the next mutating workflow
  transition MUST detect and heal an interrupted projection update from the
  WorkflowRun. Read-only surfaces MUST render from WorkflowRun without mutation.
- **FR-040**: Successful validation MUST advance to `run`; blocked validation or
  protected preflight MUST remain at `validate` with structured blockers.
- **FR-041**: A valid passed run MUST complete the workflow; a valid failed run
  MUST advance to `repair`; a Core error MUST keep the `run` stage blocked with
  normalized blockers and MUST NOT record it as executed or failed.
- **FR-042**: Stage rendering MUST preserve existing stage statuses and MUST NOT
  reconstruct an all-pending stage list when a WorkflowRun exists.
- **FR-043**: On the next workflow persistence only, a legacy use case without a
  WorkflowRun MUST receive one lazy, idempotent migration inferred from existing
  documents and references without deleting target confirmation.

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
- **NFR-006**: Secret canaries MUST occur zero times in command output,
  normalized outcomes, and all `.verifysignal/` artifacts.
- **NFR-007**: Windows compatibility checks MUST remain mandatory in CI.

## Edge Cases

- Initialization is repeated on an existing field-absent workspace.
- A user supplies `--core-cmd` for an explicit setup while environmental local
  candidates point somewhere else.
- A legacy readiness snapshot says `ready` but has no protected-operation fields.
- Core exits nonzero with valid JSON on stdout and diagnostics on stderr.
- Core returns an error during run without execution metadata; the attempt is
  non-run state but must conservatively gate the next write rerun.
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
- An active confirmation exists for an earlier source run after a supersede
  review changes the effective classification.
- Two stage persistence attempts target the same WorkflowRun; the second must
  load and transition the latest stored state rather than reset it.
- A process stops after writing WorkflowRun but before one or both projections;
  the next mutating workflow transition heals the projections from the
  authoritative run.
- A legacy use case has stage documents and target confirmation but no workflow
  reference or WorkflowRun.

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
  `unknown-write-risk` results for explicit non-write outcomes.
- **SC-007**: After every tested stage transition, WorkflowRun, use-case reference,
  and rendered state agree on current stage and status in 100% of assertions.
- **SC-008**: Secret canary values occur zero times in all outputs and persisted
  artifacts generated by the recovery tests.
- **SC-009**: The complete Spec suite, pinned cross-repository regression, browser
  smoke, and localized-home journey finish green before either recovery PR is
  considered merge-ready.

## Assumptions

- The companion Core change adds trustworthy pre-execution metadata to current
  `verifysignal.error/v1` entitlement failures without changing that schema ID.
- Older compatible Core versions can return public errors without execution
  metadata and must remain safely consumable.
- Managed Core distribution, receipt issuance, and cached verification material
  are already correct; VerifySignal backend production code is not part of this
  feature.
- Existing supersede reviews are the durable audit record; active confirmation
  artifacts are gates, not an immutable event log.
- Cross-repository acceptance pins Core, Spec, and backend paths explicitly so
  sibling auto-discovery cannot produce a false pass.

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
