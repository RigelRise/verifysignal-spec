# Contract: Run Preflight, Rerun, and Confirmation

## Shared preflight interface

`build_run_preflight(project_metadata, use_case, readiness, workflow_state,
supersede_reviews)` is pure. Both `workflow check run` and direct `run` call the
same function and project its decision without reimplementing policy.

```json
{
  "status": "blocked",
  "canProceed": false,
  "blockers": [
    {
      "code": "runtime.protected-readiness-required",
      "severity": "blocker",
      "message": "Protected runtime validation has not passed.",
      "recoveryCommand": "verifysignal validate example --runtime-readiness --json"
    }
  ],
  "requiresConfirmation": false,
  "confirmation": null,
  "rerunDecision": {
    "decision": "allowed",
    "outcomeClass": "none",
    "policyBranch": "none"
  },
  "nextAction": "verifysignal validate example --runtime-readiness --json"
}
```

No new top-level CLI schema identifier is required; this decision is embedded in
the existing workflow-check and run JSON envelopes.

## Concurrency admission gate

Before direct run evaluates stage or durable preflight state, it acquires one
non-blocking lease for the canonical resolved project plus alias. It holds that
lease until run persistence and terminal workflow handling finish. Workflow
check probes the same lease and immediately releases it when free; because a
probe cannot reserve future execution, direct run acquisition is always final.

An occupied lease returns:

```json
{
  "code": "runtime.run-in-progress",
  "severity": "blocker",
  "category": "run-concurrency"
}
```

Failure to establish trustworthy platform locking instead returns
`runtime.run-lock-unavailable` with the same severity/category. Both blockers
mean zero Core resolution/invocation and zero prepared-request,
`lastCoreAttempt`, RunHistory, or lastRun creation.

Lease implementations:

- POSIX: held exclusive non-blocking `flock` on a private no-follow regular file
  in a per-user runtime namespace outside the project, keyed only by the
  opened project directory's `st_dev`/`st_ino` plus `alias.casefold()` digest,
  plus an in-process registry to reject same-process re-entry.
  `.verifysignal/.run-locks/<alias>` is observability scaffolding only;
- Windows: global named mutex keyed by a SHA-256 digest of the
  normalized/case-normalized resolved absolute project path plus
  `alias.casefold()`.

The OS releases either lease when the holder process terminates. Runtime files,
project-local directories, and mutex names are coordination scaffolding, not
persistent proof of ownership.

## Evaluation order

Preflight evaluates all available metadata and returns deterministic blockers in
this priority order:

1. current workflow target confirmation;
2. required run request, main skill, supporting artifacts, and current
   fingerprints;
3. `UseCaseRecord.status == ready`;
4. current protected-operation readiness snapshot;
5. side-effect policy completeness and authorization requirements;
6. authoritative rerun decision and active confirmation.

For a managed workflow, the protected-command caller resolves active
WorkflowRun authority once before building this metadata. Its stage decision and
the target-confirmation input above must come from that same WorkflowRun
instance; the caller must not re-read target authority through a stale use-case
reference.

The function performs no runtime resolution, Core/version call, environment or
dotenv read, generated-input resolution, prepared-request write, confirmation
write, or workspace mutation. After the pure result returns, callers may invoke
the single confirmation reconciliation function.

After concurrency admission, direct run stops on the same first durable blocking
decision as workflow check. If `canProceed` is false, Core is invoked zero times.

## Rerun classification table

The evaluator compares a real `lastRun` with a strictly newer
`lastCoreAttempt`, when present. Equal or unparseable attempt timestamps do not
override a timestamped real run. Only `lastCoreAttempt.operation == run`
participates.

