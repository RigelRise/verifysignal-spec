# Data Model: State-Aware Automatic Authoring Loop

## Probe Capability

- `name`: exact operation name `probe`.
- `schema`: exact output schema `verifysignal.probe/v1`.
- `schemaVersion`: integer `1`.
- `status`: Core-provided stability status.
- `supported`: derived boolean.

The object is derived from public version metadata and is not persisted.

## Probe Invocation

- `runRequest`: canonical project-local run-request path.
- `skills`: ordered list of canonical project-local skill paths.
- `headed`: optional boolean.
- `slowMoMs`: optional integer.
- `entitlementReceipt`: optional protected receipt path.

Credential and session values are absent. Their references remain inside the
run request.

## Session Reference

- `source`: `environment` or `local-config`.
- `key`: name whose value Core resolves to a storage-state file path.

The key name is safe metadata. The resolved path and file content never enter
Spec state.

## Stateful Grounding Outcome

- `status`: public probe status.
- `boundaryReached`: true only when Core reports the commit boundary reached.
- `boundaryExecuted`: must be false.
- `fullFlowExecuted`: must be false.
- `targetChecks`: safe public diagnostics.
- `deferred`: step/assertion identifiers.
- `blocker`: optional public code and recovery.

## Automatic Loop Decision

- `path`: `probe`, `legacy-read-only`, `upgrade-required`, or `stop-for-input`.
- `reason`: stable human-readable rationale.
- `mayPersistRepair`: whether an observed correction may be persisted through
  workflow persistence.
- `requiresRunConfirmation`: true only after a successful write-flow probe.
- `mayInvokeRun`: false until explicit confirmation.

Invariant: capability detection and probe outcome cannot themselves authorize a
mutating run. A deliberate invocation of the isolated dogfood is the
authorization for its single ephemeral loopback write; it is not reusable for
another target.
