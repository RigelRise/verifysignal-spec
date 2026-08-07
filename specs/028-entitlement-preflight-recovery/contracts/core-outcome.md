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

The companion Core's entitlement dispatcher uses a deeply immutable
runtime-operation classification. Exported policy access, including nested
operation lists, cannot be mutated to move `run` into compatibility discovery
or otherwise bypass its receipt guard. This is a composed security invariant;
Spec still observes it only through the public CLI behavior.

An absent schema, wrong schema version, non-mapping `data`, malformed envelope,
or success schema belonging to another operation normalizes to
`core.contract-invalid`. A valid run success also requires one unambiguous,
non-empty, portable public run identity. Status alone never proves the response
kind.

### Public run identity

- Current Core publishes the run identity at `data.summary.runId`.
- `data.runId` remains accepted as a legacy compatibility location.
- If both locations are present, both values MUST satisfy the full portable
  single-component grammar and be equal.
- If either present value is empty, absolute, nested, traversal-shaped, hidden,
  overlong, contains controls or a trailing dot/space, or uses a Windows device
  basename (`CON`, `PRN`, `AUX`, `NUL`, `COM1`-`COM9`, or `LPT1`-`LPT9`)
  case-insensitively before an extension, the whole response is contract-invalid.
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

This known-not-started projection is valid only because the code is an
advertised entitlement error and the execution unit is exactly
`started: false`, `phase: pre-execution`, and
`sideEffectMayExist: false`. The same tuple on a non-entitlement error, or an
entitlement error with any contradictory/incomplete field, normalizes all four
execution projection fields to unknown.

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

## Write-ahead run-attempt persistence and refinement

After resolving prepared-request ownership and immediately before invoking Core,
persist this conservative `UseCaseRecord.lastCoreAttempt`:

```yaml
lastCoreAttempt:
  attemptedAt: "2026-08-05T00:00:00.123456789Z"
  operation: run
  schema: null
  status: unknown
  errorCode: null
  executionState: unknown
  sideEffectMayExist: true
```

If this write fails, Core is not invoked. Cleanup remains limited to the exact
invocation-owned prepared request. Once written, the marker survives adapter,
normalization, post-response interpretation, and `record_run` failures.

When Core returns a public error or invalid public response, refine the same
attempt timestamp from the normalized public outcome:

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

- Keep `attemptedAt` unchanged from the write-ahead marker.
- `executionState: not-started` only for an advertised entitlement error whose
  complete execution tuple is exactly false/pre-execution/false.
- Every other error case records `executionState: unknown` with normalized
  execution fields null, including a syntactically complete tuple on a
  non-entitlement error or a contradictory entitlement tuple.
- A `contract-invalid` response cannot supply trustworthy public execution
  metadata. Keep `executionState: unknown` and the write-ahead
  `sideEffectMayExist: true` regardless of malformed/null/false response fields.
- An adapter or normalizer exception keeps execution unknown and
  `sideEffectMayExist: true`, and may refine status/error code to the safe
  contract-invalid classification.
- A valid `verifysignal.run/v1` uses `attemptedAt` as RunHistory `startedAt`,
  creates a nanosecond `completedAt` strictly later than that start even when
  the wall clock does not advance, and clears the marker only after
  authoritative `record_run` succeeds.
- For that valid success, public `sideEffectMayExist: true` from either
  `execution.sideEffectMayExist` or `data.sideEffects.sideEffectMayExist` is
  preserved in `postCommitInterpretation`, RunHistory, and canonical `lastRun`;
  it is real-run commit evidence even when the authored class is `none`.
- If marker clearing fails after `record_run`, the durable real run has the same
  start timestamp and remains authoritative; the marker is not strictly newer.
- If `record_run` raises after making `lastRun` durable, the same equal-start
  ordering applies while the marker remains for conservative recovery.
- Only a marker whose `operation` is `run` participates in rerun classification.

The marker is not RunHistory, does not contain a run ID, and does not update
`lastRun`. Its canonical storage is
`.verifysignal/use-cases/<alias>.run-authority.json`, schema
`verifysignal-spec-run-authority/v1`; the same field in `<alias>.yaml` is a
compatibility projection.

The RunHistory filename derived from the public run identity is checked against
the entire sibling namespace before read or write. A differently cased sibling,
or inability to verify the namespace, fails closed before any authority or
projection mutation; Spec never lowercases or otherwise rewrites Core identity.
The resulting `(alias, runId)` identity is immutable and is written with a
native durable create-without-replacement primitive. Existing identity or A,B,A
reuse fails before changing canonical/YAML authority, preserving the original
history bytes and the later current `lastRun`.

The timestamp is generated locally with nanosecond precision before invocation
and is strictly later than every parseable prior last-run start/completion and
prior attempt timestamp, including under wall-clock rollback. Confirmation scope
uses a digest over every allowlisted marker field, not an additional persisted
ID. A changed attempt therefore cannot reuse a current approval merely because
it occurred in the same wall-clock second.

Marker creation compares the exact prior marker timestamp or absence observed by
the invocation. Refinement and clear compare the invocation's exact
`attemptedAt`. A comparison mismatch fails without modifying the foreign marker.

