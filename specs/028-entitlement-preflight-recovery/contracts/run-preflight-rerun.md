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

The function performs no runtime resolution, Core/version call, environment or
dotenv read, generated-input resolution, prepared-request write, confirmation
write, or workspace mutation. After the pure result returns, callers may invoke
the single confirmation reconciliation function.

Direct run stops on the same first blocking decision as workflow check. If
`canProceed` is false, Core is invoked zero times.

## Rerun classification table

The evaluator compares a real `lastRun` with a strictly newer
`lastCoreAttempt`, when present. Equal or unparseable attempt timestamps do not
override a timestamped real run. Only `lastCoreAttempt.operation == run`
participates.

| Latest relevant evidence | Side-effect class | Outcome class | Policy branch |
|---|---|---|---|
| No real run and no run attempt | any | `none` | none; `allowed` |
| `lastCoreAttempt.executionState == not-started` | any | `no-commit` | `afterNoCommit` |
| Real run explicitly says `postCommit: false` and `sideEffectMayExist: false` | any | `no-commit` | `afterNoCommit` |
| Real run confirms/infers commit or side effect may exist | write/external notification, or historical explicit write evidence | `commit` | `afterCommit` |
| Newer run attempt has `executionState == unknown` | write/external notification | `unknown-write` | `afterUnknown` |
| Real write run has genuinely indeterminate commit/side-effect result | write/external notification | `unknown-write` | `afterUnknown` |
| Unknown label plus explicit false booleans | any | `no-commit` | `afterNoCommit` |
| Unknown attempt | none/authenticated-read with no historical write evidence | `no-commit` | `afterNoCommit` |

Historical explicit write evidence cannot be erased by changing the current
declared class to `none`. Legacy truth in `postCommit`, `sideEffectMayExist`, or
a committed-status interpretation remains write evidence even when the old run
does not contain `sideEffectPolicy` or `sideEffects` snapshots.

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

Only after preflight is ready may direct run:

1. resolve Core;
2. load approved environment inputs;
3. resolve generated inputs;
4. prepare a run request;
5. invoke Core.

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

## Persistence matrix after Core invocation

| Core outcome | RunHistory / lastRun | Evidence / coverage / repair | `lastCoreAttempt` | Workflow stage |
|---|---|---|---|---|
| Valid `verifysignal.run/v1`, passed | Persist real run | Persist public result projections | Clear after successful persistence | Complete workflow |
| Valid `verifysignal.run/v1`, failed | Persist real run | Persist diagnostic public projections | Clear after successful persistence | Advance to repair |
| `verifysignal.error/v1`, explicitly not started | Unchanged | Unchanged | Record `not-started` | Keep `run` current and blocked; do not mark executed/failed |
| `verifysignal.error/v1`, execution unknown | Unchanged | Unchanged | Record `unknown` | Keep `run` current and blocked; do not mark executed/failed |
| Invalid schema | Unchanged | Unchanged | Record contract-invalid/unknown | Keep `run` current and blocked |

Prior run history, evidence, lastRun, repair sessions, and supersede reviews are
never deleted or rewritten by a Core error.

## Compatibility and secret safety

- Existing CLI flags, including `--confirm-risk`, remain available.
- Existing rerun policies parse unchanged; `afterUnknown` becomes effective.
- Legacy error envelopes remain safe and conservative.
- Preflight and attempt output names only declared input names, never values.
- Secret canary scans cover command JSON and the complete `.verifysignal/` tree.