| Latest relevant evidence | Side-effect class | Outcome class | Policy branch |
|---|---|---|---|
| No real run and no run attempt | any | `none` | none; `allowed` |
| Newer run attempt has `sideEffectMayExist == true` (even if execution says not started) | any, including `none`/authenticated-read | `unknown-write` | `afterUnknown` |
| `lastCoreAttempt.executionState == not-started` and `sideEffectMayExist == false` | any | `no-commit` | `afterNoCommit` |
| Real run explicitly says `postCommit: false` and `sideEffectMayExist: false` | any | `no-commit` | `afterNoCommit` |
| Real run confirms/infers commit or side effect may exist | write/external notification, or historical explicit write evidence | `commit` | `afterCommit` |
| Newer run attempt has `executionState == unknown` | write/external notification | `unknown-write` | `afterUnknown` |
| Real write run has genuinely indeterminate commit/side-effect result | write/external notification | `unknown-write` | `afterUnknown` |
| Canonical `unknown` status plus explicit false booleans | any | `no-commit` | `afterNoCommit` |
| Unknown attempt | none/authenticated-read with no historical write evidence | `no-commit` | `afterNoCommit` |

Historical explicit write evidence cannot be erased by changing the current
declared class to `none`. Legacy truth in `postCommit`, `sideEffectMayExist`, or
a committed-status interpretation remains write evidence even when the old run
does not contain `sideEffectPolicy` or `sideEffects` snapshots.

Explicit runtime `sideEffectMayExist: true` is authoritative write-risk
evidence. On a real run it selects `commit`/`afterCommit`; on a non-run attempt
it selects `unknown-write`/`afterUnknown`. Authored `none` or authenticated-read
metadata can suppress only absent/unknown risk with no historical write
evidence, never an explicit runtime true boolean. The true boolean also outranks
a contradictory `executionState: not-started` projection; that inconsistent
attempt remains `unknown-write`, never `no-commit`.
For a valid real result, true from either public success location
`execution.sideEffectMayExist` or `data.sideEffects.sideEffectMayExist` is
preserved through `postCommitInterpretation`, RunHistory, and canonical
`lastRun`, then selects `commit`/`afterCommit` even for authored class `none`.

Persisted risk authority is not truthiness-coerced. Declared booleans and
`commitStep.reached` must be actual booleans; text fields must be non-empty; and
safety status/rerun tokens must be canonical, unambiguous, and free of boundary
whitespace. Coherence applies across all risk-bearing mappings in the run:
`commitStep.reached: true` or strongly committed status cannot coexist with
`postCommit: false`, and explicit true risk cannot coexist with a safe claim.
Both normalized `sideEffectStatus` and public `sideEffects.status` contribute
restrictive status evidence and accept only the same canonical status
vocabulary; an unknown or boundary-whitespace token invalidates persisted
authority instead of being ignored.
Malformed/contradictory authority fails before write or preflight. If an
in-memory value bypasses that boundary, true/reached/strongly committed evidence
still wins conservatively.

A persisted `violated` outcome remains `commit`/`afterCommit` evidence and
blocks a blind rerun under the unchanged policy. The existing reconciliation
path permits one new attempt only for an observation-mode violation with no
independent reached/post-commit/committed-status evidence, no later run attempt,
and an exact semantic owner policy change. Missing prior policy, an unchanged
policy, a notes-only edit, confirmed commit evidence, or a later run attempt
does not qualify. The prior classification remains in history; the next real
run replaces it as the latest evidence and must be clean before a strict pass.

The returned `rerunDecision` always includes `decision`, `outcomeClass`,
`policyBranch`, `reason`, `refreshRuntimeInputs`, and `nextAction`; it includes
`sourceRunId` and confirmation fields only when applicable.

## Active confirmation reconciliation

After the pure decision:

| Current decision | Stored active gate | Reconciliation |
|---|---|---|
| No confirmation required | any | Delete active confirmation artifact if present |
| Confirmation required | absent | Create exact current gate |
| Confirmation required | same ID/scope/source and still valid | Preserve approval/record according to existing approval contract |
| Confirmation required | different ID, scope, source, risk, or reason | Replace with exact current gate |

This is the only writer of active run-risk confirmation state. `list`, workflow
check, and direct run all derive presentation from the same decision. Supersede
reviews remain separate and are never removed by reconciliation.

An explicit safe `lastCoreAttempt` replaces an unknown attempt, selects
`afterNoCommit`, and therefore removes a stale unknown-write-risk gate.

## Invocation and prepared-request ownership

While holding the per-alias lease, and only after preflight is ready, direct run
may:

1. resolve Core;
2. load approved environment inputs;
3. resolve generated inputs;
4. prepare a run request;
5. persist conservative write-ahead `lastCoreAttempt` intent;
6. invoke Core.

Preparation must return the exact prepared-request path,
`createdByThisInvocation: boolean`, the created file identity, and a held
cleanup anchor. On POSIX, creation is exclusive and relative to a held no-follow
directory descriptor; cleanup verifies the same device/inode and unlinks
relative to that descriptor. On Windows, every non-reparse ancestor is held
without delete sharing, the file is created with `CREATE_NEW` without write or
delete sharing, and cleanup marks the exact retained file handle for deletion.
In both cases, replacing or renaming a pathname cannot redirect cleanup.
Platforms without either safe primitive set refuse prepared creation and block
before Core. Cleanup never deletes:

- a file that existed before the invocation;
- a user-authored canonical run request;
- a sibling file, parent directory, glob, evidence directory, or report;
- a path outside `.verifysignal/`.

The write-ahead marker uses a canonical nanosecond UTC attempt timestamp
strictly later than all parseable prior last-run start/completion and attempt
evidence, null schema/error code, status/execution `unknown`, and
`sideEffectMayExist: true`. Failure to persist it prevents step 6 and triggers
only the ownership-safe cleanup above.

Initial marker creation compares the exact previous marker timestamp or absence
observed by this invocation. Every refinement and clear compares this
invocation's `attemptedAt`. An ownership mismatch fails without overwriting or
clearing the foreign marker. These exact-attempt checks remain mandatory even
though the lease is the primary single-writer boundary.

## Canonical run-safety authority

New safety writes use the exact JSON sibling
`.verifysignal/use-cases/<alias>.run-authority.json` with schema
`verifysignal-spec-run-authority/v1` and exact keys `schemaVersion`,
`useCaseAlias`, `lastCoreAttempt`, and `lastRun`. The canonical values overlay
the same fields in `<alias>.yaml` only after reconciliation with base YAML and
RunHistory. An absent/identical projection is compatible; canonical state
overrides evidence proven older. Explicit nulls are tombstones against
demonstrably stale non-null projection values, not absent optional values.
Canonical `lastRun` is limited to the exact projection allowlist emitted by
`record_run`, with recursive secret rejection across mappings, secret-named
and compound secret containers such as `apiToken`, and nested lists. URI and
URI-reference credentials—including scheme-less, network-path, relative-query,
and prose-embedded references—Bearer/Basic values, and opaque high-entropy
scalars are rejected before generic public-field exemptions and before any
affected write. Whitespace-containing/multiline prose is not parsed as one URI;
embedded references are scanned independently.

Without this file, legacy YAML fields remain readable. A unique newer valid
RunHistory is recovered before preflight; a timestamp-less generic `lastRun`
without matching history remains readable but blocks the first canonical safety
write as unorderable. Once the file exists, malformed JSON/schema/identity/field
shape, invalid attempt/run identity or timestamps, unallowlisted or
secret-looking `lastRun` data, non-regular type, or direct or ancestral
link/reparse redirection fails closed. Base YAML or RunHistory with newer
temporal evidence, conflicting identity at an equal timestamp, or divergence
without a reconcilable order also fails closed. Readers never downgrade to the
generic projection, timestamp-merge competing documents, or follow a redirect
outside the project.

Public run IDs, RunHistory names, aliases, and generated IDs use the shared
portable single-component grammar: controls, trailing dot/space, and Windows
device basenames are invalid case-insensitively, including before an extension.
RunHistory reads and writes scan all siblings and reject names that differ only
by case or an unavailable scan before selecting or mutating authority.
Each `(alias, runId)` is immutable: RunHistory uses a native durable
create-without-replacement operation, so an existing identity, losing concurrent
create, or A,B,A reuse fails before canonical/YAML projection mutation and
preserves the existing bytes/current `lastRun`.

Ordinary use-case, run-authority, RunHistory, and WorkflowRun path guarantees
cover direct/ancestral redirects present at validation and cooperating Spec
processes. Adversarial same-user component replacement between validation and
ordinary authority I/O is outside the local-worktree threat model. The prepared
request contract above remains handle-anchored against pathname replacement and
does not inherit that exception.

