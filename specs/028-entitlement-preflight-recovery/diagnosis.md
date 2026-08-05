# Entitlement Preflight Recovery Diagnosis

| Field | Value |
|---|---|
| Status | Confirmed |
| Diagnosed on | 2026-08-05 |
| Spec branch | `028-entitlement-preflight-recovery` |
| Spec baseline | `8b36d8d6ff57ed880cfd3d199c26339cd765caa6` (`origin/main`) |
| Incident Spec version | VerifySignal Spec `0.22.1` |
| Companion diagnosis | `verifysignal/specs/022-entitlement-preflight-recovery/diagnosis.md` |

## Executive verdict

The trivial localized-home use case was authored coherently, but a fresh Spec
workspace silently selected an adjacent Core source checkout and declared it
ready without proving a protected operation. That source Core hit the confirmed
same-key-ID trust-selection defect described in the companion Core diagnosis and
returned a real `verifysignal.error/v1` envelope with
`entitlement.key-unknown`.

Spec then amplified that pre-execution rejection in four ways:

1. its Core error adapter did not recognize the real top-level error code;
2. direct `run` did not enforce the already-blocked validation state;
3. the Core error was persisted as a synthetic failed browser run with missing
   gates and unknown side-effect state;
4. a separate legacy confirmation path converted that state into
   `unknown-write-risk`, although the use case was `none/observe`, Core had not
   started execution, and the same run record said rerun was allowed.

The backend is not causal. The cached receipt/key pair is valid, the cached and
Core built-in public keys have identical fingerprints, and the exact authoring
check passes in Core's production trust context. Recovery belongs to Core and
Spec; no backend production-code branch is required.

| Area | Verdict |
|---|---|
| Golden Path runtime selection/readiness | **P0**: fresh workspace can silently select an ancestor-sibling source runtime and overstate readiness |
| Core error handling/run lifecycle | **P0**: pre-execution failure becomes a fake failed browser run |
| Run prerequisites | **P0**: direct run bypasses blocked validation |
| Rerun/confirmation state | **P0/P1**: contradictory decision engines create false write risk |
| Workflow persistence | **P1**: WorkflowRun and rendered stage state diverge |
| Backend | Correct inputs; no production-code change required |

## Scope and provenance

The diagnosis used current main source, pure probes, focused tests, and the
persisted incident artifacts under
`../rigel-rise-website/.verifysignal/`. The feature worktree was clean before
this document was added. No production data was changed and no raw receipt,
signature, token, private key, credential, email address, or PEM value was
printed or copied into this record.

The incident artifacts establish the following boundaries:

- repository understanding and all authored stage documents were persisted;
- target confirmation was correctly stored as `direct-user` on a real
  WorkflowRun;
- static authoring coherence passed with all four required gates exercised and
  zero blockers/warnings;
- Core rejected authoring-check and run at the entitlement boundary;
- the protected Core run did not start its deterministic browser runner;
- Spec nevertheless wrote a run record, a later confirmation record, and a
  repair record.

This does not claim that no browser was used elsewhere during interactive
authoring. It proves that this protected Core `run` never reached its browser
runner.

## Sanitized incident timeline

All timestamps are UTC on 2026-08-04.

| Time | Persisted event |
|---|---|
| 13:50:38 | Workspace created without `coreResolutionMode` in `../rigel-rise-website/.verifysignal/workspace.yaml` |
| 13:50:48 | Valid production entitlement receipt issued; only non-sensitive metadata was inspected |
| 14:03:49 | Onboarding declared an `ancestor-sibling` source Core ready |
| 14:19:45 | Repository understanding persisted at revision `5adfd592...`; a WorkflowRun was created with only `understand` completed |
| 14:20:14 | Production URL persisted as a correct `direct-user` confirmation |
| 14:21:24 | Plan persisted with four required gates |
| 14:23:54 | Canonical request and skill persisted: 14 targets, 104 steps, seven assertions, side-effect policy `none/observe` |
| 14:26:10 | Static authoring coherence passed; protected authoring-check then returned `entitlement.key-unknown` |
| 14:26:36 | Direct run reached Core despite blocked validation; Spec persisted a same-second synthetic failed run with no report or evidence |
| 14:26:57 | Later preflight persisted `unknown-write-risk` despite false side-effect booleans and an allowed rerun decision |
| 14:27:30 | Repair persisted zero deterministic findings and no actionable repair |

