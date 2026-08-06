# Contract: WorkflowRun-Authoritative Persistence

## Authority

For an active staged workflow,
`verifysignal-spec-workflow-run/v1` is authoritative for current stage, workflow
status, stage states, target confirmation, blockers, and next/resume commands.

A protected preflight resolves that authority once. The exact WorkflowRun
instance that determines stage eligibility also supplies target confirmation;
stage and target gates must never come from different recovered/projection runs.

The following are projections, not independent authorities:

- the use-case `workflow` reference;
- `verifysignal-spec-workflow-state/v1` under the alias workflow directory.

`state_document()` must receive the authoritative run. It must not construct an
all-pending list for an existing active run.

### Authority document validation

A WorkflowRun is decoded or selected only after its document passes this strict
boundary:

- mapping shape; exact schema and workflow identity;
- portable single-component `runId`/`useCaseAlias`, with document run ID equal
  to its filename and, when selected for an alias, the declared alias equal to
  that request. Controls, trailing dot/space, and Windows device basenames are
  invalid case-insensitively, including before an extension;
- supported workflow status/current stage/integration;
- valid required workflow start/update timestamps and valid optional workflow
  completion timestamp when present;
- exactly one structured state for every supported stage, with supported stage
  status, valid optional timestamps, and structured non-empty blocker codes
  whose optional severity/category/message/recovery/documentation fields have
  the declared scalar types;
- structured gate decisions with supported stage/decision, valid timestamp, and
  a string-or-null reason;
- for status `completed`, `currentStage: run`, a workflow `completedAt`, and a
  completed `run` state; for every other status, null `completedAt`;
- completed-or-skipped predecessors of the current stage, except that the
  exercised repair transition permits a failed `run` immediately before
  `repair`, and post-repair revalidation may retain completed repair history
  while resetting `validate` and `run` to pending;
- when present, exactly the allowed target-confirmation fields, expected
  question ID, non-empty URL, direct-user/explicit-command source, and valid
  timestamp;
- no secret-looking values and no direct or ancestral POSIX symlink or Windows
  junction/reparse-point authority path on read or write.

Stage-level `startedAt`/`completedAt` are compatibility-optional. When present
they must be valid timestamps, but legacy or pending stage state is not rejected
solely because either field is absent.

Candidate discovery first determines whether a structured regular file declares
the requested alias. Any such matching candidate that then fails validation is
`workflow.authority-invalid`; it is not silently skipped in favor of an older
valid referenced run. A candidate declaring another alias, or an unreferenced
unstructured/non-candidate file, does not displace this alias's valid authority.
A referenced invalid/unstructured/redirected document always fails closed.

Candidate discovery and every WorkflowRun read/write scan the sibling namespace
before authority selection or mutation. Two `.yaml` names that differ only by
case are ambiguous on the supported cross-platform workspace contract and fail
closed even on a case-sensitive host; inability to verify siblings also fails
closed. A use-case reference cannot break the collision.

Newest-authority comparison preserves all nine fractional timestamp digits.
Each WorkflowRun write assigns `updatedAt` strictly after its prior timestamps
and every parseable persisted WorkflowRun update timestamp, even when the wall
clock is equal or moves backward. Equal newest timestamps remain ambiguous and
fail closed even when one tied candidate is named by the mutable use-case
reference; that projection is not an authority tie-breaker.

## Transition interface

One transition operation receives:

- project and use-case alias;
- active run ID or permission to lazily migrate;
- source stage and transition outcome (`completed`, `blocked`, `failed`);
- durable document path, structured blockers, and next command;
- optional valid target confirmation.

It returns the updated WorkflowRun and the two derived projections.

### Write and healing order

1. Load the latest WorkflowRun referenced by the use case. If absent, apply the
   lazy migration contract below.
2. Validate stage ordering, blocker shape, target confirmation, and secret
   safety in memory, and reject any redirected authority path before opening or
   replacing its target.
3. Assign a logically later nanosecond `updatedAt` and write the validated
   WorkflowRun using existing atomic single-file replacement.
4. Derive and write the use-case reference from that run.
5. Derive and write rendered state from that run.
6. Reload/compare run ID, stage, and status across all three documents.

The three-file group is **not** transactionally or crash atomic. If a process
stops after step 3 or 4, the next mutating workflow transition treats WorkflowRun
as the authority and heals missing or stale projections before applying its new
transition. Read-only surfaces render from WorkflowRun without writing; repair
never reconstructs WorkflowRun from a stale projection.

