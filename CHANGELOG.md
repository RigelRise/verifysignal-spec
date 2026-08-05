# Changelog

## 0.24.0 - 2026-08-05

- Bumped VerifySignal Spec to `0.24.0`.

## 0.23.4 - 2026-08-04

- Bumped VerifySignal Spec to `0.23.4`.

## 0.23.3 - 2026-08-04

- Bumped VerifySignal Spec to `0.23.3`.

## 0.23.2 - 2026-08-04

- Bumped VerifySignal Spec to `0.23.2`.

## 0.23.1 - 2026-08-04

- Bumped VerifySignal Spec to `0.23.1`.

## 0.23.0 - 2026-08-04

- Bumped VerifySignal Spec to `0.23.0`.

## 0.22.1 - 2026-08-04

- Bumped VerifySignal Spec to `0.22.1`.

## 0.22.0 - 2026-07-30

### Embedded release-anchor acceptance

- Added `scripts/ci/install_with_embedded_anchor.py`: a clean-machine
  acceptance leg that installs a real signed Core release trusting only the
  production key embedded in this package (all release-trust environment
  variables are refused). Core's release workflow runs it on every release to
  prove the signing secret corresponds to the shipped anchor.
- Documented the embedded release trust anchor and its additive-only
  environment override in the installation guide.
- Bumped VerifySignal Spec to `0.22.0`.

## 0.21.6 - 2026-07-30

### Hermetic Core update and test readiness

- Added `core reset` and `core update`: updates remove local Core selection,
  resolve the backend's latest verified managed runtime, and report any verified
  managed fallback without silently reusing environment, `PATH`, or sibling
  checkouts.
- Made integration regeneration independent from Core discovery or execution.
- Added a current-WorkflowRun browser target confirmation gate. Repository URLs
  are suggestions until the user confirms or replaces them.
- Added `credentials prepare` and explicit `--env-file` support for validate,
  probe, and run, with declared-key allowlisting, strict non-executable parsing,
  owner-only permissions, and verified Git exclusion.
- Warned through `credentialWarnings` when an explicit `--env-file` is tracked
  by Git or is not ignored by it. Preparation still refuses to create a file it
  cannot exclude; reading an owner-selected file warns instead of blocking.
- Updated agent guidance and the identity-neutral authenticated-project dogfood
  to prove the complete managed-update, target-confirmation, credential,
  zero-resource probe, and single-resource run sequence.
- Bumped VerifySignal Spec to `0.21.6`; no VerifySignal Core change is required.

### Browser-first product understanding

- Added `browser-first-understanding/v1` with repository, browser-first, and
  hybrid modes so product understanding can start from a live URL without
  source or Git access.
- Added secret-safe URL, signal, inventory, provenance, freshness, and
  persistence rules while preserving existing repository workspaces without a
  migration.
- Updated the shared Codex and Claude workflow guidance for headed assisted
  login, bounded read-safe mapping, candidate review, and public Core probe-only
  handling for potentially mutating proof.
- Bumped the package from `0.20.0` to `0.21.0`.

### Codex browser and invocation parity

- Added user-scoped Playwright MCP setup through the public Codex and Claude
  MCP commands, plus a project-scoped compatibility fallback with
  comment-preserving merge, safe handling of existing configuration,
  install/upgrade support, and preservation of the workspace's selected
  default integration.
- Rendered Codex skills and public workflow guidance with `$verifysignal-*`
  while preserving Claude Code's `/verifysignal-*` syntax and normalizing
  legacy Codex responses without rewriting historical workflow documents.
- Hardened browser-first persistence with a complete public payload schema,
  bounded aliases, field-path diagnostics, cross-reference validation, and
  atomic rejection of lossy or unknown payloads.
- Added explicit candidate grounding and authoritative side-effect scoring,
  stable ranked handoff, inventory-only acceptance, and staged
  integration-native `specify` continuation.
- Routed managed Playwright MCP configuration through a pinned isolated
  launcher with private temporary output and cleanup across normal, failure,
  interrupt, and termination paths while preserving user-owned configuration.
- Fixed a Codex P0 where the configured MCP disappeared when `npx` could not
  reach the registry during agent startup: integration setup now installs the
  pinned provider into a private versioned user cache, the stdio launcher is
  offline-only, and PR CI requires a real MCP `initialize` plus `tools/list`
  handshake exposing browser navigation and snapshot tools.
- Made the managed Codex Playwright project fallback required and added a real
  clean-user Codex app-server acceptance that proves session discovery of
  navigation, snapshot, and click tools without a model turn, project trust,
  or a configuration override.
- Prevented an empty Codex Browser Plugin/in-app inventory from masking an
  already loaded project Playwright MCP; browser-first guidance now resolves
  the MCP first and recommends setup/restart only after both inventories fail.
- Fixed clean-project startup for both Codex and Claude by registering the
  managed Playwright launcher in agent user scope through each agent's public
  MCP command. PR acceptance now starts Codex without trust/config overrides
  and discovers the Claude entry from a second clean project.