The real evidence is concentrated in:

- `../rigel-rise-website/.verifysignal/use-cases/localized-home-across-locales.yaml:188-605`;
- `../rigel-rise-website/.verifysignal/runs/localized-home-across-locales/localized-home-across-locales-20260804T142635Z.yaml:1-207`;
- `../rigel-rise-website/.verifysignal/confirmations/localized-home-across-locales.yaml:1-16`;
- `../rigel-rise-website/.verifysignal/workflows/runs/wf-20260804-141945-89527ed1-localized-home-across-locales.yaml:6-72`;
- `../rigel-rise-website/.verifysignal/workflows/use-cases/localized-home-across-locales/state.yaml:5-71`.

## Corrected causal chain

1. Fresh workspace initialization did not persist `coreResolutionMode`.
2. The absent field resolved to legacy `legacy-auto` behavior.
3. Legacy resolution discovered and selected the adjacent Core source checkout.
4. Version compatibility plus Spec-side receipt/key-cache checks were reported
   as runtime readiness; no protected-operation proof had run.
5. Source Core defaulted to `development-test` and hit its confirmed
   duplicate-before-context-filter defect, returning
   `entitlement.key-unknown` before browser execution.
6. Spec's entitlement classifier inspected only legacy
   `data.findings[].code`, not the real top-level `error.code`, so the public Core
   error was not normalized.
7. Direct `run` did not apply the same `record.status == ready` prerequisite as
   `workflow check run` and invoked Core despite blocked validation.
8. The run command treated the error envelope as a browser outcome, synthesized
   missing gate coverage and a failed run, and lost the causal error code from
   the run record.
9. Side-effect inference persisted `postCommit: false` and
   `sideEffectMayExist: false` but defaulted `sideEffectStatus` to `unknown`.
10. The canonical rerun evaluator allowed the read-only rerun, while a separate
    legacy path interpreted any unknown status as write risk and persisted a
    blocking confirmation.

The repair result does not corroborate that authoring was sound. It means the
Core entitlement error was not translated into a deterministic repair finding.
The evidence for sound authoring is the passing authoring-coherence result and
the exact production-context Core authoring check passing with zero findings.

## Findings

### S-01 — P0: fresh Golden Path workspaces silently retain legacy runtime selection

`init_workspace()` does not stamp `coreResolutionMode` in
`src/verifysignal_spec/workspace/repository.py:102-134`. An absent value becomes
`legacy-auto` at `:184-189`. Initialization immediately calls runtime setup in
`src/verifysignal_spec/commands/init.py:22-38`, while legacy resolution accepts
local overrides in `src/verifysignal_spec/runtime/resolver.py:184-191` and
searches workspace, environment, PATH, and ancestor siblings at `:531-554`.

A fresh-workspace probe confirmed no stored mode, effective mode
`legacy-auto`, and multiple ancestor-sibling Core candidates. This behavior is
currently preserved by `tests/integration/test_core_update.py:63-76`.

Backward compatibility for existing workspaces whose schema predates the field
is distinct from the default for a genuinely new Golden Path workspace. The
planning phase must make that distinction explicit rather than silently treating
new and legacy workspaces alike.

### S-02 — P0: readiness proves inputs exist, not that protected Core execution is ready

The resolver declares a compatible local command ready after version checks and
Spec-side receipt/key preparation in
`src/verifysignal_spec/runtime/resolver.py:192-252`. The legacy setup path does
the same in `src/verifysignal_spec/workflows/core_setup.py:94-196`.

The incident use-case record consequently reports all of the following at once:

- runtime source `ancestor-sibling` and status `ready`;
- valid receipt and active cached verification key;
- recommended next action to continue with validation or run;
- immediate protected authoring-check failure with
  `entitlement.key-unknown`.

The existing ancestor-sibling entitlement test uses a fake Core that only checks
whether environment JSON contains a key ID. Its fixture ID differs from the
official built-in ID, so it cannot exercise Core trust-context selection or
same-ID deduplication. Readiness language must not imply protected readiness
until a public runtime proof establishes it.