The no-redirect boundary covers every traversed project-relative component,
including `.verifysignal`, `workflows`, `runs`, and the final document. A
regular-looking filename below a symlink/junction/reparse ancestor is invalid,
and a rejected save must leave the external target unchanged.

That ordinary authority boundary covers redirects present at validation and
cooperating VerifySignal processes. Adversarial same-user component replacement
between validation and ordinary authority I/O is outside the local-worktree
threat model. Prepared-request creation and cleanup remain separately
handle-anchored against pathname replacement.

## Stage transition table

| Event | Source/current stage | Updated stage state | Workflow current stage/status |
|---|---|---|---|
| Understanding persisted | `understand` | `understand: completed` | `specify / paused` |
| Specification persisted | `specify` | `specify: completed` | `clarify / paused` |
| Clarification persisted and blockers resolved | `clarify` | `clarify: completed` | `plan / paused` |
| Clarification persists blocker | `clarify` | `clarify: blocked` with blockers | `clarify / paused` |
| Plan persisted | `plan` | `plan: completed` | `tasks / paused` |
| Tasks persisted | `tasks` | `tasks: completed` | `implement / paused` |
| Implementation persisted | `implement` | `implement: completed` | `validate / paused` |
| Authoring-check passed without `--runtime-readiness` | `validate` | `validate` remains pending | `validate / paused` |
| Runtime-readiness validation or revalidation passed | `validate`, `run`, or `repair` | `validate: completed`; later-stage state is reset when revalidating | `run / paused` |
| Runtime-readiness validation blocked/error | `validate`, `run`, or `repair` | `validate: blocked` with normalized blockers; later-stage state is reset when revalidating | `validate / paused` |
| Valid real run passed | `run` | `run: completed` | `run / completed` with `completedAt` |
| Valid real run failed | `run` | `run: failed` | `repair / paused` |
| Core error/invalid schema during run | `run` | `run: blocked` with normalized blockers; never executed/failed | `run / paused` |
| Successfully applied repair persisted | `repair` | `repair: completed`; `validate` and `run` reset to pending | `validate / paused` |

Earlier completed authored stages remain completed on every later transition.
Revalidation deliberately resets states after `validate`; a successfully applied
repair deliberately resets `validate` and `run` so neither result can be
claimed from pre-repair evidence. A blocked stage can be retried; success clears
that stage's active blockers.

## Protected command stage guard

Protected validation is allowed only when the current stage is `validate`,
`run`, or `repair`. Run is allowed only at `run`. The guard is evaluated before
runtime resolution, environment loading, prepared-request creation, or Core
invocation. An active workflow reads that stage from WorkflowRun authority and
threads the same resolved run into target-confirmation evaluation. It does not
perform a second authority lookup through
`UseCase.workflow.lastWorkflowRunId`. A legacy staged use case with no
WorkflowRun may derive only this pre-migration
decision from the validated canonical documents, supported plan/task
projections, compatible legacy workflow reference, and safe executable
references described below; its next workflow persistence creates WorkflowRun.
An on-disk referenced but invalid authority never receives this exception.

An otherwise valid managed workflow at the wrong stage returns one structured
blocker:

```json
{
  "code": "workflow.stage-out-of-order",
  "severity": "blocker",
  "category": "workflow",
  "message": "Workflow current stage is tasks; cannot execute run.",
  "currentStage": "tasks",
  "requestedStage": "run",
  "recoveryCommand": "/verifysignal-tasks <alias>"
}
```

If authority resolution is invalid because an on-disk referenced WorkflowRun or
any alias-matching candidate cannot be decoded and strictly validated, or
because the newest matching authorities are ambiguous, the command fails closed
with `workflow.authority-invalid`,
`currentStage: unknown`, the requested stage, and a safe workflow
status/list recovery command. It MUST NOT trust the mutable use-case reference or
rendered state as fallback stage authority, and it performs zero Core resolution
or invocation. A standalone pre-workflow use case with no WorkflowRun and no
durable workflow evidence remains outside this managed-stage guard.

## Projection invariants

After healing or a successful transition:

```text
WorkflowRun.runId == UseCase.workflow.lastWorkflowRunId
WorkflowRun.currentStage == UseCase.workflow.currentStage
WorkflowRun.status == UseCase.workflow.workflowStatus
WorkflowRun.currentStage == RenderedState.currentStage
WorkflowRun.status == RenderedState.status
WorkflowRun.stageStates == RenderedState.stageStates
```

