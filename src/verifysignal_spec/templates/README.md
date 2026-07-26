# Bundled Templates

Templates are copied into target repositories by `verifysignal init`.
Generated text is English-only and points agents at the `.verifysignal/`
workspace and public VerifySignal Core CLI boundary.

Every staged `/verifysignal-*` template must start with the installed
`verifysignal workflow check <stage>` command and require the
`workflow.guardrails/v1` capability before repository inspection, browser
mapping, or stage work.
Templates must not suggest package-manager fallbacks, and they must route all
managed `.verifysignal/` writes through canonical CLI operations such as
`verifysignal workflow persist`.

Stage authoring templates must point agents to the public workflow contract from
`verifysignal workflow info verifysignal-use-case --json`. Payload shape
guidance comes from `stagePayloadContracts`, not installed package source.

The understand template must also consume
`stagePayloadContracts.browserFirstUnderstanding` when a live URL is supplied.
Browser-first mapping uses a headed Playwright MCP or equivalent host browser,
stays within the approved read-safe origin/scope, pauses for user-entered
authentication, keeps the browser open through summary acknowledgement, and
persists only synthesized signals. Raw DOM, MCP snapshots, screenshots, traces,
response bodies, cookies/storage, form values, credentials, and URL query values
must never become `.verifysignal/` artifacts.

Executable skill boundary guidance must distinguish executable skills from
source-only reusable skills. A run request lists only the skills that Spec has
resolved as executable for the current Core public contract. When Core does not
declare deterministic multi-skill roles, ordering, and evidence semantics,
agents must compose required reusable behavior into the main skill and preserve
helper skills only as source-only metadata.

Real-run guardrail templates must also preserve the planned main skill, require
explicit `gateId` evidence mappings, distinguish Core technical status from
Spec planned coverage status, and route runtime contradictions through repair or
replan instead of weakening skills live.

Browser workflow guardrail templates must require target environment
confirmation before executable planning, preserve resolved target decisions
through plan and implementation, and require
`verifysignal validate <alias> --runtime-readiness` before reporting
browser artifacts ready.

Validation output describes authored evidence mapping and must keep
`fullBrowserFlowExecuted: false` until `/verifysignal-run` executes. Run output
must treat `status` as the authoritative use-case verdict and keep
`coreBrowserStatus` separate from `specCoverageStatus`. A Core pass with missing
required gates is `status: incomplete`; a failed Core/browser run makes coverage
diagnostic and must not be summarized as passed.

Golden Path guidance must recommend a real-target first run before optional
examples, render recommendation/run/repair/blocker results as stage cards, and
never use fake/demo targets as a user-facing fallback.

Repair guidance must classify the root cause before edits. Missing prerequisite,
environment recovery, wait/flow, selector, data/product-state, coverage mapping,
and unsupported feedback have different next actions. Step-ordering repairs are
the only ones VerifySignal applies itself, and only when validation intent is
preserved; selector, wait, and run-profile repairs are proposed for the developer
to apply. Data, credential, required gate, target-selection, and
expected-behavior changes still require confirmation.

Execution-boundary repair guidance must not weaken required gates when a helper
or source-only skill passed without mapped evidence. The correct recovery is to
compose helper behavior into the main executable skill, reclassify the helper as
source-only, or use a Core runtime whose public contract declares supported
multi-skill execution.

Write-flow guidance must require explicit side-effect intent from Spec and
public guardrails from Core. Read-only use cases can declare `sideEffects.class:
none`; write and external-notification use cases default to `mode: enforce`,
need a commit step, a local side-effect envelope, runtime outputs when later
validation depends on created state, and an explicit rerun policy. Generated
runtime input names are use-case-owned and resolved per run; templates must not
hard-code target-project-specific examples as canonical names.

Human-observable debug/browser runs default to `slowMoMs: 900`; explicit
`--slow-mo` values still win.