### S-03 — P0: real Core error envelopes are not normalized and become pseudo-runs

`CoreAdapter._run()` appropriately parses JSON stdout even when the subprocess
exits nonzero in `src/verifysignal_spec/core/adapter.py:65-90`. The downstream
classifier is the defect: `core_entitlement_blocker_code()` inspects only
`data.findings[].code` at
`src/verifysignal_spec/core/contracts.py:241-250`. Real Core returns
`verifysignal.error/v1` with a top-level `error.code`.

A pure probe confirmed:

```text
real envelope {status:error,error:{code:entitlement.key-unknown}} -> null
legacy fake envelope {status:blocked,data.findings:[...]}          -> entitlement.unverifiable
```

Validate calls this incomplete parser at
`src/verifysignal_spec/commands/validate.py:291-299`; run does not call it.
After Core returns, `src/verifysignal_spec/commands/run.py:383-508` treats any
response as a browser outcome, invents a run ID and gate misses, changes use-case
status, appends history, and selects repair guidance. The incident record has no
Core report or evidence path, yet recommends inspecting and repairing a Core
report.

A pre-execution entitlement rejection must remain a blocked/not-started
preflight outcome. It must not create browser-run coverage, history, side-effect,
confirmation, or repair state. Spec needs one schema-aware normalization boundary
for current public Core errors, with legacy findings accepted only as an explicit
compatibility path. Core should supply public pre-execution metadata rather than
forcing Spec to infer private ordering.

### S-04 — P0: direct run bypasses blocked validation and shared prerequisites

`workflow check run` requires `record.status == ready` in
`src/verifysignal_spec/workflows/prerequisites.py:517-523`. The public
`commands.run.run()` path loads artifacts and performs several checks at
`src/verifysignal_spec/commands/run.py:60-171`, but does not enforce use-case
readiness or reuse that prerequisite policy before invoking Core.

A controlled probe with complete artifacts but blocked validation produced:

```text
workflow check run -> missing, canProceed=false, next=validate
direct run         -> passed, Core invoked, coverage complete
```

The current CLI run contract test constructs a use case that is not
validated/ready and expects direct success, accidentally making the bypass part
of the test suite. Planning must converge check and execution on a single pure
run-preflight decision, evaluated before runtime/Core invocation.

### S-05 — P0/P1: rerun policy has two contradictory engines and `afterUnknown` is inert

`RerunPolicy.afterUnknown` is parsed and validated in
`src/verifysignal_spec/workspace/models.py:121-180`, but the evaluator selects
only `afterCommit` or `afterNoCommit` in
`src/verifysignal_spec/workflows/write_safety.py:382-404`. Non-write classes are
allowed immediately.

A separate legacy assertion in
`src/verifysignal_spec/workspace/repository.py:1190-1202` treats every
`sideEffectStatus == unknown` as risky, regardless of explicit false
`postCommit` and `sideEffectMayExist` values. Confirmation generation at
`:1081-1098` then labels even a class-`none` operation
`unknown-write-risk`. Direct run consults this confirmation path before the
canonical evaluator at `src/verifysignal_spec/commands/run.py:171-283`.

Varying `afterUnknown` across `allowed`, `blocked`, and
`requires-confirmation` produced the same result in every probe: the canonical
decision remained allowed via `afterNoCommit`, while the legacy path still
generated unknown write risk. Therefore the incident gate was not the user's
`afterUnknown` policy working as authored; that field was not consumed.

The later design needs one authoritative decision model shared by workflow
check, direct run, and list/status surfaces. Unknown handling should apply only
to genuinely indeterminate write outcomes, never to a documented pre-execution
failure or side-effect class `none` with explicit false booleans.

### S-06 — P1: stale confirmation artifacts survive after risk disappears

The repository exposes save/load operations but no clear/expire path at
`src/verifysignal_spec/workspace/repository.py:738-744`.
`list_risk()` trusts the stored confirmation at `:952-965` instead of deriving
the current requirement.

In a probe, an unknown state created a confirmation. After replacing the last
run with an explicitly safe pre-execution/not-started state, recalculated
requirements were empty, but the stored artifact remained and list output still
reported confirmation required. Direct run recalculates, so list and execution
can disagree.

