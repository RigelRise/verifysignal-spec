# verifysignal.understand

Capture safe product understanding from a repository, a live URL without source
access, or both before authoring run requests.

## Public Contract Gate

- No prior product understanding is required for this command.
- Start by running `verifysignal workflow check understand --json` to verify
  that the installed CLI supports the current workflow contract.
- Use the installed `verifysignal` executable directly. Do not use `npx` or package-runner wrappers.
- Continue only when the result includes
  `requiredCapability: workflow.guardrails/v1` and `supported: true`.
- Then run `verifysignal workflow info verifysignal-use-case --json`. Use
  `stagePayloadContracts.byStage.understand` as the public payload contract.
  Browser-first work additionally requires advertised capability
  `browser-first-understanding/v1`.
- If `workflow check` or the required workflow information is unavailable,
  unsupported, or exits with an invalid subcommand error, stop immediately and
  tell the developer to upgrade `verifysignal` and regenerate the agent integration. Do not inspect the repository or browse the product with an unknown CLI contract, and do not write
  `.verifysignal/product-context.yaml` directly.

## Choose the Understanding Mode

- Treat `/verifysignal-understand --url <url>` as `browser-first`. The user may
  simply provide a URL conversationally; do not require them to know this
  syntax.
- Use `repository` when source is available and no live mapping was requested.
- Use `hybrid` when both safe repository context and browser observations are
  available. Preserve whether each signal came from `repository`, `browser`, or
  `hybrid` provenance, and record conflicts as gaps.
- This command may run for the initial understanding pass or after an accepted
  stale-understanding refresh.
- Work in the target repository for repository/hybrid mode. For browser-first,
  an empty local engagement directory is valid even when it has no `.git/`.
- Keep generated docs, workflow prompts, run requests, and skills in English.
  Use pt-BR only for conversation with the product owner when appropriate.
- Use `.verifysignal/` as the only durable workspace.

## Browser-First Mapping

- Use Playwright MCP or an equivalent host browser/Playwright interface. This
  exploratory browser is not the deterministic validator; documented public
  Core `discover`, `probe`, and `run` operations remain authoritative.
- Open a headed browser. Use human-observable pacing: wait about 700 ms between
  meaningful actions and pause after each navigation so the user can follow.
- Default to one same-origin scope, at most 20 meaningful pages or states,
  depth 3, three to five candidate journeys, and a 15-minute soft budget. Honor
  a narrower user scope. Follow an additional origin only after explicit scope
  approval.
- Prefer user-facing routes/states, then flows, forms, permissions,
  loading/empty/error states, and integrations. Stop at the budget and report
  partial understanding rather than implying whole-product coverage.
- Do not activate mutating, transactional, destructive, or unknown-safety
  controls during mapping. Record each skipped control and inaccessible state
  as a gap.
- Assisted authentication is the default. Navigate to login in the headed
  browser, ask the user to enter credentials directly, and wait until the user
  explicitly confirms that login is complete. Never ask for credential values
  in chat. A non-assisted approach is allowed only when the user requests it
  and the host can keep secret values out of durable state.
- After login, resume only within the approved origins and scope. If
  authentication expires, pause for the user instead of attempting to recover
  secret material.
- Summarize the mapped surfaces, gaps, and candidate journeys, then keep the browser open until the user acknowledges the summary or explicitly asks you
  to close it.

## Safe Durable Understanding

- Persist only synthesized structured product signals: stable id, kind,
  surface/state, short user-visible evidence summary, provenance, observed
  time, confidence, and inventory references.
- Never persist or print credentials, authorization material, cookies, local or session storage, storage state, entered form values, raw query values, raw DOM/HTML, MCP snapshots, screenshots, traces/HAR, headers, response bodies, or provider-specific browser captures.
- Strip URL fragments and query values from durable target locators.
- Prepare `understandingMode`, product/repository summary, sanitized target
  environment, exploration scope, product signals, coverage inventory,
  candidate use cases, provenance status, generated/observed time, and gaps.
- Keep the existing coverage inventory as the downstream bridge.
  `sourceInventoryItems` refers to inventory item ids even when the item was
  observed in the browser.
- Produce three to five candidate journeys when that many are safely observable.
  If fewer are observable, persist a `partial` inventory with explicit reasons;
  never fabricate a candidate. Describe this explicitly as a partial inventory.
- Do not write managed `.verifysignal/` artifacts directly. Persist through:
  `verifysignal workflow persist understand --scope <scope> --payload
  <payload.json> --json`.

## Repository and Scoped Passes

- Avoid sensitive files by default and ask before reading local environment or
  secret-bearing configuration.
- Build a systematic inventory of discoverable user-facing source surfaces.
  Enumerate trivial public/read-only candidates before branch-heavy,
  authenticated, write-heavy, tokenized, billing, upload, or rare-data flows.
- Support `--scope all`, `--scope changed`, `--scope continue`,
  `--scope route:<path>`, and `--scope area:<name>`.
- Mark repository inventory complete only when every discoverable user-facing
  surface in scope is covered or explicitly excluded. Otherwise record
  `partialInventoryReasons`; mark affected areas stale after repository changes.
- Preserve a Git hash or explicit Git-unavailable reason for repository/hybrid
  provenance. Browser-first freshness is age-based and does not require Git.

## Candidate Review and Proof Boundary

- Present the ranked candidates and ask the user to select one journey for
  proof. Do not auto-select a potentially mutating journey.
- A read-only selection may continue through the public
  specify/plan/tasks/implement/validate/run workflow.
- Before any potentially mutating proof, run
  `verifysignal core version --json`. Continue only when `data.operations`
  contains an operation with `name: probe`, `schema:
  verifysignal.probe/v1`, and `schemaVersion: 1`. If it does not, preserve the
  candidate and report the missing Core capability.
- If the selected journey may write or notify an external system, require
  explicit confirmation and exact public `verifysignal.probe/v1` support. Use
  `verifysignal probe <run-request> --skill <main-skill> --json`; probe must not commit and probe success does not authorize a normal run.
- If browser capability, authentication, target reachability, or public Core
  capability is missing, preserve the candidate and report the exact
  partial/blocked prerequisite. Do not claim proof.
- Report whether understanding is complete, partial, stale, or blocked before
  recommending scenarios. Suggest `/verifysignal-specify` after the user
  selects a sufficiently grounded candidate.
