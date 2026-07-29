# Golden Path Troubleshooting

Golden Path recovery should explain the blocker, show the strongest safe
evidence, and provide the exact next action without weakening validation intent.

## Common Blockers

- Missing understanding: run safe product understanding from an available
  repository or user-approved live URL and resume the original specify flow. Do not ask the
  user to restart manually unless the host cannot continue.
- Partial inventory: continue understanding with `--scope continue` or a focused
  scope, and keep the partial reason visible in recommendation output.
- Explicit acceptance required: no candidate met all ideal first-run criteria.
  Explain the missing criteria and proceed only after the user accepts the risk.
- Missing or unconfirmed target: confirm the suggested browser target or provide
  another one in clarify before planning, probing, or running. A URL inferred
  from repository start instructions remains a suggestion and must be confirmed
  again for each new WorkflowRun.
- Unreachable target: start the app or correct the target URL, then rerun the
  first-run recommendation.
- Unresolved credentials: inspect the exact declared environment keys. With
  owner approval, prepare a project-local file using `verifysignal credentials
  prepare <alias> --env-file .env.verifysignal.test.local`, fill it locally,
  and pass the same explicit `--env-file` to validate, probe, and run. Never
  source or implicitly read `.env`/`.env.local`, and never copy values into
  managed artifacts.
- Test environment file not ignored by Git: add the exact path to `.gitignore`
  or `.git/info/exclude`. VerifySignal warns before reading a file that Git
  would commit.
- Stale inventory or guidance: rerun product understanding or regenerate the
  agent integration.
- Managed runtime blocked: run `verifysignal init --here --integration codex` to
  complete email-token unlock and managed runtime acquisition. Use `verifysignal
  core setup --core-cmd <path>` only for diagnostics, offline environments, and
  development overrides.
- Incompatible Core: verify `verifysignal core version --json` and upgrade the
  component that is behind the public CLI JSON contract.
- Install guidance missing or stale: rerun `verifysignal-spec integration install
  <codex|claude>` or `verifysignal-spec integration upgrade` to regenerate local
  onboarding guidance.
- Blocked guided flow: inspect `.verifysignal/workflows/golden-path-state.yaml`
  and follow `resumeCommand`; do not infer a new stage from chat history.
- 009 workspace state compatibility: inspect/reset state through the public
  workflow commands below. Do not delete unrelated `.verifysignal/` artifacts.
- Write rerun blocked by resource identity: validate the use case, then repair
  or re-implement the generated identity input/template, `resourceIdentity`, or
  `rerunPolicy`. Do not hand-edit `lastRun` or registry state to bypass a
  write-safety guard.
- Write rerun requires owner confirmation after a committed write: run
  `verifysignal workflow approve-rerun --alias <alias> --confirm-risk <id> --json`
  using the confirmation id from `workflow check run`, then re-check/run.
- Reviewed false-positive write outcome: record an auditable review with
  `verifysignal workflow supersede-write-outcome`; do not hand-edit managed
  run history. Write policies should use `sideEffectPolicy.allowed[]` and
  `sideEffectPolicy.forbidden[]`, not legacy
  `sideEffectPolicy.rules[].effect/match`, and confirmation signals must be
  runtime-supported confirmation signals.
- Generated identity collision: the refreshed value repeated a locally recorded
  committed binding for the same use case and target. Adjust the generation
  strategy or owner-approved seed before rerunning. Fresh generated write values
  should preserve the seed plus a run-attempt token; no live target probe is
  required by default.
- Unresolved confirmation placeholder: confirmation expected values can use
  `{{parameters.<name>}}`, but Spec must resolve them before Core execution.
  Declare/provide the missing runtime parameter or route through
  clarify/plan/implement. Do not replace the blocker with a weaker literal or
  a credential placeholder.

## Workspace State

Use read-only inspection before cleanup:

```sh
verifysignal workflow inspect-golden-path-state --json
verifysignal workflow reset-golden-path-state --preview --json
verifysignal workflow reset-golden-path-state --confirm --json
```

Reset removes only Golden Path-owned state and preserves unrelated use cases,
run requests, skills, reports, repair sessions, registry records, and
user-authored files.

## Outcome Meanings

- `passed`: direct strict pass; first-run success.
- `repaired-passed`: safe repair, revalidation, rerun, and strict pass; also
  first-run success.
- `skipped`: the user declined Golden Path; manual selection continues.
- `blocked`: required runtime data, host permission, safety boundary, or runtime
  compatibility stopped automatic continuation.
- `failed` or `incomplete`: the first run did not prove all required gates; use
  repair or replan with clear product feedback.
