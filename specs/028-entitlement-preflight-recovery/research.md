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
inputs without claiming a protected call passed. Resolve one effective
entitlement endpoint for each protected command and use it for both receipt
selection and the source adapter's endpoint-scoped cached public-key lookup.

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
closed as `core.contract-invalid`. In the companion Core, the runtime-operation
policy consulted by entitlement dispatch is deeply immutable, including nested
operation lists, so exported policy access cannot reclassify `run` after module
initialization.

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
- Expose a mutable operation-policy object and rely on caller discipline:
  rejected because one consumer mutation could bypass the receipt guard for all
  later calls in the process.

## Decision 4: Trust only the canonical entitlement pre-execution proof

**Decision**: Preserve a complete execution object on successful outcomes. For
an error envelope, treat execution as known-not-started only when its public code
is an advertised entitlement error and its complete tuple is exactly
`started: false`, `phase: pre-execution`, and `sideEffectMayExist: false`. Any
non-entitlement, incomplete, contradictory, or unadvertised error projection is
wholly unknown. Do not infer execution from process duration, exit code, stderr,
missing evidence, or private Core ordering. Every error remains ineligible for
browser-run persistence.

**Rationale**: The companion Core owns the actual execution boundary, while the
error code identifies whether the reported phase is the entitlement guard that
is contractually pre-execution. A syntactically complete tuple attached to an
unrelated error must not manufacture a no-commit proof.

**Alternatives considered**:

- Treat every syntactically complete execution object as authoritative:
  rejected because unrelated or contradictory errors could manufacture a safe
  rerun classification.
- Treat an entitlement code without the exact tuple as pre-execution: rejected
  because the complete public proof, not the label alone, establishes safety.
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
coverage, evidence, last-run, first-run, or repair state. After resolving
prepared-request ownership, Spec first persists a conservative redacted
`lastCoreAttempt`, then invokes Core. Error envelopes refine that same marker and
produce a blocked command result while removing only the exact prepared-request
file created by that invocation. A valid response leaves the marker in place
through interpretation and `record_run`, then clears it only after the real run
is durable.

**Rationale**: Run persistence represents an attempted browser execution, not a
generic Core subprocess call. Schema identity is the stable public discriminator.
The write-ahead marker closes the interval in which Core may have run but a
process or persistence failure could otherwise leave no conservative intent.

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
- Write the marker only after Core responds: rejected because adapter,
  normalization, interpretation, or persistence failure would recreate an
  untracked execution window.
- Clear the marker before persisting RunHistory: rejected because a crash in
  between would lose both conservative intent and authoritative run state.

## Decision 7: Classify rerun policy from the prior real outcome

**Decision**: Select exactly one policy branch: no prior run is allowed;
not-started with explicit false side-effect evidence, or other explicit false
evidence, uses `afterNoCommit`; commit evidence uses
`afterCommit`; genuinely indeterminate write outcomes use `afterUnknown`.
Non-write explicit false evidence never creates unknown write risk, while
historical real write evidence remains conservative. Explicit runtime
`sideEffectMayExist: true` is itself write-risk evidence and outranks authored
class `none` or authenticated-read and any contradictory persisted
`executionState: not-started` label. A newer unknown run attempt from
`lastCoreAttempt` selects `afterUnknown` when its authored class, historical
evidence, or explicit runtime boolean establishes write risk, without becoming a
run.

A prior side-effect-policy `violated` result remains conservative
`commit`/`afterCommit` evidence. Preserve the established owner reconciliation:
an unchanged policy blocks a blind rerun, while an observation-mode violation
with no independent reached/post-commit/committed-status evidence and no later
run attempt may use one exact semantic policy change to permit a new attempt and
retain the prior result in history. Missing prior policy, notes-only edits,
confirmed commit evidence, and later run attempts do not qualify.

**Rationale**: `afterUnknown` was parsed but never selected, and a separate
repository helper treated every unknown label as write risk. The decision must
combine public outcome evidence and declared policy once.

**Alternatives considered**:

- Remove `afterUnknown`: rejected because indeterminate write outcomes are real
  and the public artifact already declares the policy.