Confirmation persistence must be reconciled atomically with current risk. If
historical confirmations are retained for audit, they must be visibly historical
rather than active gates.

### S-07 — P1: WorkflowRun and rendered workflow state diverge

`state_document(..., run=None)` creates a fresh all-pending stage array in
`src/verifysignal_spec/workflows/repository.py:61-93`. Stage persistence calls it
without the active run for specification, clarification, planning, tasks, and
implementation in
`src/verifysignal_spec/workflows/stage_persistence.py:331-357,373-426,503-533,548-562,724-726`.
The active WorkflowRun is loaded there only for target confirmation at
`:1195-1216`; normal stage progression does not transition it.

A probe reproduced the split: after persisting a specification, the WorkflowRun
remained at `understand`, while the rendered state moved forward but reset every
stage to pending. The incident artifacts show the same divergence: the real run
is paused at `understand`, while alias state says `validate` and marks every
stage pending.

One atomic transition must own WorkflowRun progression, the use-case reference,
and rendered state. Derived state should be rendered from that authoritative run,
not reconstructed with an empty stage list.

### S-08 — P2: incident artifact fidelity is incomplete

Several persisted details make forensic recovery harder:

- the claimed `discover: all-grounded` result is not independently recoverable;
  no discover result was saved, candidate grounding statuses remain `unknown`,
  and its task remains pending;
- all authored task statuses remain pending after later stages ran;
- rendered state references `validation.md` and `repair.md`, but neither file
  exists;
- structured product context records seven inventory items, five candidates,
  and six unique signal references, while rendered understanding reports no
  product signals and only one candidate;
- the synthetic run retains only `coreStatus: error`, losing the actual Core
  error envelope/code that caused it.

These gaps did not cause the entitlement failure, but they weaken auditability
and made the one-pass narrative more confident than the durable evidence.

## Verification

The primary focused current-main suite passed outside the loopback restriction
of the filesystem sandbox:

```text
54 passed
```

It covered Core update/resolution, runtime resolver, Core adapter, managed
runtime entitlement handoff, receipt invocation, agent guardrails, and explicit
confirmation contracts. The only warnings were pytest temporary-directory
cleanup warnings and were not product failures.

Supplemental focused runs also passed:

- 3 runtime-resolution compatibility tests;
- 40 adjacent CLI run, rerun, workflow, and stage-persistence tests;
- the ancestor-sibling entitlement readiness test when loopback binding was
  permitted.

Pure probes independently reproduced:

- missing fresh-workspace mode and ancestor-sibling selection;
- failure to classify the exact real Core error envelope;
- pseudo-run persistence from a pre-execution Core error;
- direct-run validation bypass;
- inert `afterUnknown` plus contradictory unknown-write-risk;
- stale confirmation/list state;
- WorkflowRun/rendered-state divergence.

The green suites demonstrate regression gaps rather than disproving the
findings. The later plan must add production-shaped coverage for each reproduced
case, including exact public Core envelopes and a same-official-key-ID source
runtime.

## Backend and repository ownership

The backend produced correct inputs. The incident validation used cached
material (`api.status: not-checked`), the cached receipt and active key agreed on
the official key ID, and the cached public key fingerprint exactly matched
Core's built-in production key. The same artifacts pass Core authoring-check in
the production trust context.

No VerifySignal backend production-code change is required. An existing backend
contract test named for BE/Spec/Core compatibility exercises backend routes but
does not invoke Spec or Core; broader cross-repository journey coverage may be
valuable, but it should not create a backend implementation dependency for this
recovery.

## Inputs for the planning phase

This document is a diagnosis, not the implementation plan. The next phase must
decide the recovery sequence while preserving these constraints:

1. new Golden Path workspaces must have an explicit managed runtime policy,
   without breaking legacy workspaces that predate the field;
2. readiness must distinguish command/version compatibility, trust-material
   availability, and proven protected-operation readiness;
3. one public Core outcome normalizer must classify pre-execution entitlement
   failures before any run state is persisted;
4. direct run and workflow check must share one prerequisite decision;
5. rerun and confirmation behavior must come from one authoritative engine and
   reconcile stale artifacts;
6. WorkflowRun must be the authoritative state machine for persisted stages;
7. Core and Spec require cross-repository regression coverage; backend
   production code remains outside scope.
