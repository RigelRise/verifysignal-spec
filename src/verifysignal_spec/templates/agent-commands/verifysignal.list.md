# verifysignal.list

List use cases and workflow status.

- No product understanding prerequisite is required for this command.
- Start by running `verifysignal workflow check list --json` for a deterministic no-prerequisite status before listing.
- Use the installed `verifysignal` executable directly. Do not use `npx` or package-runner wrappers.
- Continue only when the result includes `requiredCapability: workflow.guardrails/v1` and `supported: true`.
- If `workflow check` is unavailable, unsupported, or exits with an invalid subcommand error, stop immediately and tell the developer to upgrade `verifysignal` and regenerate the agent integration.
- Use deterministic CLI commands such as `verifysignal list` and `verifysignal workflow list`.
- Do not write managed `.verifysignal/` artifacts directly. Persist managed artifacts through VerifySignal Spec CLI operations only.
- Summarize aliases with `lastRun` separate from `current` readiness. A historical passed run is not current readiness.
- Treat `current.status` as local metadata only, from a persisted readiness snapshot. Values: `ready`, `ready-credential-bound` (passed credentialed read — a trusted ceiling), `needs-rerun-confirmation` (passed committed write — confirm before the next run), `rerun-confirmed` (committed write the owner has superseded/approved), `needs-validate`, `stale`, `blocked`, `not-checked`.
- Render `current.presentation`, not the raw status, as the badge. `ceiling: true` is a use case that PASSED and sits at an inherent safety floor — render it as a calm lock (🔒, or 🔓 when `rerun-confirmed`) and NEVER as amber/yellow. Amber (`severity: attention`) is reserved for states a command can move; red (`severity: failed`) for `blocked`.
- A row carries a suggested command IF AND ONLY IF `current.nextAction` is set. Surface `current.nextAction` verbatim whenever present (covers `needs-validate`, `stale`, `blocked`, `not-checked`). For a ceiling/ready row `nextAction` is null by design — show `presentation.headline` and any `confirmHint`/`pendingCeilingNote` framed as "no action needed", and do NOT invent a command to "clear" a lock (the lock represents a real condition, not a defect).
- Group the output: rows that need attention (`severity` attention/failed, with a `nextAction`) first; ready and locked-ceiling rows after, muted as "no action needed". The summary line must not imply failure when no row needs attention.
- The normal list view must remain metadata-only. Do not call Core, network, credential, entitlement, target reachability, or browser checks from list.
- Include the compact row facts: alias, last run, current state, requirements, and risk.
- For credentialed rows, show credential group and required runtime names only; never show values.
- For write/external-notification rows, show side-effect class, cleanup policy, and confirmation/rerun risk when present.
- Show normalized readiness/risk labels rather than raw post-commit field names. A historical passed write run is not proof that a rerun will use a fresh resource identity.
- Do not inspect sensitive files.
- Surface the recommended next command for any row whose `current.nextAction` is set — including `blocked`, which now routes to re-validate.