- Let class `none` override all historical evidence: rejected because changing
  metadata must not erase evidence of a prior real write or an explicit current
  runtime warning that a side effect may exist.
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
authority without writes. Protected preflight resolves the active WorkflowRun
once and threads that exact instance through both stage eligibility and target
confirmation; it never re-reads target authority through a potentially stale
use-case projection. Lazily create a missing WorkflowRun only on the next
workflow write. Select the furthest authored stage supported by readable
canonical stage documents, a compatible durable workflow reference, or
project-relative executable references that resolve to actual regular,
non-symlink files; then backfill earlier authored stages and preserve direct
target confirmation. An unreadable on-disk referenced authority or ambiguous
newest authorities fail closed instead of migrating from mutable projections.
Migration creates no browser run, RunHistory, Core result, evidence, task
execution status, or repair result.

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
- Resolve stage and target confirmation independently: rejected because a stale
  confirmed projection could authorize a newer active WorkflowRun that has no
  direct target confirmation.

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

## Decision 12: Admit one active run per resolved project and alias

**Decision**: Direct run acquires a non-blocking, crash-released lease for the
canonical `(resolved project, alias)` before stage or preflight evaluation and
holds it through final persistence. Workflow check probes the same admission
mechanism and releases a free probe immediately. POSIX uses an exclusive
`flock` on a private no-follow regular file in a per-user runtime namespace
outside the mutable project plus an in-process key registry; the filename is
only a digest of the opened project directory's `st_dev`/`st_ino` identity and
the case-folded alias, so alternate path spellings of the same directory share
one lease. The project-local alias
directory remains non-authoritative observability scaffolding, so replacing it
cannot mint another lease. Windows uses a global named mutex whose name contains
the digest of the normalized/case-normalized resolved absolute path and
case-folded alias. Contention returns
`runtime.run-in-progress`; unavailable trustworthy primitives return
`runtime.run-lock-unavailable`. This guarantee covers cooperating Spec runners
in the same host/OS lock domain; it does not introduce distributed coordination.

**Rationale**: A single `lastCoreAttempt` field cannot safely represent two
simultaneous Core executions. OS-owned leases are released after normal exit or
process termination and avoid stale ownership files.

**Alternatives considered**:

- Persist a PID/lock file: rejected because crashes, PID reuse, and path
  replacement create stale or spoofable ownership.
- Lock the project-local alias directory: rejected because renaming it preserves
  the held inode while allowing a second pathname identity to be created.
- Rely only on POSIX `flock`: rejected because same-process re-entry and Windows
  require explicit handling.
- Let workflow check retain the lease: rejected because a read-only readiness
  probe must not reserve execution after it returns; direct run reacquires and
  remains authoritative.
- Wait indefinitely for the lease: rejected because the CLI needs a
  deterministic blocker and recovery command.

## Decision 13: Combine the lease with exact-attempt CAS and logical time

**Decision**: Marker creation compares the exact prior `attemptedAt` or absence
observed by the invocation. Refinement and clear compare the invocation's own
`attemptedAt`; a mismatch preserves the foreign marker and fails. New attempt
identity is `max(wall clock, every parseable prior run/attempt timestamp + 1ns)`.
Run completion and WorkflowRun updates use the same strictly-after rule. A
contract-invalid response retains conservative `sideEffectMayExist: true`
instead of replacing it with untrusted null/false execution data.

**Rationale**: The lease is the primary single-writer boundary, while CAS
prevents a stale or unexpectedly interleaved invocation from overwriting or
clearing another attempt. Logical ordering keeps strict newest-evidence
comparisons valid when timestamps share a second or the clock moves backward.

**Alternatives considered**:

- Trust the lease without ownership comparison: rejected because defensive
  persistence must still fail safely if ownership changes unexpectedly.
- Use wall-clock seconds or microseconds: rejected because same-tick writes can
  become equal and Python timestamp conversion can discard nanosecond identity.
- Generate a second persisted attempt ID: rejected because `attemptedAt` already
  belongs to the secret-safe allowlist and can provide exact identity when
  logically ordered.
- Copy contract-invalid execution fields into the marker: rejected because an
  invalid envelope cannot weaken the conservative pre-invocation fact.

## Decision 14: Durably order run authority writes

