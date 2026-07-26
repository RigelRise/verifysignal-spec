# verifysignal.specify

Define one browser validation use case before artifact planning.

- Start by running `verifysignal workflow check specify --json`.
- Before constructing the payload, read the public workflow contract with `verifysignal workflow info verifysignal-use-case --json` and use `stagePayloadContracts.specify` as the source of truth. Do not inspect installed package source to infer payload schemas.
- Use the installed `verifysignal` executable directly. Do not use `npx` or package-runner wrappers.
- Continue only when the result includes `requiredCapability: workflow.guardrails/v1` and `supported: true`.
- If `workflow check` is unavailable, unsupported, or exits with an invalid subcommand error, stop immediately and tell the developer to upgrade `verifysignal` and regenerate the agent integration. Regenerate the agent integration after upgrading. Do not fall back to `verifysignal check`, directory listing, repository inspection, or use-case questions.
- product understanding is required before use case specification can be grounded.
- If the check returns `missing` with `recommendedAction: auto-prepare-understanding`, treat it as the Golden Path onboarding auto-prepare path, not as a terminal blocker.
- For missing understanding, state that safe product understanding will inspect an available repository or a user-approved live URL without persisting secrets, give an approximate time expectation, run the understand workflow, and then resume the original specify flow without requiring the user to manually restart `/verifysignal-specify`.
- Use `onboardingPreparation.nextCommand`, `onboardingPreparation.resumeCommand`, `resumeCommand`, and `stageCards` from the check result as the source of truth for the next action. Ask once only when the result says host permissions or sensitive boundaries require approval.
- If auto-prepare succeeds, return to first-run recommendation in the same conversation instead of asking the developer to invoke `/verifysignal-specify` again.
- Do not ask for alias, target behavior, expected outcome, run request details, or skill details while product understanding is missing.
- If the check returns `stale`, explain the stale reason from the result and why refresh is important for accurate run requests and skills.
- When stale refresh is accepted, run `verifysignal workflow check specify --refresh-decision accepted --json`, route through `/verifysignal-understand`, then return to candidate selection.
- When stale refresh is declined, run `verifysignal workflow check specify --refresh-decision declined --json` and continue with the stale-context warning.
- When the check returns `ready`, immediately run `verifysignal workflow recommend-first-run --json` and use that response as the product-owned first-run recommendation source of truth.
- Do not present candidateUseCases or recommendedCandidate from workflow check as the product-owned first-run recommendation; those fields are inventory context only. The first recommendation must come from `workflow recommend-first-run`.
- Present the project overview, the recommended first-run candidate from `workflow recommend-first-run`, branchRelevantCandidates separately, and then other candidate validation use cases before asking what to specify.
- Prefer the product-owned real-target first-run recommendation when the developer is new to the project. Canonical examples may be mentioned as learning aids after that recommendation, not as fake/demo fallbacks.
- If the coverage inventory is `partial`, state that more scenarios may exist and offer `/verifysignal-understand` with `--scope continue` or a focused scope before listing speculative additions.
- If the coverage inventory is `complete`, list additional scenarios from inventory when the developer asks for more.
- Let the developer choose a candidate or provide a custom use case.
- Record exactly one validation intent with alias, purpose, target surface, expected outcome, runtime assumptions, acceptance scenarios, and unresolved questions.
- Record `sideEffects.class` explicitly. Use `none` for read-only, `authenticated-read` for authenticated non-mutating checks, `write` for product-state mutations, `external-notification` for external messages, and `unknown` only as a clarify blocker.
- For write/external-notification intent, plan canonical side-effect policy only: `sideEffectPolicy.allowed[]` and `sideEffectPolicy.forbidden[]`. Do not author `sideEffectPolicy.rules[].effect/match`; that legacy shape is compatibility input only and must be migrated or blocked with owner choices.
- Do not try to categorize every possible action globally. Classify the selected use case and record unresolved uncertainty instead of guessing.
- For write/external-notification candidates, record resource identity when it is obvious with high confidence; otherwise leave a bounded clarification item. Resource identity is use-case-specific and must not rely on hard-coded field names.
- Browser validation use cases require a resolved target application environment before executable planning. If the target URL, local start command, or equivalent browser target is not known, record it as a high-impact unresolved question and route to `/verifysignal-clarify`.
- If the request contains multiple behaviors, split or ask for clarification before planning.
- Do not write managed `.verifysignal/` artifacts directly. Persist managed artifacts through `verifysignal workflow persist specify --alias <alias> --payload <payload.json> --json`.
- Keep the use case mapped to exactly one future run request.
- Do not create run request or skill files in this stage.
- Suggest `/verifysignal-clarify` as the next command when high-impact unknowns remain.
