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
| Protected validation passed | `validate` | `validate: completed` | `run / paused` |
| Protected validation blocked/error | `validate` | `validate: blocked` with normalized blockers | `validate / paused` |
| Valid real run passed | `run` | `run: completed` | `run / completed` with `completedAt` |
| Valid real run failed | `run` | `run: failed` | `repair / paused` |
| Core error/invalid schema during run | `run` | `run: blocked` with normalized blockers; never executed/failed | `run / paused` |
| Repair persisted and revalidation required | `repair` | repair outcome recorded | `validate / paused` |

Earlier completed stages remain completed on every later transition. A blocked
stage can be retried; success clears only that stage's active blockers.

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

Migration occurs only on the next workflow persistence when no loadable active
WorkflowRun exists.

1. Create exactly one run and immediately link it from the use case.
2. Inspect canonical stage documents in workflow order.
3. Mark a stage completed only when its durable canonical document exists and
   parses. Stop at the first missing/invalid stage; do not infer later completion.
4. Use the first incomplete stage as `currentStage`; if all authored stages and
   a valid readiness snapshot exist, choose `run`, otherwise choose `validate`
   conservatively.
5. Preserve a valid existing target confirmation by copying it into the run.
6. Preserve use-case, run history, readiness, supersede reviews, and active
   confirmation artifacts.
7. Do not synthesize discover evidence, task execution statuses, run history, or
   repair results.

A second write follows the linked run and creates no additional migration run.

## Error and preflight behavior

- A blocked run preflight does not transition the `run` stage to started,
  completed, or failed.
- A Core error can update `lastCoreAttempt` and an active confirmation derived
  from unknown write risk, but does not create a WorkflowRun browser-run event.
- A valid failed `verifysignal.run/v1` is a real run and therefore advances to
  repair even when evidence is partial.
- Target confirmation remains scoped to the same WorkflowRun and is never
  self-confirmed from authored plan/implementation text.

## Secret safety

All three documents pass existing secret validation before each individual
write. Healing copies only validated structured fields from WorkflowRun; it does
not copy raw Core responses, environment values, receipt/key material, report
contents, or stderr.