Executing protected runs with a pre-authority Spec binary after this sidecar has
been created is an unsupported downgrade. Reconciliation covers observable
generic/RunHistory writes from older binaries; no newer reader can recover an
older process that executed Core and crashed before persisting any evidence.

## Persistence matrix after Core invocation

| Core outcome | RunHistory / lastRun | Evidence / coverage / repair | `lastCoreAttempt` | Workflow stage |
|---|---|---|---|---|
| Valid `verifysignal.run/v1`, passed | Persist real run with `startedAt == lastCoreAttempt.attemptedAt` and strictly later `completedAt` | Persist public result projections | Retain through `record_run`; clear only afterward | Complete workflow |
| Valid `verifysignal.run/v1`, failed | Persist real run with the same timestamp ordering | Persist diagnostic public projections | Retain through `record_run`; clear only afterward | Advance to repair |
| `verifysignal.error/v1`, explicitly not started | Unchanged | Unchanged | Refine write-ahead marker to `not-started` without changing `attemptedAt` | Keep `run` current and blocked; do not mark executed/failed |
| `verifysignal.error/v1`, execution unknown | Unchanged | Unchanged | Refine write-ahead marker to `unknown` without changing `attemptedAt` | Keep `run` current and blocked; do not mark executed/failed |
| Malformed envelope returned by `run` | Unchanged | Unchanged | Retain/refine unknown marker with `errorCode: null` and `sideEffectMayExist: true`; expose `core.contract-invalid` only as the blocker | Keep `run` current and blocked |
| Core invocation/normalization exception | Unchanged | Unchanged | Retain/refine unknown marker with conservative side-effect risk | Keep `run` current and blocked |
| Interpretation or `record_run` failure after a valid response | Do not synthesize success; any real `lastRun` already made durable remains authoritative | Do not clear prior state to hide the failure | Retain marker; any equal-start durable real run outranks it, including when only clearing fails | Apply terminal transition only after the real run is authoritative |

Prior run history, evidence, lastRun, repair sessions, and supersede reviews are
never deleted or rewritten by a Core error.

Marker create/refine, lastRun update, and marker clear each use file flush plus
crash-durable atomic replacement. RunHistory uses file flush plus a native
durable create-without-replacement primitive. Before Core, write the
canonical marker before the generic projection. For a valid result, write
RunHistory, then canonical authority containing `lastRun` and the still-owned
marker, then the generic projection. Clear only afterward by writing the
canonical null tombstone before the generic projection. POSIX additionally
`fsync`s replacement metadata (and a newly created directory entry when
applicable); Windows uses write-through replacement for mutable authority and a
write-through move without replacement for RunHistory. This ordering supports
conservative recovery but is not a multi-file transaction.

## Compatibility and secret safety

- Existing CLI flags, including `--confirm-risk`, remain available.
- Existing rerun policies parse unchanged; `afterUnknown` becomes effective.
- Legacy error envelopes remain safe and conservative.
- Existing marker schemas remain unchanged; exact-attempt CAS and logical
  nanosecond ordering are writer guarantees, not new persisted fields.
- The additive run-authority v1 sibling owns `lastCoreAttempt`/`lastRun` after
  creation; generic YAML remains readable for legacy absence and writable only
  as a compatibility projection. Canonical state overrides only proven-stale
  evidence; newer/equal-divergent/unorderable YAML or RunHistory fails closed.
  There is no timestamp merge.
- Protected execution by a pre-authority Spec binary after sidecar creation is
  an unsupported downgrade. Current reconciliation covers only observable
  generic YAML/RunHistory writes, not an older execution that persisted nothing.
- `.run-locks/` and per-user runtime files are internal coordination state; no
  stale path or PID file is trusted as lease ownership.
- Preflight and attempt output names only declared input names, never values.
- Secret canary scans cover command JSON and the complete `.verifysignal/` tree,
  including nested/compound secret containers and lists, credential-bearing URI
  references without schemes or embedded in prose, Bearer/Basic, and
  high-entropy values presented under otherwise exempt public field names.
