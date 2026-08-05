# Research: Entitlement Preflight Recovery

## Decision 1: Distinguish creation-time defaults from legacy absence

**Decision**: Persist `managed-only` only when Spec creates a new workspace.
Interpret an absent field in an already-existing workspace as `legacy-auto`.
Successful explicit `init --core-cmd` and `core setup --core-cmd` persist
`development-override`.

**Rationale**: The incident came from treating a new workspace as legacy, but
silently changing existing field-absent workspaces would break the compatibility
promise from feature 026. Creation context is the reliable boundary.

**Alternatives considered**:

- Interpret every absent field as managed-only: rejected because it silently
  migrates legacy workspaces and can remove an intentional local development
  setup.
- Retain legacy-auto for new workspaces: rejected because it preserves the
  diagnosed Golden Path source-selection failure.
- Keep `init --core-cmd` invocation-only: rejected by the approved plan because
  the option is an explicit local-runtime choice and should be durable like
  `core setup --core-cmd`.

## Decision 2: Model readiness as three proofs plus scope

**Decision**: Add command compatibility, trust material, protected operation,
and readiness scope to readiness v1. A snapshot can truthfully prove command and
inputs without claiming a protected call passed.

**Rationale**: Version compatibility and a matching cached key ID did not prove
that the selected source Core could arm its trust context. The prior single
ready label combined materially different claims.

**Alternatives considered**:

- Replace the existing status with one new enum: rejected because it would
  break readers and still compress distinct failure domains.
- Run a protected operation during every runtime resolution: rejected because
  resolution is used in contexts that should remain compatibility-only and may
  lack a use-case request/skill.
- Bump the snapshot schema: rejected because optional additive fields have safe
  conservative defaults.

## Decision 3: Normalize public Core responses once

**Decision**: Create one operation-aware outcome normalizer. Exact operation
success schemas and `verifysignal.error/v1` are accepted; top-level
`error.code` precedes the legacy findings fallback; any other schema fails
closed as `core.contract-invalid`.

**Rationale**: The adapter correctly retained JSON from a nonzero exit, but each
caller interpreted its shape differently. A single boundary prevents error
envelopes from leaking into success-only persistence logic.

**Alternatives considered**:

- Patch only `core_entitlement_blocker_code()`: rejected because run would still
  accept an error envelope as a browser result and other schema errors would
  remain ambiguous.
- Infer response type from status alone: rejected because both public success
  and error schemas can carry `failed`, `blocked`, or `error`-like states.
- Parse Core report internals: prohibited by the public Core boundary.

## Decision 4: Treat execution metadata as authoritative and absence as unknown

**Decision**: Preserve Core's additive `execution` object when present. Do not
infer execution from process duration, exit code, stderr, missing evidence, or
private Core ordering. An older error without the object remains execution
unknown but is still ineligible for browser-run persistence.

**Rationale**: The companion Core owns the actual execution boundary. Spec can
make safe persistence decisions from schema type even when older Core cannot
prove whether side effects may exist.

**Alternatives considered**:

- Treat all entitlement codes as pre-execution: rejected because future Core
  paths may change and Spec must not duplicate private ordering.
- Treat missing metadata as started: rejected because that would recreate fake
  runs.
- Treat missing metadata as definitely not started: rejected because it makes an
  unsupported safety claim for older Core.

## Decision 5: Share a pure preflight before all runtime work

**Decision**: Build one pure run-preflight decision and call it from workflow
check and direct run before runtime resolution, environment loading, generated
inputs, prepared request creation, or Core invocation.

**Rationale**: The incident's workflow check and direct run disagreed because
they had independent prerequisite paths. A pure decision is deterministic,
unit-testable, and side-effect free.

**Alternatives considered**:

- Make direct run shell out to workflow check: rejected because it adds parsing,
  process, and recursion complexity instead of sharing policy.
- Keep two callers synchronized with duplicated checks: rejected because that is
  the diagnosed failure mode.
- Resolve Core first to improve error messages: rejected because blocked
  preflight must do zero runtime work.

## Decision 6: Persist only operation-valid results

**Decision**: Only a valid `verifysignal.run/v1` response can create run history,
coverage, evidence, last-run, first-run, or repair state. Error envelopes produce
a blocked command result, remove only the exact prepared-request file created by
that invocation, and persist a redacted non-run `lastCoreAttempt` marker.