**Decision**: Marker create/refine/clear and lastRun update use same-directory
temporary files, file flush plus `fsync`, atomic replacement, and durable
replacement metadata. RunHistory is different: its portable `(alias, runId)`
identity is immutable and uses a native create-without-replacement primitive
(link/create plus parent `fsync` on POSIX; write-through move without replace on
Windows). Existing identity or A,B,A reuse fails before later authority or
projection writes. Before Core, canonical marker precedes its generic
projection. A real result then orders RunHistory, canonical lastRun plus
still-owned marker, generic projection, canonical marker tombstone, and the
cleared generic projection.

**Rationale**: Atomic rename prevents torn files but does not by itself prove
that content and directory metadata survive a crash. The ordered chain ensures
recovery sees either conservative intent, a durable real run, or both; it never
clears intent before the real run authority is durable.

**Alternatives considered**:

- Keep ordinary atomic replacement: rejected because a power/process failure
  can expose a durability gap even without a torn document.
- Clear the marker with an ordinary write: rejected because marker removal is
  itself part of the safety ordering.
- Claim a multi-file transaction: rejected because the files remain separately
  replaced; safety comes from ordering and conservative recovery semantics.

## Decision 15: Validate WorkflowRun before authority selection

**Decision**: A WorkflowRun must pass strict document validation before it can
be decoded or selected: schema/workflow/path identity, safe alias, workflow and
stage enums, exactly one state for every stage, comparable required workflow
timestamps and valid optional workflow/stage timestamps when present,
structured blockers and gate decisions, exact target-confirmation shape/source,
secret safety, and non-symlink authority. Stage-level timestamps remain optional
for legacy compatibility; pending stage state is not globally hardened merely
because temporal evidence is absent. Any structured on-disk candidate that
declares the requested alias but fails validation blocks with
`workflow.authority-invalid`, even if an older referenced run is valid. An
unreferenced unstructured file or unreferenced candidate declaring another alias
is not a matching authority and cannot displace the valid run; a referenced
wrong-alias document is invalid authority.

**Rationale**: Selecting only successfully decoded candidates lets a corrupt
newer authority disappear and silently revives stale confirmation/stage state.
Candidate matching must be determined before full validation, then corruption
must fail the matching alias closed.

**Alternatives considered**:

- Skip invalid candidates and choose the newest valid run: rejected because it
  can authorize stale state after corruption.
- Let permissive model defaults repair malformed authority: rejected because
  defaults turn missing or invalid security-relevant fields into plausible
  state.
- Block every corrupt file in the shared runs directory: rejected because a
  different use-case alias is not authority for the requested workflow.

## Decision 16: Add a canonical run-safety overlay with null tombstones

**Decision**: Persist the execution/rerun safety fields in
`.verifysignal/use-cases/<alias>.run-authority.json` under exact schema
`verifysignal-spec-run-authority/v1`. Its only payload fields are the matching
`useCaseAlias`, `lastCoreAttempt`, and `lastRun`. On load, these two values
overlay an absent, identical, or provably older generic `<alias>.yaml` record;
an explicit null is a tombstone, not absence, when the projected value is
demonstrably stale. Before overlay, compare each safety slot and the newest
cross-slot evidence against both base YAML and RunHistory. Newer temporal
evidence, conflicting identity at an equal timestamp, or divergence without a
reconcilable order fails closed rather than being merged or discarded. Legacy
workspaces with no authority file keep reading their generic fields. A unique
newer valid RunHistory is recovered before preflight; a timestamp-less generic
run without matching history stays readable but blocks the first canonical
safety write as unorderable. Canonical `lastRun` accepts only the exact
projection allowlist produced by `record_run` and recursively rejects
secret-looking data. Its risk-bearing mappings use exact boolean/text types,
canonical unambiguous status tokens, and within-/cross-mapping coherence; a
reached commit step or strongly committed state cannot be paired with a false
post-commit claim. Invalid persisted risk fails before write, while the
in-memory evaluator conservatively gives true/reached/strongly committed facts
precedence over safe claims. Public `sideEffectMayExist: true` from either
`execution` or `data.sideEffects` is preserved through
`postCommitInterpretation`, RunHistory, and canonical `lastRun`. After the
sidecar exists, protected execution by a Spec
binary that predates this authority is an unsupported downgrade. A current
reader can reconcile only observable generic YAML/RunHistory footprints; no
reader can reconstruct an older Core invocation that persisted no evidence.