Rendered commands may be adapted for the active integration, but their semantic
stage and alias must match the WorkflowRun.

The target-confirmation gate reads
`WorkflowRun.targetEnvironmentConfirmation` from this same authority. If a stale
use-case reference points to an older confirmed run while recovery selects a
newer unconfirmed run, the newer run controls both gates and preflight blocks.

## Lazy migration

Migration occurs only on the next workflow persistence when the authority loader
finds no active WorkflowRun. The loader first recovers a unique newest matching
WorkflowRun when possible, including after a stale reference to a removed run.
An on-disk referenced or alias-matching WorkflowRun that exists but cannot pass
strict validation, or ambiguous newest matching authorities, are errors, not
permission to rebuild authority from projections.

1. Collect durable authored-stage evidence:
   - readable canonical authored-stage documents and durable `plan.yaml` /
     `tasks.yaml` projections only when they are regular project-owned files,
     declare the exact `verifysignal-spec-workflow-artifact-plan/v1` /
     `verifysignal-spec-workflow-tasks/v1` schema respectively, and carry the
     same `useCaseAlias` being migrated;
   - a compatible legacy workflow reference whose current stage proves prior
     authored stages; and
   - project-relative `runRequest`, `mainSkill`, `skills`, or
     `sourceOnlySkills` references only when each cited artifact resolves safely to
     an actual regular, non-symlink file. Any valid executable reference is
     implement-stage evidence; a path string alone is not.
2. Select the furthest authored stage supported by the collected evidence and
   backfill that stage and every earlier authored stage as completed. This
   intentionally preserves legacy workspaces whose later durable artifacts
   survived even when an earlier canonical stage document did not.
3. With implement-stage evidence, set `currentStage: run` only when the
   existing readiness snapshot proves a passed protected operation; otherwise
   set `currentStage: validate`. With no authored evidence, begin at
   `understand`.
4. Create exactly one WorkflowRun, copy a valid existing direct target
   confirmation, write the WorkflowRun as authority, and derive/link both
   projections.
5. Preserve use-case data, real run history, readiness, supersede reviews, and
   active confirmation artifacts. Migration does not create a browser run or
   RunHistory record, Core execution result, discover/gate/evidence artifacts,
   task execution statuses, or repair result.

A second write follows the linked run and creates no additional migration run.

## Error and preflight behavior

- A blocked run preflight does not transition the `run` stage to started,
  completed, or failed.
- Immediately before Core invocation, direct run persists conservative
  write-ahead `lastCoreAttempt` intent. A Core error can refine that marker,
  update an active confirmation derived from unknown write risk, and update the
  managed WorkflowRun `run`-stage blocker plus its projections, but does not
  create a WorkflowRun browser-run event or rewrite the prior readiness
  snapshot.
- A valid real run keeps the marker through `record_run`; terminal WorkflowRun
  transition and marker clearing follow authoritative real-run persistence.
- A valid failed `verifysignal.run/v1` is a real run and therefore advances to
  repair even when evidence is partial.
- Target confirmation remains scoped to the same WorkflowRun and is never
  self-confirmed from authored plan/implementation text.

## Secret safety

WorkflowRun and rendered state pass existing secret validation before each
individual write. The use-case workflow reference is derived from allowlisted
WorkflowRun fields and uses the existing use-case writer; it is not a raw-result
copy or a claim that the whole use-case record is rescanned at this boundary.
Healing does not copy raw Core responses, environment values, receipt/key
material, report contents, or stderr.

The shared validator recurses through mappings, secret-named mapping/list
containers (including compound aliases such as `apiToken`), and arbitrarily
nested lists with an iterative traversal that fails closed on cycles or
defensive depth/size limits while preserving secret-field context to each
scalar leaf. It
rejects credential-bearing userinfo and secret query/fragment parameters for
URI schemes and URI references, including scheme-less, network-path,
relative-query, and references embedded in prose, plus Bearer/Basic credentials
and opaque high-entropy values before generic public-field exemptions.
Whitespace-containing/multiline prose is not parsed as one URI; embedded
references are scanned independently. Only exact public digest/reference and
documented public-container shapes retain narrow allowlists, and validation
finishes before the first WorkflowRun, rendered-state, or derived-reference
write.

Nested references are percent-decoded only through a bounded scan, query-key
recognition includes credential/signature provider and bracketed/array forms,
and base64/base64url payloads remain subject to entropy checks. Documented
selector and token-policy containers lose secret context only after their field
and value shape is validated; a secret-looking alias by itself is not public.