**Rationale**: Run persistence represents an attempted browser execution, not a
generic Core subprocess call. Schema identity is the stable public discriminator.

**Alternatives considered**:

- Persist a failed run for observability: rejected because it invents browser
  coverage, side-effect state, and repair guidance. The normalized command error
  already supplies observability.
- Add error entries to normal run history: rejected because existing history
  semantics represent Core run results. A future command-attempt audit log is a
  separate feature; the single latest redacted attempt marker is sufficient for
  safety derivation.
- Delete every prepared path after an error: rejected because it could destroy
  pre-existing or user-owned artifacts.

## Decision 7: Classify rerun policy from the prior real outcome

**Decision**: Select exactly one policy branch: no prior run is allowed;
not-started or explicit false evidence uses `afterNoCommit`; commit evidence uses
`afterCommit`; genuinely indeterminate write outcomes use `afterUnknown`.
Non-write explicit false evidence never creates unknown write risk, while
historical real write evidence remains conservative. A newer unknown run attempt
from `lastCoreAttempt` selects `afterUnknown` without becoming a run.

**Rationale**: `afterUnknown` was parsed but never selected, and a separate
repository helper treated every unknown label as write risk. The decision must
combine public outcome evidence and declared policy once.

**Alternatives considered**:

- Remove `afterUnknown`: rejected because indeterminate write outcomes are real
  and the public artifact already declares the policy.
- Let class `none` override all historical evidence: rejected because changing
  metadata must not erase evidence of a prior real write.
- Keep confirmation generation separate: rejected because it caused workflow,
  list, and run disagreement.

## Decision 8: Active confirmations are derived gates, not an event log

**Decision**: Recalculate the active confirmation from the authoritative
preflight decision. Replace a changed requirement and delete a resolved one.
Retain supersede reviews separately as immutable audit records.

**Rationale**: A stale confirmation currently remains visible after risk
disappears. Separating active gate from historical review makes list/status and
execution agree without losing owner decisions.

**Alternatives considered**:

- Keep every confirmation file active forever: rejected because it creates false
  blockers.
- Delete supersede reviews with the gate: rejected because it loses audit data.
- Ignore stored confirmation in list only: rejected because persistence would
  remain contradictory and other readers could still trust it.

## Decision 9: Make WorkflowRun authoritative with lazy migration

**Decision**: Transition and write WorkflowRun first, then derive its use-case
reference and rendered projection. The three-file update is coordinated and
healable, not transactionally atomic: the next mutating transition repairs
projection drift from WorkflowRun, while read-only surfaces render from that
authority without writes. Lazily create a missing WorkflowRun only on the next
workflow write by inferring durable stage documents and preserving target confirmation.

**Rationale**: Stage persistence currently constructs all-pending rendered
state without updating the active run. WorkflowRun already has the richer stage
model and is the natural authority.

**Alternatives considered**:

- Make rendered state authoritative: rejected because it lacks gate decisions,
  target confirmation, and full run identity.
- Eagerly migrate every workspace on read: rejected because read-only commands
  should not mutate projects and incomplete legacy evidence needs conservative
  handling.
- Delete rendered state and use-case references: rejected because existing
  integrations and readers rely on those projections.

## Decision 10: Keep backend and version files outside the implementation

**Decision**: Use backend only as an explicitly pinned integration fixture. Do
not create a backend branch or edit production backend code. Do not hand-edit
Spec version files; use a `fix:` PR title for automated patch classification.

**Rationale**: The exact receipt/key pair passes the protected Core control, so
issuance is not causal. Repository automation owns version reconciliation.

**Alternatives considered**:

- Refresh or reissue the receipt: rejected because it cannot fix the same-key-ID
  selection defect and would hide the client lifecycle bugs.
- Add backend fallback behavior: rejected because it expands scope without a
  backend defect.

## Decision 11: Require product-shaped red/green evidence and pinned composition

**Decision**: Each behavior group starts with a failing production-shaped test,
then the focused green suite, full pytest, explicit-path Docker composition,
browser smoke, and the localized-home regression. Windows stays CI-required.

**Rationale**: Existing green tests used different key IDs or fake response
shapes and therefore missed the incident. Explicit pins prevent adjacent sibling
discovery from making the composition test accidentally pass.

**Alternatives considered**:

- Rely on unit tests only: rejected because the defects cross runtime selection,
  subprocess contracts, and persistence.
- Rely on the live site only: rejected because deterministic negative controls
  and secret assertions require hermetic fixtures.
