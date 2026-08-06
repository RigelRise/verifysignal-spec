# Contract: WorkflowRun-Authoritative Persistence

## Authority

For an active staged workflow,
`verifysignal-spec-workflow-run/v1` is authoritative for current stage, workflow
status, stage states, target confirmation, blockers, and next/resume commands.

The following are projections, not independent authorities:

- the use-case `workflow` reference;
- `verifysignal-spec-workflow-state/v1` under the alias workflow directory.

`state_document()` must receive the authoritative run. It must not construct an
all-pending list for an existing active run.

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
   safety in memory.
3. Write the updated WorkflowRun using existing atomic single-file replacement.
4. Derive and write the use-case reference from that run.
5. Derive and write rendered state from that run.
6. Reload/compare run ID, stage, and status across all three documents.

The three-file group is **not** transactionally or crash atomic. If a process
stops after step 3 or 4, the next mutating workflow transition treats WorkflowRun
as the authority and heals missing or stale projections before applying its new
transition. Read-only surfaces render from WorkflowRun without writing; repair
never reconstructs WorkflowRun from a stale projection.

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
invocation. An active workflow reads that stage from WorkflowRun authority. A
legacy staged use case with no WorkflowRun may derive only this pre-migration
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

If authority resolution is invalid because an on-disk referenced WorkflowRun
cannot be decoded or validated, or because the newest matching authorities are
ambiguous, the command fails closed with `workflow.authority-invalid`,
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

## Lazy migration

Migration occurs only on the next workflow persistence when the authority loader
finds no active WorkflowRun. The loader first recovers a unique newest matching
WorkflowRun when possible, including after a stale reference to a removed run.
An on-disk referenced WorkflowRun that exists but cannot be decoded or validated
or ambiguous newest matching authorities are errors, not permission to rebuild
authority from projections.

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
- A Core error can update `lastCoreAttempt`, an active confirmation derived from
  unknown write risk, and the managed WorkflowRun `run`-stage blocker plus its
  projections, but does not create a WorkflowRun browser-run event or rewrite
  the prior readiness snapshot.
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