**Rationale**: A generic use-case writer can legitimately save a stale object
while a run invocation is changing safety state. If both writers independently
own the same YAML fields, that stale write can erase a write-ahead marker,
discard a completed run, or resurrect a cleared marker. A small sibling
authority makes ownership explicit without a breaking schema migration, and
placing it in the existing `use-cases` directory avoids a first-run directory
creation gap.

The durable order is deliberately asymmetric. Before Core, canonical marker is
written before its generic projection. For a valid result, RunHistory is durable
first, then canonical authority records `lastRun` plus the still-owned marker,
then the generic projection is updated. Clear is a later exact-owner operation
that writes a canonical null tombstone before updating the generic projection.
This is recoverable ordered persistence, not a multi-file transaction or a
temporal merge algorithm.

**Alternatives considered**:

- Keep `lastCoreAttempt` and `lastRun` authoritative in the general use-case
  YAML: rejected because unrelated stale writers can overwrite them.
- Omit null fields from the canonical file: rejected because absence cannot
  distinguish a deliberate clear from an older non-null projection.
- Add a data-wide migration: rejected because legacy absence has a safe fallback
  and the first safety write can establish authority lazily.
- Merge canonical and generic/history values by timestamp: rejected because a
  newer or unorderable projection is a conflict, while older state is merely a
  stale projection. Authority resolution must fail closed or select the whole
  canonical record; it must not synthesize a third state from competing files.

## Decision 17: Treat the full authority path and coherent candidate set as security boundaries

**Decision**: Canonical use-case, run-authority, and WorkflowRun reads/writes
must reject a direct link or any persisted POSIX symlink/Windows junction or
reparse-point ancestor present at validation and must not reach that redirect
target. A present malformed,
identity-mismatched, unsupported, or non-regular run-authority file fails closed
instead of falling back to YAML. WorkflowRun selection accepts exactly one
structurally valid newest matching candidate. A completed workflow requires
`currentStage: run`, `completedAt`, and a completed `run` state; a non-completed
workflow cannot carry `completedAt`. Predecessors of the current stage must be
completed or skipped, with the exercised repair exception for a failed `run`
immediately before `repair` and the post-repair revalidation shape that retains
completed repair history while resetting `validate`/`run`. An equal-newest
timestamp remains ambiguous even when one candidate is referenced by the
mutable use-case projection.

This guarantee is for persisted workspace redirects and cooperating
VerifySignal processes. Concurrent adversarial same-user replacement between
validation and ordinary authority I/O is outside the local-worktree threat
model; prepared-request ownership remains handle-anchored against that race.

**Rationale**: Checking only the final pathname does not stop an ancestor from
redirecting an authority read or write outside the project. Likewise, a stale
projection must not repair an invalid candidate or break a tie between two
equally new authorities. Both cases would turn non-authoritative state into a
security decision.

**Alternatives considered**:

- Check only `Path.is_symlink()` on the final file: rejected because a parent
  directory can redirect the same operation.
- Follow the redirected path and validate its resolved location afterward:
  rejected because the race and external-write boundary already occurred.
- Prefer a referenced WorkflowRun when newest timestamps tie: rejected because
  the reference is a derived projection, not authority.
- Accept enumerated fields without stage coherence: rejected because a
  syntactically valid but impossible stage progression can authorize run.

## Decision 18: Make Windows-only safety behavior a native protected gate

**Decision**: Add a `windows-safety` job on `windows-latest` with Python 3.12
that installs Spec plus pytest and runs the run-invocation-lock,
durable-run-persistence, authority-path-safety, and native prepared-request
handle unit suites. Durable persistence includes native execution of
`test_durable_create_is_native_no_replace_and_leaves_no_temporary_file`; the job
also executes `test_workspace_layout_portability.py` and
`test_run_history_filename_portability.py`, including the same portable-name
and RunHistory/WorkflowRun case-fold collision corpus exercised by POSIX.
The stable
protected `spec` context depends on this job, the full Ubuntu `spec-tests` job,
and the separate `windows-install` customer journey, and fails unless all three
succeed.

**Rationale**: POSIX tests cannot execute `CreateMutexW`,
`MoveFileExW(REPLACE_EXISTING | WRITE_THROUGH)`, the no-replace write-through
move used for RunHistory, or native reparse/junction detection, while the
installer journey proves installation rather than safety primitives. Both
Windows checks are needed and serve different contracts.

**Alternatives considered**:

