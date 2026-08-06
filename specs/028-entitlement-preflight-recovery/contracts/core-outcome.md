# Contract: Protected Core Outcome Normalization

## Boundary

Every protected Core response is normalized by
`normalize_core_outcome(operation, response)` before validate, run, readiness,
history, coverage, repair, confirmation, or WorkflowRun code reads it.

The normalizer uses only public CLI JSON. It does not read Core source, package
internals, reports, evidence directories, process duration, or private ordering.

## Accepted schemas

| Invoked operation | Success schema | Error schema |
|---|---|---|
| `authoring-check` | `verifysignal.authoring-check/v1` | `verifysignal.error/v1` |
| `run` | `verifysignal.run/v1` | `verifysignal.error/v1` |

The operation table is sourced from Spec's public required-operation contract.
If later protected operations adopt this normalizer, each must declare its exact
advertised success schema before use.

An absent schema, wrong schema version, non-mapping `data`, malformed envelope,
or success schema belonging to another operation normalizes to
`core.contract-invalid`. A valid run success also requires one unambiguous,
non-empty, path-safe public run identity. Status alone never proves the response
kind.

### Public run identity

- Current Core publishes the run identity at `data.summary.runId`.
- `data.runId` remains accepted as a legacy compatibility location.
- If both locations are present, both values MUST be path-safe and equal.
- If either present value is empty, absolute, nested, traversal-shaped, hidden,
  overlong, or otherwise path-unsafe, the whole response is contract-invalid.
- Missing identities and conflicting current/legacy identities normalize to
  `core.contract-invalid`; Spec does not guess which identity to persist.

## Error-code precedence

1. If `error.code` is a non-empty string in `verifysignal.error/v1`, use it.
2. Otherwise, scan legacy `data.findings[]` in order for the first code present in
   `CORE_ENTITLEMENT_ERROR_MAP`.
3. Preserve the code only when it is advertised for the invoked protected
   operation (including entitlement codes). Reduce any unadvertised value to
   `core.error`; do not reflect it or invent a run result.

When both forms exist, top-level `error.code` wins even if the legacy finding
differs.

## Current public error example

```json
{
  "schema": "verifysignal.error/v1",
  "schemaVersion": 1,
  "status": "error",
  "operation": "run",
  "error": {"code": "entitlement.key-unknown"},
  "execution": {
    "started": false,
    "phase": "pre-execution",
    "sideEffectMayExist": false
  }
}
```

Normalized projection:

```json
{
  "operation": "run",
  "kind": "core-error",
  "schema": "verifysignal.error/v1",
  "status": "error",
  "errorCode": "entitlement.key-unknown",
  "blockerCode": "entitlement.unverifiable",
  "executionKnown": true,
  "executionStarted": false,
  "executionPhase": "pre-execution",
  "sideEffectMayExist": false,
  "eligibleForRunPersistence": false
}
```

## Older public error example

```json
{
  "schema": "verifysignal.error/v1",
  "schemaVersion": 1,
  "status": "error",
  "operation": "run",
  "error": {"code": "entitlement.key-unknown"}
}
```

This is a valid Core error but has:

```json
{
  "executionKnown": false,
  "executionStarted": null,
  "executionPhase": null,
  "sideEffectMayExist": null,
  "eligibleForRunPersistence": false
}
```

It is not a browser run. Because a legacy run error cannot prove that execution
did not start, Spec records a redacted `lastCoreAttempt` with
`executionState: unknown`. For write/external-notification use cases, the next
rerun preflight consumes `afterUnknown`.

## Run-error attempt persistence

When an invoked `run` returns a public Core error or an invalid public response,
update `UseCaseRecord.lastCoreAttempt`:

```yaml
lastCoreAttempt:
  attemptedAt: "2026-08-05T00:00:00.123456789Z"
  operation: run
  schema: verifysignal.error/v1
  status: error
  errorCode: entitlement.key-unknown
  executionState: not-started
  sideEffectMayExist: false
```

Derivation rules:

- `executionState: not-started` only when `started` is exactly false and
  `sideEffectMayExist` is exactly false.
- Every other error case records `executionState: unknown`; preserve a public
  boolean `sideEffectMayExist` if present, otherwise null/omitted.
- A later error replaces the marker.
- A later valid `verifysignal.run/v1` clears it after run persistence succeeds.
- Only a marker whose `operation` is `run` participates in rerun classification.

The marker is not RunHistory, does not contain a run ID, and does not update
`lastRun`.

The timestamp is generated locally with nanosecond precision. Confirmation
scope uses a digest over every allowlisted marker field, not an additional
persisted ID. A changed attempt therefore cannot reuse a current approval merely
because it occurred in the same wall-clock second.

## Run persistence eligibility

| Normalized kind | Eligible | Permitted persistence |
|---|---:|---|
| Valid `run` success schema/version with mapping data and path-safe run ID, any public run status | Yes | Real run history, coverage, evidence/report references, first-run and repair projections |
| Public Core error returned by `run` | No | `lastCoreAttempt`, managed WorkflowRun `run`-stage blocker/projections, and derived active confirmation; prior readiness is unchanged |
| Contract-invalid envelope returned by `run` | No | `lastCoreAttempt` with unknown execution and `errorCode: null`, plus the managed run-stage blocker/projections |
| Core invocation exception before a classifiable public outcome | No | `lastCoreAttempt` with unknown execution and `errorCode: core.contract-invalid`, plus the managed run-stage blocker/projections |
| Valid or blocked non-run operation response | No | Operation-specific validation/readiness/workflow state only; no `lastCoreAttempt` |

## Secret-safety allowlist

Normalized output and `lastCoreAttempt` may persist only:

- operation, schema, status, public error code, mapped blocker code;
- attempted timestamp;
- public execution state, advertised phase, and side-effect boolean.

They must not persist raw response, stdout/stderr, command path, prepared request
path, report/evidence path, receipt, signature, verification key, access token,
environment variable value, credential, URL containing secrets, or user data.

## Failure behavior

- A public error returns a structured blocked command result with the normalized
  code and execution classification.
- `core.contract-invalid` directs the user to compatible Core/Spec recovery.
- Neither case emits fabricated gate coverage or repair guidance that assumes a
  Core report exists.