- Made integration install and upgrade fail closed when user-scope MCP
  registration is blocked, instead of returning a successful exit code with a
  browser that the next plain agent session cannot discover.
- Prevented pre-observation host browser failures from being persisted as
  product understanding, made missing workflow prerequisites explicit
  blockers, and added actionable payload enum/`--stdin` diagnostics.
- Added structured JSON permission failures and prevented
  `entitlement.key-unknown` from entering init/Core-setup recovery loops.
- Prevented interactive initialization from requesting or exchanging an unlock
  token after email delivery failed or was throttled; accepted delivery now
  explains that Enter preserves the pending state when the token did not arrive.
- Isolated managed runtime receipts, verification keys, and installed packages
  by entitlement API endpoint so a production cache cannot satisfy or poison a
  local/staging initialization. The production cache layout and explicit cache
  override remain backward compatible.
- Added a manual-smoke RED/GREEN regression matrix covering every defect
  observed while validating this pull request.
- Made structural validation scope explicit and separated it from protected
  runtime and entitlement readiness.
- Bumped the package from `0.21.0` to `0.21.1`.
- Bumped the package from `0.21.1` to `0.21.2`.
- Fixed managed-runtime reuse after initialization so `core version`, workflow
  contract discovery, and browser authoring resolve the endpoint-isolated
  cached Core instead of recursively invoking the public Spec CLI.
- Bumped the package from `0.21.2` to `0.21.3`.
- Prevented Spec from injecting cached development/test verification keys into
  packaged runtimes. Managed stable runtimes now use their packaged trust
  material, while source-checkout development retains the existing environment
  handoff.
- Materialized Core-required side-effect policy modes in generated run
  requests: read-only classes default to `observe`, while write and external
  notification classes default to `enforce`.
- Bumped the package from `0.21.3` to `0.21.4`.
- Made Core-advertised degenerate-text and generated-CSS authoring warnings
  block runtime readiness before browser navigation while keeping validation
  static.
- Preserved side-effect-policy attribution across run, validation, first-run,
  and repair: a violation fails the Spec result, an unchanged policy blocks a
  rerun, an explicit owner policy change requires a clean rerun, and repair
  never auto-whitelists observed traffic.
- Added a full regression lifecycle for the manual failure: violation, blocked
  unchanged rerun, explicit policy review, clean rerun, and strict pass.
- Bumped the package from `0.21.4` to `0.21.5`.

### Open-source presentation and packaging

- Rewrote the README to be concise and terminal-first: the real hexagon brand
  mark, badges, an ASCII architecture, an open-core boundary table, and safety
  and "what it is not" sections.
- Added community-health files: `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`,
  `SECURITY.md`, `GOVERNANCE.md`, `CODEOWNERS`, issue and PR templates, and
  Dependabot.
- Added an `examples/` directory with two use cases and their `qa-report/v1`
  evidence (a read-only golden path and a write flow), guarded by a contract test.
- Made the package PyPI-ready (`[project.urls]`, classifiers, keywords) plus a
  Trusted-Publishing release workflow and a version-consistency test.
- Added brand assets under `docs/assets/`, a documentation index, and a
  `ROADMAP.md`.
- No changes to CLI behavior, schemas, templates, or the public Core contract.

## 0.19.0 - 2026-07-13

- Absorbed Core's new experimental crystallization capability, contract-first and
  additively, following the `discover` (feature 016) precedent:
  - Added `CoreAdapter.crystallize(run_dir, out=..., entitlement_receipt=...)`
    for Core's entitlement-protected `crystallize` operation
    (`verifysignal.crystallize/v1`).
  - Added `record`/`replay` parameters to `CoreAdapter.run()` (`run` stays on
    `verifysignal.run/v1`; the flags are additive).
  - Added `core_supports_crystallize()` optional-capability probe; `crystallize`
    is intentionally NOT part of `REQUIRED_OPERATIONS`, so an older Core without
    it stays compatible.

## 0.10.2 - 2026-06-08

- Fixed Core public contract projection for the current `data.sections` shape:
  network match keys now come from `awaitNetwork.match.keys`, field descriptors
  prefer `path`, artifact schema versions are projected separately from section
  schema versions, credential sources come from `credentialRefs.supportedSources`,
  and browser target composition follows Core-declared metadata.
- Added compatibility findings for divergent canonical and legacy contract
  shapes while keeping canonical Core metadata authoritative.

## 0.10.1 - 2026-06-07

- Fixed implement persistence and authoring coherence checks to use the Core
  public browser contract when validating executable browser intent and network
  evidence.

## 0.10.0 - 2026-06-06

- Added Core public contract driven authoring for run requests, browser skills,
  credential references, report coverage interpretation, and agent guidance.
- Added fail-closed blockers for missing or malformed Core executable contract
  sections and legacy executable artifact schemas.
- Kept Core contract projections ephemeral per command; no Core contract
  snapshots are persisted into target `.verifysignal/` workspaces.
