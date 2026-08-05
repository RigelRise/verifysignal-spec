# verifysignal.validate

Validate draft artifacts through VerifySignal and the managed VerifySignal Runtime.

- Start by running `verifysignal workflow check validate --alias <alias> --json`.
- Prefer the public `verifysignal` CLI for user-facing commands. Do not use `npx` or package-runner wrappers.
- Continue only when the result includes `requiredCapability: workflow.guardrails/v1` and `supported: true`.
- If `workflow check` is unavailable, unsupported, or exits with an invalid subcommand error, stop immediately and tell the developer to upgrade `verifysignal` and regenerate the agent integration.
- If the check does not allow continuation, name the missing artifact or decision, point to `nextCommand`, and stop.
- Do not perform stage-specific work until the check allows it.
- Treat `workflow check validate` as structural readiness only. A structural `status: ready` does not validate protected-runtime entitlement readiness and MUST NOT be reported as complete validation.
- Read `readinessScope`, `runtimeReadinessStatus`, and `runtimeReadinessCommand`; when the structural check is ready, follow its `nextAction` exactly before claiming runtime readiness.
- If validation is blocked during the Golden Path first run, present a blocker stage card with category, primary evidence, recovery command, and next action.
- Review `structuralValidation` before Core validation. If structural validation is blocked, report the exact finding and do not call Core.
- If recoverable migration plans are present, ask the developer before invoking `verifysignal workflow migrate --approve <migration-id> --json`.
- If the managed runtime or entitlement is missing or blocked, state that structural validation can still run, but a verified VerifySignal runtime plus valid entitlement receipt is required for complete validation and browser execution. Route happy-path recovery to `verifysignal init --here --integration codex`; use `verifysignal core setup --core-cmd <path>` only for diagnostics, offline environments, and development overrides. Do not suggest artifact repair for environment, API, distribution, token, receipt, or Core entitlement rejection blockers.
- Treat `api.*`, `entitlement.*`, `distribution.*`, `artifact.*`, `cache.*`, `platform.unsupported`, and `core.incompatible` readiness blockers as non-repairable runtime setup/security issues unless a later Core validation or run produces deterministic artifact findings.
- For `entitlement.key-unknown`, use that blocker's exact `recoveryCommand`;
  do not rerun `init`, `init --force`, or `core setup`. Those commands cannot
  make an unknown receipt key trusted and must not become a recovery loop.
- Treat `skill-execution.*` readiness blockers as execution-boundary issues: the run request exposes the wrong executable skill set for the current Core contract. Report the blocker and recovery command; do not suggest gate weakening.
- Do not print raw email addresses, email unlock tokens, signed download URLs, receipt payloads, credentials, local env-file values, screenshots, browser storage, source snapshots, or private runtime contents.
- Use shared CLI JSON and project-local `.verifysignal/` workspace state as the source of truth for current readiness, credential readiness hints, structured confirmation, cleanup lifecycle, and conservative side-effect envelope reporting.
- Backward-compatible wording may still state: "VerifySignal Core is required for the complete VerifySignal validation and browser execution experience"; interpret that as the private runtime boundary, not a manual happy-path install step.
- Delegate Core-dependent behavior through `verifysignal validate <alias> --runtime-readiness` .
- `runtime readiness verifies target resolution, target reachability, required runtime prerequisites, and Core authoring readiness` without executing the full browser validation flow.
- Validation writes a project-local readiness snapshot when it can evaluate the alias. The snapshot is advisory current-readiness metadata for list/run preflight; it is not browser execution.
- When credentials are missing, name the credential group and required runtime names only. If a credential readiness hint exists, show it as non-executable user guidance; do not read env files or execute the hint text.
- If the developer approved a prepared test environment file, pass it
  explicitly with `--env-file`. Do not look for `.env` or `.env.local`.
- For stale understanding, distinguish discovery/specification from alias-scoped validate/run. Alias-scoped checks should use warning, validation, or structured confirmation based on use-case impact rather than automatically forcing `/verifysignal-understand`.
- Treat validation output as static readiness: `authoredEvidenceCoverageStatus` means required gates have mapped authored evidence, and `fullBrowserFlowExecuted: false` means the browser flow has not run yet.
- Report the selected main skill shown by validation output before discussing Core results.
- For later browser inspection, remind users that `verifysignal run <alias> --profile debug` uses 900ms slow motion by default unless `--slow-mo` is explicitly set.
- Review `authoringCoherence`. If it is blocked, treat the artifact as not ready even if individual browser steps look executable.
- Review public Core `authoringWarnings`. The blocking guardrails `degenerate-text-target` and `unstable-generated-css-target` must block runtime readiness before browser navigation; fix the named target and rerun static validation instead of masking ambiguity with positional selection.
- Review execution-boundary guidance before Core validation. A reusable/source-only skill is not executable unless the public Core contract declares supported multi-skill roles, ordering, and evidence semantics.
- For write and external-notification use cases, treat missing `sideEffectGuardrails`, missing commit step, missing local envelope, missing `rerunPolicy`, unsupported confirmation signal types, and unsupported runtime output sources as readiness blockers.
- Treat `sideEffectPolicy.allowed[]` / `sideEffectPolicy.forbidden[]` as the runtime-compatible policy shape. `sideEffectPolicy.rules[].effect/match` is legacy compatibility input only; readiness must migrate it or block with guided owner choices before run.
- A runtime-supported confirmation must be proven by public capability data or accepted public runtime outcomes. If a real outcome reported `unsupported-confirmation-signal`, trust that over static authoring acceptance until newer capability data proves support.
- Resolve `{{parameters.*}}` confirmation expected values before Core execution. If a confirmation references a missing parameter, credential namespace, unsupported namespace, or secret-looking resolved value, report the exact finding and route through clarify/plan/implement instead of calling Core.
- For newly authored write and external-notification use cases, require persisted `resourceIdentity`. If identity is unclear, route back to clarify instead of relying on AI memory.
- Report the normalized `rerunDecision` when present; validation and run preflight must agree for the same workspace state.
- Reconcile the latest observed side-effect policy violation with the policy snapshot from that run. An unchanged or unavailable prior policy blocks readiness; an explicit owner policy change permits a new run only with a rerun-required warning. Static runtime readiness does not navigate the browser.
- Newly authored write and external-notification use cases require side-effect lifecycle declarations. Legacy artifacts without lifecycle or safety-capability metadata require conservative confirmation/migration guidance instead of optimistic readiness.
- Generated runtime inputs are resolved at run preparation, not during static validation; do not mark them missing merely because the authored run request does not persist a fixed value.
- Fresh generated write values use the authored seed plus a run-attempt token when rerun policy requires new inputs; repeated committed values should block with guided recovery rather than requiring manual run-history edits.
- Distinguish coherent planned validation from a narrow technical pass. A page-view validation requires mapped rendered-result UI evidence and declared backend checks, not only navigation or HTTP 200.
- Preserve Core verdicts exactly and do not reinterpret passed, failed, blocked, or error outcomes.
- Record redacted validation summaries in workflow state and stage documents.
- Do not write managed `.verifysignal/` artifacts directly. Persist managed artifacts through VerifySignal CLI operations only.
- Do not use `verifysignal author`, nonexistent schema/scaffold commands, or manual file edits to repair workflow-managed artifacts. Route schema fixes through `/verifysignal-repair` or `verifysignal workflow persist implement`.
- Do not parse raw report internals or import private VerifySignal Core packages.
- Suggest `/verifysignal-run` when readiness passes or `/verifysignal-repair` only when actionable artifact/runtime findings exist.
