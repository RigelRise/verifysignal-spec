# Golden Path

The Golden Path is the first VerifySignal experience for a new project. It
guides the user toward the simplest stable validation candidate on a real target
they care about, asks them to accept or skip that recommendation, and presents
each step with clear agent-chat stage cards.

Golden Path is scoped to the first run only. After the first run is accepted,
skipped, blocked, failed, passed, or repaired-passed, ordinary understand,
specify, plan, validate, run, and repair workflows continue as normal.

## Product Principles

- Recommend a real project validation first; deterministic fixtures are for
  tests and examples only.
- Rank first-run suitability separately from product priority, branch relevance,
  and recent Git activity. Prefer unauthenticated, read-only, single-surface,
  stable rendered evidence with no credentials and low external dependency.
- Keep active-branch or high-priority work visible as secondary context, but do
  not let branch relevance outrank a lower-risk first-run candidate.
- If no candidate meets the ideal criteria, recommend the lowest-risk existing
  candidate only with explicit risk labels and explicit user acceptance.
- Treat a skipped recommendation as skipped, not as pass, fail, or inconclusive.
- After skip, manual use-case selection remains available immediately.
- Count success only when the first run reaches strict pass directly or reaches
  strict pass after a transparent safe repair cycle.
- Preserve validation intent during repair. Required gates and rendered-result
  evidence are not weakened without explicit user confirmation.
- Never persist credential values, browser storage, cookies, raw logs, or
  secret-looking target values in recommendations, repair feedback, or stage
  cards.

## Stage Card Shape

Golden Path output is agent-chat first. Every major step should be displayable as
a structured card with a status marker, summary, why-it-matters text, primary
evidence, optional repair details, and next action.

Expected guided stages:

- `[RECOMMENDED]`: the product-owned first-run recommendation is shown.
- `[ACCEPTED]`: the user accepted the recommended first run.
- `[RUNNING]`: authoring, validation, or execution is in progress.
- `[REPAIR]`: safe repair feedback is visible before revalidation/rerun.
- `[PASS]`: direct strict pass or repaired strict pass.
- `[SKIPPED]`: the user declined Golden Path and can choose manually.
- `[BLOCKED]`: runtime data, host permission, safety, or Core compatibility is
  required before continuing.
- `[FAIL]`: the first run did not reach strict pass.

## Missing Understanding

When `/verifysignal-specify` starts in a clean workspace, the prerequisite check
returns auto-prepare metadata. The integration should inspect safe public
an available repository or user-approved live URL, persist product understanding, and resume first-run
recommendation without requiring the user to invoke `/verifysignal-specify`
again. Sensitive files and credential-bearing configuration remain out of scope
unless the user explicitly approves access.

## Canonical Examples

Canonical examples are learning and regression aids. A fake/demo target must not
become the user-facing fallback when a real target or stable candidate is
missing.

### Public Unauthenticated Example

Expected outcome: a public page such as `home-page-unauth` reaches pass on a
real staging or local target without credentials. The run proves visible product
behavior such as a hero section, activity area, and ranked table or equivalent
rendered-result evidence.

Failure modes: missing target, unreachable target, slow browser timing, missing
rendered evidence, or incomplete Spec coverage.

Evidence expectations: `coreBrowserStatus=passed`,
`specCoverageStatus=complete`, `missingRequiredGates=[]`, screenshots or UI
assertions mapped to required gates, and project-local run artifacts.

Interpretation: `pass` means strict pass. `fail` means Core/browser or required
evidence failed. `not-evaluated` should appear only for explicitly conditional
optional gates.

### Authenticated Secret-Safe Example

Expected outcome: an authenticated flow validates a real behavior while
credential values remain runtime-only. The use case may reference credential
groups or environment variable names, but not actual secret values.

Failure modes: unresolved credential references, expired accounts, target
environment mismatch, or browser storage/cookie leakage attempts.

Evidence expectations: visible authenticated content, credential references
only, no browser storage values, no cookies, and no raw sensitive payloads in
stage cards, logs, recommendations, or repair feedback.

Interpretation: `pass` requires strict pass without persisted credentials.
`fail` or `blocked` is expected when runtime credentials are missing.
`not-evaluated` applies only to conditional data gates inside the authenticated
flow.

### Repairable Failure Example

Expected outcome: a safe mechanical failure such as a wait strategy issue is
classified, auto-applied when validation intent is preserved, then revalidated
and rerun before success is reported.

Failure modes: selector ambiguity, wait timeout, step ordering, target
specificity, equivalent-flow drift, or run profile defaults.

Evidence expectations: repair feedback includes root cause, autonomy,
before/after summary, intent-preserved status, revalidation status, rerun
status, and a repair stage card. Raw logs may support diagnosis but are not the
primary evidence.

Interpretation: `pass` after repair is `repaired-passed` only after revalidation
and rerun strict pass. `fail` means repair did not reach strict pass. Changes to
required gates, data assumptions, credentials, targets, or expected behavior
require confirmation instead of auto-apply.

### Conditional Data Example

Expected outcome: a data-dependent section is validated only when the clarified
condition is true in the real target environment.

Failure modes: empty seeded data, stale assumptions, API outage, or a condition
that was never established.

Evidence expectations: the condition, condition evaluation, gate status, and
rendered evidence are explicit. Required gates cannot silently become
conditional after a failed run.

Interpretation: `pass` means the condition was true and evidence was captured.
`fail` means the condition was true but evidence failed. `blocked` means the
condition or target cannot be established. `not-evaluated` means the condition
was false or not applicable and that state was planned.