- Mock Win32 calls on Ubuntu only: rejected because it does not exercise native
  handle, mutex, or write-through behavior.
- Add the focused pytest modules to `windows-install`: rejected because that job
  intentionally proves the advertised customer installer path and has a
  separate dependency/tooling profile.
- Leave native safety tests advisory: rejected because branch protection would
  permit a regression in a mandatory platform primitive.

## Decision 19: Use one portable authority-name boundary across supported filesystems

**Decision**: Apply one bounded, full-match filename-component grammar to
use-case aliases, generated IDs, public Core run IDs, RunHistory IDs, and
WorkflowRun IDs: lowercase aliases use at most 80 characters, lowercase
generated IDs and mixed-case run IDs use at most 200 characters, and every
grammar starts alphanumeric then permits only alphanumeric, dot, underscore, or
hyphen. Reject control characters, trailing dot/space, and Windows
device basenames (`CON`, `PRN`, `AUX`, `NUL`, `COM1`-`COM9`, and
`LPT1`-`LPT9`) case-insensitively, including when followed by an extension.
Before RunHistory or WorkflowRun read, selection, or write, scan the whole
authority sibling namespace and fail closed when two names differ only by case
or the scan cannot be completed. Run the same corpus on POSIX and native
Windows.

**Rationale**: A case-sensitive host can otherwise create two valid-looking
authorities that collapse to one path on a default Windows filesystem. Likewise,
a basename accepted on POSIX may be an unaddressable Windows device path. The
workspace contract must not depend on the host that first persisted it.

**Alternatives considered**:

- Validate only separators and traversal: rejected because it accepts Windows
  devices, control/trailing characters, and cross-platform collisions.
- Lowercase every public Core run ID: rejected because it changes public
  identity and can merge two already-distinct values.
- Let the newest timestamp or mutable projection break a case-fold tie: rejected
  because filename identity is ambiguous before content authority is selected.

## Decision 20: Scan secret structure before generic metadata exemptions

**Decision**: Use one recursive secret scanner for affected authority and
workflow writes. It traverses mappings, secret-named and compound secret alias
mapping/list containers (including `apiToken`), and arbitrarily nested sequences
with an iterative traversal while carrying secret-field context to scalar
leaves. Cycles and defensive depth/size limits fail closed with a structured
blocking finding rather than interpreter recursion. For every scalar, detect
userinfo and secret query/fragment parameters in URI schemes and URI references,
including scheme-less, network-path, relative-query, and references embedded in
prose or bounded repeatedly encoded nested values, plus verified Bearer/Basic
credentials and opaque base64/base64url or other high-entropy values before
applying generic public-metadata field exemptions. High-entropy public branch,
identifier, structured-code, schema-version, Core run-ID, and path values are
allowlisted only in their matching field context and with an exact public
shape. Git branch shapes include slash-separated names and numeric
single-component feature branches. Exact `credential` leaves remain
secret-bearing, including below runtime-output metadata, while validated
`credentialRefs` environment key names stay public. Exact
query-key matching includes compound `*_token` keys and provider
credential/signature segments in bracketed/array aliases without treating
public near-matches as secrets. Windows drive-relative values are rescanned
after whitespace or punctuation boundaries. A whitespace-containing or multiline prose
scalar is not parsed as one giant URI; its embedded references are scanned
independently. Keep only exact public digest, credential/session-reference, and
shape-validated selector/token-policy containers as narrow allowlists. A valid
selector has exactly one primary signal plus typed modifiers; token-policy
fields use documented scalar types and enums. Malformed candidates retain
secret context instead of raising or bypassing the scan. Complete the scan
before the first affected write.

**Rationale**: A field named `reportPath`, a scalar placed in a list, a secret
under a container such as `authorization`, or a non-HTTP URI must not turn the
same credential into safe persisted metadata. Structural recursion and ordering
make the redaction boundary independent of document shape and field naming.

**Alternatives considered**:

- Scan only dictionary scalar values: rejected because lists and nested
  containers bypass the field context.
- Inspect only HTTP(S) URLs: rejected because database, WebSocket, and other URI
  schemes, URI references without a scheme, and references embedded in prose
  can carry the same userinfo/query credentials.
- Apply path/schema/id exemptions before content checks: rejected because a
  credential-bearing URI, Bearer token, or opaque secret can be mislabeled as
  public metadata.
