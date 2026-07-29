# verifysignal.clarify

Resolve only high-impact unknowns before planning.

- Start by running `verifysignal workflow check clarify --alias <alias> --json`.
- Before constructing the payload, read the public workflow contract with `verifysignal workflow info verifysignal-use-case --json` and use `stagePayloadContracts.clarify` as the source of truth. Do not inspect installed package source to infer payload schemas.
- Use the installed `verifysignal` executable directly. Do not use `npx` or package-runner wrappers.
- Continue only when the result includes `requiredCapability: workflow.guardrails/v1` and `supported: true`.
- If `workflow check` is unavailable, unsupported, or exits with an invalid subcommand error, stop immediately and tell the developer to upgrade `verifysignal` and regenerate the agent integration. Regenerate the agent integration after upgrading.
- If the check does not allow continuation, name the missing artifact or decision, point to `nextCommand`, and stop.
- Do not perform stage-specific work until the check allows it.
- Ask focused questions only when missing information materially affects scope, runtime requirements, security, or user-visible validation behavior.
- For write/external-notification uncertainty, clarify only non-secret structure: side-effect class, commit step, allowed local envelope, resource identity, collision policy, runtime output names/sources, rerun policy, and whether generated inputs are needed.
- Clarify expected mutating requests as canonical `sideEffectPolicy.allowed[]` / `sideEffectPolicy.forbidden[]` entries. Do not author `sideEffectPolicy.rules[].effect/match`; if legacy/canonical policy conflicts, guide the owner to keep canonical, migrate legacy, or choose explicitly.
- Resource identity questions should ask which use-case-owned input or post-commit binding identifies the created/affected resource. Do not ask for credentials or fixed secret-bearing values.
- For write/external-notification behavior, clarify side-effect lifecycle before planning or implementation: cleanup policy (`none`, `manual`, `automated`, `external`), cleanup requiredness, tracking intent, and manual/external cleanup instructions when applicable.
- For credentialed use cases, capture optional credential readiness hints only as non-secret user-managed guidance. Hints may name env vars or secret-manager wrappers, but must not include `KEY=value`, credential values, or file contents.
- If `sideEffects.class` is `unknown` or credentials/data/side-effect ownership is unresolved, block planning instead of drafting executable artifacts.
- For each high-impact clarification, include the question plus one or two context sentences explaining why it affects the run request, skill design, data setup, credential context, permissions, or expected outcome.
- Environment-dependent questions about seed data, runtime configuration, external services, credential groups, permissions, or expected outcome must remain pending unless the developer confirms a non-secret answer.
- A repository URL, local start command, previous workflow target, or URL copied
  by the agent is a recommendation, not a decision. Always present the
  recommended target and allow the developer to confirm or replace it. Persist
  browser target confirmation with `direct-user` or `explicit-command`
  provenance for the current WorkflowRun only.
- Do not write managed `.verifysignal/` artifacts directly. Persist managed artifacts through `verifysignal workflow persist clarify --alias <alias> --payload <payload.json> --json`.
- Do not ask for credential values. Ask for credential group names or environment variable names only.
- When exact declared credential keys are missing, ask permission before
  offering `verifysignal credentials prepare <alias> --env-file
  .env.verifysignal.test.local --json`. Never suggest sourcing `.env.local`.
- Block planning when unresolved clarification items would change the run request or reusable skill structure.
- Suggest `/verifysignal-plan` after clarification is sufficient.