Marker create/refine/clear and lastRun update are crash-durable replacement
writes. RunHistory flushes the file and uses native durable
create-without-replacement. Each durably orders the directory entry (`fsync` on
the parent directory for POSIX, including a newly created entry when applicable;
write-through replacement/create for Windows). Before Core, the canonical marker
precedes its YAML projection. A valid result orders RunHistory → canonical
authority with `lastRun` plus the still-owned marker → YAML projection →
canonical null-marker tombstone → YAML projection. This is recoverable
ordering, not a multi-file transaction.

The canonical file has the exact top-level keys `schemaVersion`,
`useCaseAlias`, `lastCoreAttempt`, and `lastRun`. On load it overlays both run
fields only after reconciling base YAML and RunHistory evidence. An
absent/identical projection is compatible, and canonical state overrides
projection evidence proven older, including a demonstrably stale marker after a
null tombstone. Newer temporal evidence, a conflicting identity at the same
timestamp, or divergence without a reconcilable order fails closed; the loader
does not timestamp-merge files. `lastRun` accepts only the exact canonical
projection allowlist produced by `record_run` and is recursively secret-scanned.
Risk-bearing mappings require exact boolean/text/`commitStep.reached` types,
canonical unambiguous status tokens without boundary whitespace, and coherent
claims across mappings. Reached/strongly committed/explicit true evidence cannot
be paired with false or safe claims; invalid persisted authority fails closed,
while already-decoded strong evidence remains conservative.
Legacy absence retains the generic fields until the first new safety write; a
present malformed, identity-mismatched, non-regular, unallowlisted,
secret-bearing, or redirected canonical file fails closed without fallback.
A sidecar-absent reader first recovers a unique newer valid RunHistory before
preflight. A timestamp-less generic `lastRun` with no matching history remains
readable but blocks the first canonical safety write as unorderable. After the
sidecar exists, protected execution through a pre-authority Spec binary is an
unsupported downgrade; a current reader can reconcile only observable older
YAML/RunHistory footprints, not an execution that persisted no evidence.

## Run persistence eligibility

| Normalized kind | Eligible | Permitted persistence |
|---|---:|---|
| Valid `run` success schema/version with mapping data and portable run ID, any public run status | Yes | Write-ahead marker remains through interpretation; persist real run history, coverage, evidence/report references, first-run and repair projections; then clear marker |
| Public Core error returned by `run` | No | Refine write-ahead `lastCoreAttempt`, persist managed WorkflowRun `run`-stage blocker/projections and derived active confirmation; prior readiness is unchanged |
| Contract-invalid envelope returned by `run` | No | Refine write-ahead marker to unknown execution with `errorCode: null` while retaining `sideEffectMayExist: true`, plus the managed run-stage blocker/projections |
| Core invocation/normalization exception before a classifiable public outcome | No | Retain/refine write-ahead marker with unknown execution and conservative side-effect risk, plus the managed run-stage blocker/projections |
| Failure interpreting a valid response or persisting RunHistory | No | Retain the conservative write-ahead marker; do not clear or synthesize partial run state |
| Valid or blocked non-run operation response | No | Operation-specific validation/readiness/workflow state only; no `lastCoreAttempt` |

## Secret-safety allowlist

Normalized output and `lastCoreAttempt` may persist only:

- operation, schema, status, public error code, mapped blocker code;
- attempted timestamp;
- public execution state, advertised phase, and side-effect boolean, or the
  conservative local `true` used only for write-ahead/contract-invalid risk.

They must not persist raw response, stdout/stderr, command path, prepared request
path, report/evidence path, receipt, signature, verification key, access token,
environment variable value, credential, URL containing secrets, or user data.

The shared scanner recurses through mappings, secret-named mapping/list
containers (including compound aliases such as `apiToken`) and nested lists via
an iterative traversal that fails closed on cycles or defensive depth/size
limits while preserving secret-field context at scalar leaves. Before
generic public-metadata field exemptions, it rejects userinfo or secret
query/fragment parameters in URI schemes and URI references, including
scheme-less, network-path, relative-query, and references embedded in prose,
plus Bearer/Basic credentials and opaque high-entropy values. Multiline or other
whitespace-containing prose is not treated as one giant URI; embedded
references are scanned independently. Only exact public digest,
credential/session-reference, and documented public-container shapes are narrow
allowlists. The scan completes before every affected authority or workflow
write.

Embedded scanning includes bounded repeated percent-decoding of nested
references, credential/signature provider query aliases and bracketed/array
forms, and base64/base64url payloads. Basic candidates are verified as encoded
`user:password` material so ordinary “Basic authentication” prose remains
public. Public selector and token-policy containers are exempt only after their
documented field/value shape is validated; a secret-looking alias alone grants
no exemption.

## Failure behavior

- A public error returns a structured blocked command result with the normalized
  code and execution classification.
- `core.contract-invalid` directs the user to compatible Core/Spec recovery.
- Invalid canonical run authority, newer/conflicting/unorderable YAML or
  RunHistory evidence, or a direct/ancestral POSIX symlink or Windows
  junction/reparse point on an authority path blocks before Core and never
  falls back, merges competing state, or mutates the redirect target.
- Neither case emits fabricated gate coverage or repair guidance that assumes a
  Core report exists.
