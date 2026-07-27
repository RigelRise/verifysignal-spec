# verifysignal.run

Run a validated use case by alias through the managed VerifySignal runtime.

- Start by running `verifysignal workflow check run --alias <alias> --json`.
- Prefer the public `verifysignal` CLI for user-facing commands. Do not use `npx` or package-runner wrappers.
- Continue only when the result includes `requiredCapability: workflow.guardrails/v1` and `supported: true`.
- If `workflow check` is unavailable, unsupported, or exits with an invalid subcommand error, stop immediately and tell the developer to upgrade `verifysignal` and regenerate the agent integration.
- If the check does not allow continuation, name the missing artifact or decision, point to `nextCommand`, and stop.
- If a Golden Path first run is blocked by target, credential, stale inventory, stale workspace, or Core compatibility, present a blocker stage card with the exact recovery command.
- Do not run against a target inferred by the agent. Require target confirmation
  for the current WorkflowRun and pass an approved test environment file only
  through explicit `--env-file`.
- If the managed runtime, API, entitlement receipt, or runtime download is blocked, classify it as runtime setup/security and route happy-path recovery to `verifysignal init --here --integration codex`; use `verifysignal core setup --core-cmd <path>` only for diagnostics, offline environments, and development overrides. Do not suggest `/verifysignal-repair` for missing runtime, token exchange, receipt, distribution, package verification, or Core entitlement rejection blockers.
- Do not perform stage-specific work until the check allows it.
- If `workflow check run` returns `recommendedAction: approve-rerun`, do not execute the browser run until the owner confirms the write rerun. Use `verifysignal workflow approve-rerun --alias <alias> --confirm-risk <confirmation-id> --json`, then re-check/run. Non-interactive run may use the same documented `--confirm-risk <confirmation-id>` token.
- Stale repository understanding is not automatically a global understand detour for an existing alias. Follow the check output: continue with warning, validate, refresh, or confirm based on impact and write risk.
- Resolve the alias to exactly one run request, main skill, and supporting reusable skills.
- Use parameter values already declared in the run request. Prompt only for runtime values that are still missing.
- Resolve generated runtime inputs during run preparation and keep the authored run request generic. Record only safe resolved values for that execution.
- Fresh generated write values preserve the seed plus a run-attempt token derived from the prepared run id; do not reuse deterministic alias-prefix tokens for refreshed write identities.
- Resolve `{{parameters.*}}` confirmation expected values before Core execution. Block missing, credential, unsupported, or secret-looking placeholders before browser execution instead of forwarding literal braces to Core.
- For write reruns with `allowed-with-new-inputs`, confirm the refreshed generated identity binding differs from locally recorded committed bindings for the same use case and target before Core execution. If it collides, stop and route to repair/implementation; do not run merely because the owner accepted write risk.
- Generated identity bindings are `prepared/committed/discarded`: preflight prepares the value, successful commit records it as committed, and pre-commit failure records it as discarded without publishing named outputs.
- Use `verifysignal workflow approve-rerun` for normal owner-approved reruns after a real committed write. Use `verifysignal workflow supersede-write-outcome --alias <alias> --payload <review.json> --json` only when reviewing/reclassifying a prior write outcome such as a false positive. Do not hand-edit `lastRun`, registry, readiness, or run-history state.
- For write and external-notification use cases, stop before Core execution when side-effect policy, local envelope, runtime output declarations, Core `sideEffectGuardrails`, or `rerunPolicy` are missing/unsupported.
- For legacy write/external-notification artifacts missing lifecycle or safety-capability metadata, require structured confirmation and show migration guidance. Missing Core side-effect envelope is never proof of no side effect.
- Never persist credential values.
- Do not write managed `.verifysignal/` artifacts directly. Persist managed artifacts through VerifySignal Spec CLI operations only.
- Delegate execution through `verifysignal run <alias> --profile normal` unless the user requests another profile. Use-case-specific profile names are allowed when declared by that use case; unknown profiles must block and list available profiles.
- For human-observable browser debugging, use `--profile debug`; the default debug pacing is `--slow-mo 900` unless the user explicitly overrides it.
- Report Core/browser status separately from Spec coverage status using `coreBrowserStatus` and `specCoverageStatus`. A Core `passed` result can still be `specCoverageStatus: incomplete` when planned gates are missing, network-only, screenshot-only, or unmapped.
- Backward-compatible summary wording may still mention that a Core `passed` result can still be `coverageStatus: incomplete`; interpret that as Spec coverage, not browser execution.
- When Core/browser execution fails, call Spec coverage diagnostic; do not summarize diagnostic coverage as browser validation passed.
- When public Core result fields show the commit step was reached, summarize the normalized side-effect/rerun assertion instead of enumerating every raw field name. Do not call it a safe pre-commit failure.
- When a write run completes without a structured Core side-effect envelope, report write activity as unknown or inferred from declared intent/evidence. Require cleanup, refreshed generated inputs, idempotency, or confirmation before rerun when risk is unknown.
- Include side-effect lifecycle status in the run summary: cleanup policy, whether cleanup is declared, safe resource refs when available, and manual/external cleanup instructions when declared.
- Do not summarize `status: incomplete` as passed, even when `coreStatus` is `passed`; name the missing required gates and next action.
- Use `runOutcomeSummary` as the primary source for the final user-facing run result. Fall back to top-level fields only when a key is absent from `runOutcomeSummary`.
- Render exactly one final run result section. Do not repeat the same run status, run id, profile, or gate coverage in multiple tables/sections.
- Do not build markdown tables from `gateCoverage`; summarize gate coverage in concise bullets using the already-computed `missingRequiredGates`, `partialCoverage`, `runtimeContradictions`, and `repairRecommendations` fields.
- Do not repeat gate coverage after the final run result section. If detailed gate diagnostics are needed, point to `reportPath` and `evidenceDir` instead of reconstructing report internals.
- Include selected main skill, profile settings, concise gate coverage status, and runtime contradiction recommendations in the run summary.
- For an accepted Golden Path first run, present the structured stage cards from output using clear separators, status marker, one-line summary, why it matters, primary evidence, repair details when present, and next action.
- Treat `firstRunStatus: passed` and `firstRunStatus: repaired-passed` with `strictPass: true` as Golden Path success. Treat `skipped`, `failed`, `blocked`, and `incomplete` as distinct non-success states.
- Record report and evidence references, not raw report internals.
- Suggest `/verifysignal-repair` when execution fails with deterministic artifact findings or when Spec coverage reports runtime contradictions or incomplete planned gates; runtime setup, API, entitlement, distribution, and package verification blockers should go to onboarding or diagnostic runtime setup.
- Never print or persist raw email addresses, email unlock tokens, signed download URLs, receipt payloads, credentials, browser storage, screenshots, source snapshots, or private runtime contents.
- Use `verifysignal workflow inspect-golden-path-state --json` when the first-run state appears stale or interrupted.
