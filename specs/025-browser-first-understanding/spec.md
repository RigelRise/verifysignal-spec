# Feature Specification: Browser-First Product Understanding

**Feature Branch**: `025-browser-first-understanding`
**Created**: 2026-07-26
**Status**: Draft
**Input**: User description: "Add browser-first understanding from a live URL without customer source access."

## Constitution Alignment *(mandatory)*

- **Public Core boundary**: Browser exploration produces portable understanding inputs, while deterministic validation continues to use only the documented `verifysignal`/`proofsignal` public CLI surface. The feature does not import VerifySignal Core or depend on private Core internals.
- **Project-local workspace portability**: A browser-first engagement can be initialized in any local directory, including a directory that is not a Git repository. Durable state remains under `.verifysignal/` and can be inspected or moved independently of an agent integration.
- **Secret safety**: Authentication is completed by the user in a visible browser. Persisted understanding excludes credentials, cookies, storage state, query secrets, raw DOM, browser snapshots, screenshots, traces, response bodies, and entered form values.
- **Agent-neutral interface**: The understand-stage contract and persisted browser evidence are integration-neutral. Agent templates guide the experience, but the same contract can be invoked through the public CLI and implemented by any capable browser host.
- **Testable delivery**: Unit and integration tests cover URL safety, browser-first persistence, compatibility with repository understanding, public workflow contracts, readiness, and deterministic handoff to public Core commands.

## Clarifications

### Session 2026-07-26

- Q: Is browser-first understanding a replacement for repository understanding? → A: No. The product supports `repository`, `browser-first`, and `hybrid` understanding modes.
- Q: How much of the live application should v1 map? → A: Produce three to five candidate journeys within a bounded, same-origin exploration and prove one user-approved journey when safe prerequisites are available.
- Q: How should authentication work? → A: Assisted login is the default: open a headed browser, let the user authenticate directly, wait for explicit completion, and keep the browser visible until the user acknowledges the summary.
- Q: Can exploration mutate customer data? → A: Mapping is read-safe. Potentially mutating proof is allowed only after explicit confirmation and only through the public Core probe boundary, which must not commit the write.
- Q: Where does browser automation live? → A: The host integration performs exploration through Playwright MCP or an equivalent browser/Playwright interface; VerifySignal Spec owns the portable contract and durable synthesized evidence.

### Session 2026-07-27

- Q: How is the required headed browser made available in Codex? → A: Codex installation and upgrade prepare the pinned provider and register the VerifySignal-managed Playwright MCP in the agent's user scope through the agent's public MCP command. The project-scoped entry remains as a backward-compatible fallback, but a fresh session MUST NOT depend on project trust to discover the managed browser.
- Q: How are generated VerifySignal skills invoked in each supported agent? → A: Codex guidance and public workflow responses use `$verifysignal-*`; Claude Code guidance and responses continue to use `/verifysignal-*`.
- Q: How are existing Codex workspaces handled? → A: `integration upgrade` refreshes managed guidance and project MCP configuration. Existing historical workflow documents are not rewritten, but user-facing responses normalize legacy slash-prefixed commands to Codex's dollar-prefixed syntax.
- Q: Does integration upgrade change the workspace's selected agent? → A: No. Upgrade preserves the current default integration while refreshing its managed files and MCP configuration.
- Q: How are intuitive but non-canonical browser payload fields handled? → A: The public contract documents a bounded alias set. Aliases normalize losslessly, canonical/alias conflicts fail, and all other unknown or missing fields fail atomically with actionable paths.
- Q: How is an observed surface distinguished from an observed journey? → A: Browser candidates carry an explicit grounding status. A multi-surface observed journey requires a referenced transition signal; direct navigation proves only the destination surface.
- Q: Which component owns first-run ordering? → A: `workflow recommend-first-run` is the sole ranking authority. Agent guidance presents its ranked result unchanged and selection resumes through the staged specify workflow.
- Q: How are Playwright MCP artifacts kept out of the target project? → A: Managed integrations invoke a VerifySignal-owned stdio launcher that runs a pinned MCP in an isolated private temporary working directory and removes it on termination.

### Session 2026-07-28

- Q: What happens when Core browser execution passes but observes a side-effect policy violation? → A: The Spec run fails, preserves the policy snapshot and violation attribution, and does not grant Golden Path strict pass.
- Q: May repair automatically whitelist the observed request? → A: No. An unchanged or unknown prior policy blocks rerun; only an explicit owner policy change permits a new attempt, and only a later clean run restores strict pass.
- Q: Should static runtime readiness execute browser navigation to discover selector ambiguity? → A: No. It consumes Core's public authoring warnings and blocks on the categories Core advertises as blocking before browser navigation.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Map a Live Product Without Source Access (Priority: P1)

A product owner gives VerifySignal a live application URL in an empty local engagement directory. VerifySignal opens the product in a visible browser, explores a bounded set of read-safe pages and states, and creates durable product understanding with three to five candidate validation journeys, evidence provenance, and any observed coverage gaps.

**Why this priority**: This removes repository access as a prerequisite for identifying useful validation targets and is the minimum independently valuable browser-first outcome.

**Independent Test**: Initialize an engagement outside a Git repository, persist a valid browser-first understanding payload for a local fixture application, and verify that the workspace reports current understanding and ranked candidate journeys without any source files.

**Acceptance Scenarios**:

1. **Given** an empty non-Git directory and a reachable HTTP(S) URL, **When** the user asks VerifySignal to understand the product from that URL, **Then** it creates project-local browser-first understanding containing a product summary, target environment, bounded exploration scope, synthesized product signals, coverage inventory, three to five ranked candidate journeys when that many are observable, and explicit gaps.
2. **Given** an application with fewer than three safely observable journeys, **When** exploration reaches its scope or time limit, **Then** VerifySignal records a partial result and the limiting gaps instead of fabricating additional journeys.
3. **Given** a URL containing a fragment or sensitive-looking query parameters, **When** understanding is persisted, **Then** the durable target locator omits the fragment and query values while retaining enough origin and path context to identify the target.

---

### User Story 2 - Prove One Approved Journey Safely (Priority: P2)

After reviewing the candidate journeys, the user selects one journey to prove. VerifySignal gathers any missing runtime context conversationally, uses the public Core workflow for deterministic execution, and returns evidence without silently committing a write.

**Why this priority**: Mapping becomes operationally useful when it hands off one concrete behavior to VerifySignal's deterministic proof loop.

**Independent Test**: Select a read-only candidate in the browser-first fixture, generate the portable validation assets, execute the documented public Core command, and observe a recorded pass/fail result tied back to the selected candidate.

**Acceptance Scenarios**:

1. **Given** current browser-first understanding and a selected read-only candidate, **When** the user approves proof, **Then** VerifySignal prepares and runs the candidate through documented Core CLI operations and records deterministic evidence.
2. **Given** a selected candidate that may mutate application state, **When** the user has not explicitly confirmed a probe, **Then** VerifySignal does not execute the mutation and explains the required approval.
3. **Given** a confirmed potentially mutating candidate, **When** the public Core probe capability is available, **Then** VerifySignal uses the probe boundary and reports pre-commit evidence without committing the write.
4. **Given** missing credentials, unreachable runtime state, or an unavailable public Core capability, **When** proof is requested, **Then** VerifySignal preserves the candidate and reports the exact blocked prerequisite without claiming proof.

---

### User Story 3 - Preserve Repository and Agent Portability (Priority: P3)

Existing users continue to understand products from repositories, while users with both source and a live environment can combine repository and browser evidence. The same durable contract works across supported agent integrations.

**Why this priority**: Browser-first adoption must not regress the established repository workflow or make durable state dependent on one AI host.

**Independent Test**: Run the existing repository-understanding test suite unchanged, persist a hybrid payload, and validate the same browser-first workspace with at least two integration adapters or directly through the public workflow persistence command.

**Acceptance Scenarios**:

1. **Given** an existing repository-understanding workspace, **When** the feature is upgraded, **Then** its current product context and coverage inventory remain valid without migration.
2. **Given** repository and browser observations for the same product, **When** hybrid understanding is persisted, **Then** provenance distinguishes source-derived and browser-observed evidence while candidates can reference both.
3. **Given** an agent integration that cannot supply a browser capability, **When** browser-first understanding is requested, **Then** the integration reports the missing capability and leaves portable workspace state valid.

### Edge Cases

- The initial URL is unreachable, redirects outside the approved origin, uses an unsupported scheme, or resolves to a login loop.
- Authentication expires during exploration, multi-factor authentication requires repeated user action, or the user declines to log in.
- Navigation exposes destructive controls, downloads, cross-origin payment or identity providers, infinite scrolling, or cyclic routes.
- The scope limit, depth limit, candidate limit, or soft time budget is reached before enough journeys are observed.
- The application has no stable accessible names, changes URLs only through client-side state, or reuses one route for multiple materially different states.
- Browser observations conflict with repository evidence in hybrid mode.
- The Core installed on the machine lacks the required public probe capability.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST support `repository`, `browser-first`, and `hybrid` product-understanding modes and preserve `repository` as the compatible default for existing workspaces.
- **FR-002**: A browser-first workspace MUST be usable from a project-local directory that is not a Git repository and MUST keep durable state under `.verifysignal/`.
- **FR-003**: The understand workflow MUST accept an HTTP(S) target URL through a public, integration-neutral stage contract; supported agents MUST also guide users conversationally so they do not need to know the argument syntax.
- **FR-004**: Browser-first exploration MUST be bounded by an explicit scope containing allowed origins, maximum meaningful pages or states, maximum navigation depth, desired candidate range, and a soft time budget.
- **FR-005**: Unless overridden by the user, the scope MUST allow one origin, at most 20 meaningful pages or states, depth 3, three to five candidate journeys, and a 15-minute soft budget.
- **FR-006**: Mapping MUST restrict navigation to approved origins and MUST NOT activate controls that are destructive, transactional, state-changing, or of unknown safety.
- **FR-007**: The system MUST record skipped controls, inaccessible states, scope limits, authentication boundaries, and other material gaps.
- **FR-008**: Authentication MUST default to an assisted headed-browser flow in which the user enters credentials directly, explicitly signals completion, can observe paced navigation, and controls when the browser is closed.
- **FR-009**: Users MUST be able to request a non-assisted authentication approach when the host can support it without persisting secret values.
- **FR-010**: Durable browser-first understanding MUST include the understanding mode, a product summary, a sanitized target environment, exploration scope, synthesized product signals, a compatible coverage inventory, candidate validation journeys, provenance status, observed-at time, and gaps.
- **FR-011**: Persisted target locators MUST use HTTP(S), omit URL fragments and query values, and preserve only the non-secret origin/path information needed to identify the environment.
- **FR-012**: Persisted browser evidence MUST NOT contain credentials, authorization material, cookies, browser storage, raw DOM, MCP snapshots, screenshots, traces, response bodies, entered form values, or raw query values.
- **FR-013**: Product signals MUST be structured, synthesized observations with stable identifiers, surface/state descriptions, user-visible evidence summaries, provenance, and confidence; they MUST NOT embed raw captured browser artifacts.
- **FR-014**: Candidate journeys MUST identify the inventory items and/or product signals supporting them, rank confidence and priority, state runtime prerequisites, and distinguish read-only from potentially mutating behavior.
- **FR-015**: Exploration MUST produce three to five candidates when the product exposes that many within scope; otherwise it MUST report a partial result and explain why the range was not met.
- **FR-016**: Browser-first freshness MUST be age-based and MUST NOT require Git metadata. Repository and hybrid modes MAY additionally use Git freshness.
- **FR-017**: The public workflow information contract MUST advertise browser-first understanding capability and describe accepted input, required durable output, safety constraints, modes, and compatibility guarantees.
- **FR-018**: The system MUST continue to accept existing `product-context/v1` repository fields and existing coverage inventories, including candidate `sourceInventoryItems`, without requiring migration.
- **FR-019**: Hybrid understanding MUST preserve provenance that distinguishes repository-derived evidence from browser-observed evidence and MUST expose conflicts as gaps rather than silently choosing one source.
- **FR-020**: The host browser integration MAY use Playwright MCP or an equivalent browser/Playwright interface, but durable state and downstream workflows MUST NOT depend on provider-specific snapshot formats.
- **FR-021**: Deterministic discovery, probing, and execution MUST use only documented public VerifySignal Core CLI operations and versioned schemas.
- **FR-022**: A potentially mutating candidate MUST require explicit user confirmation and MUST be executed only through a public Core probe operation that provides pre-commit evidence and does not commit the write.
- **FR-023**: If a required browser or Core capability is missing, the system MUST report a blocked or partial status with an actionable prerequisite and MUST NOT claim successful understanding or proof.
- **FR-024**: After mapping, the system MUST let the user review candidates and select one approved journey for proof; it MUST not automatically choose a mutating journey.
- **FR-025**: The browser MUST remain open after exploration until the user acknowledges the understanding summary or explicitly asks to close it.
- **FR-026**: Existing repository understanding, readiness, planning, and validation behavior MUST remain compatible and covered by regression tests.
- **FR-027**: Installing or upgrading a Codex or Claude integration MUST register the VerifySignal-managed Playwright MCP in that agent's user scope through the agent's public MCP command, MUST preserve unrelated and user-owned MCP configuration, MUST be idempotent, and MUST preserve the workspace's current default integration. Existing exact project-scoped managed entries MAY remain as a backward-compatible fallback.
- **FR-028**: Every generated or returned agent command MUST use the selected integration's native invocation syntax: `$verifysignal-*` for Codex and `/verifysignal-*` for Claude Code. Existing persisted history MUST remain readable without a destructive migration.
- **FR-029**: The public understand contract MUST expose complete nested field shapes, enums, required fields, bounded aliases, and a usable canonical example; callers MUST NOT need installed source inspection to construct a valid payload.
- **FR-030**: Browser payload normalization MUST reject unknown fields, missing required values, invalid references, and canonical/alias conflicts before writing any artifact, and MUST report the failing field path.
- **FR-031**: The bounded compatibility aliases MUST include inventory `surface`, `summary`, `kind`, and `status`; candidate `id`, `title`, `expectedOutcome`, and `sideEffects.class`; signal `inventoryReferences`; and top-level `candidateUseCases` when its canonical nested field is absent.
- **FR-032**: Browser candidate journeys MUST carry an explicit grounding status. Missing legacy grounding MUST normalize conservatively to `unknown` and MUST NOT qualify for automatic guidance.
- **FR-033**: A multi-surface candidate marked `observed` MUST reference a structured transition signal with source and destination surfaces. Authentication boundaries MUST be represented as runtime requirements or gaps and MUST NOT be reported as unauthenticated observed transitions.
- **FR-034**: Declared side-effect classification MUST be authoritative for first-run safety. `write`, `external-notification`, and `unknown` candidates MUST NOT qualify as read-only.
- **FR-035**: First-run ranking MUST have one public authority, preserve deterministic meaningful tie order, accept inventory-only candidates, and continue through the selected integration's staged `specify` invocation rather than the legacy `author` command.
- **FR-036**: Managed Playwright MCP execution MUST use a pinned tested version, an isolated private temporary working directory, and cleanup on normal exit, error, interrupt, and termination; it MUST NOT create raw browser artifacts in the target project.
- **FR-037**: Integration upgrade MUST migrate the exact legacy VerifySignal Playwright entry, preserve a differing user-owned Playwright entry with a warning, and leave invalid host configuration untouched.
- **FR-038**: Structural validation readiness MUST identify its scope and next runtime-readiness action and MUST NOT be described as successful protected-runtime validation.
- **FR-039**: Managed Codex and Claude integration setup MUST install the exact pinned Playwright MCP provider into a private user cache before the agent session starts; the stdio launcher MUST execute that cached provider without package-registry access and MUST fail quickly with an exact setup command when the provider is unavailable.
- **FR-040**: Pull-request CI MUST start the pinned provider through the public VerifySignal launcher, complete MCP `initialize`, request `tools/list`, and require the browser navigation and snapshot tools before browser-first changes can merge.
- **FR-041**: Browser-first guidance MUST verify that headed browser tools are actually available in the current host session before navigation or persistence. A pre-observation host integration failure MUST NOT call understand persistence or create/update product-understanding artifacts.
- **FR-042**: The managed Codex Playwright MCP server MUST be discoverable from a fresh untrusted project through user-scoped agent configuration, exact earlier managed entries MUST upgrade safely, user-owned overrides MUST remain untouched, and pull-request CI MUST prove discovery through a real ephemeral Codex app-server thread without a trust or configuration override.
- **FR-043**: A workflow prerequisite response with `canProceed: false` because artifacts are missing MUST include a structured blocker with the missing artifact list and exact recovery command; it MUST NOT expose an empty `blockers` list.
- **FR-044**: Raw JSON passed to the file-only `--payload` option MUST fail with an actionable `--stdin` alternative instead of being treated as a path or empty payload. Invalid browser enums MUST report their allowed public values.
- **FR-045**: Non-repairable runtime blockers MUST retain their exact public recovery command. In particular, `entitlement.key-unknown` MUST NOT be routed through repeated `init`, forced init, or Core setup attempts.
- **FR-046**: Permission denial during JSON-mode integration initialization MUST return a structured non-success response with a stable blocker code and recovery guidance rather than an unstructured exception string.
- **FR-047**: Every product defect observed in the manual PR smoke MUST have a regression test demonstrated RED against the original PR head and GREEN against the correction before the pull request can be approved.
- **FR-048**: Interactive initialization MUST request an unlock token only after the entitlement API reports accepted email delivery. Delivery failure and throttling MUST preserve their original blocker without prompting for or attempting to exchange a token that was not sent.
- **FR-049**: Managed runtime receipts, refresh credentials, verification keys, and installed packages MUST be isolated by canonical entitlement API endpoint. The default production endpoint and explicit runtime-cache override MUST remain backward compatible, while local or staging initialization MUST NOT consume trust material cached for another endpoint.
- **FR-050**: A successful integration initialization MUST make a subsequent plain `codex` or `claude` launch use the managed browser without a wrapper, `-c` flag, synthetic project trust, or backend-specific launch command. Initialization MUST NOT report browser setup as ready when user-scope registration is missing or conflicting.
- **FR-051**: Runtime readiness MUST consume Core's public authoring-warning metadata and MUST block before browser navigation when `degenerate-text-target` or `unstable-generated-css-target` is advertised with blocking runtime-readiness severity.
- **FR-052**: A Core/browser result with any side-effect policy violation MUST produce an overall failed Spec run and MUST NOT produce Golden Path `strictPass: true`, even when browser execution and authored gate coverage otherwise pass.
- **FR-053**: Run history MUST preserve a secret-safe semantic snapshot of the side-effect policy used by each run. An unchanged or unavailable prior policy MUST block rerun after a violation; an explicit owner policy change MAY permit rerun with a warning, but only a later clean result may supersede the violation for readiness and strict pass.
- **FR-054**: Repair MUST classify side-effect policy violations separately from selector findings and MUST require an owner decision. It MUST NOT automatically change side-effect class, mode, allowed rules, or forbidden rules.

### Key Entities

- **Product Understanding**: Versioned durable context for a product, including its mode, summary, provenance, freshness, target environment, coverage inventory, and gaps.
- **Target Environment**: Sanitized identity of the live application, including scheme, origin, path context, environment label, reachability status, and observation time.
- **Exploration Scope**: User-approved safety and budget boundary for browser mapping, including allowed origins, page/state and depth limits, candidate range, soft duration, and excluded actions.
- **Product Signal**: A synthesized, secret-safe observation of a user-visible surface, state, transition, or runtime prerequisite with provenance and confidence.
- **Coverage Inventory**: Compatible catalog of observed surfaces and ranked candidate validation journeys, enriched with browser signal references where available.
- **Proof Selection**: User-approved candidate, its side-effect classification, runtime prerequisites, public Core capability requirements, and deterministic evidence outcome.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On the reference fixture, a user can start from a non-Git directory and obtain valid browser-first understanding with at least three ranked candidate journeys in 15 minutes or less.
- **SC-002**: Every persisted browser-first target used in automated tests contains no fragment, raw query value, credential, cookie, storage state, raw DOM, snapshot, screenshot, trace, response body, or entered form value.
- **SC-003**: On the reference fixture, one user-approved read-only journey can be handed off to a documented Core CLI operation and produce deterministic pass/fail evidence.
- **SC-004**: A confirmed potentially mutating reference journey produces pre-commit probe evidence and zero committed application writes.
- **SC-005**: Existing repository-understanding unit and integration tests pass without changing existing workspace artifacts.
- **SC-006**: Workflow capability inspection exposes a versioned browser-first understanding contract that can be consumed without reading VerifySignal Spec source code.
- **SC-007**: Repeating persistence with the same normalized browser observations produces stable identifiers and equivalent durable understanding.
- **SC-008**: All missing-capability, unreachable-target, insufficient-coverage, and expired-authentication reference scenarios finish with explicit partial or blocked status and no false proof claim.
- **SC-009**: A fresh Codex or Claude install and an existing integration upgrade expose Playwright through idempotent user-scoped MCP registration while preserving unrelated and user-owned agent configuration.
- **SC-010**: Generated Codex guidance and Codex-selected public workflow responses contain no slash-prefixed VerifySignal agent commands, while Claude Code retains slash-prefixed commands.
- **SC-011**: Canonical and documented-alias forms of the reference browser payload persist equivalent non-empty inventory, signal references, side-effect classification, and candidate grounding; malformed forms produce no workspace writes.
- **SC-012**: No candidate whose transition was not observed, whose authentication boundary is unresolved, or whose side-effect class is not `none` is labeled safe for automatic first-run guidance.
- **SC-013**: Recommendation, user presentation, acceptance, and staged specify resume use the same candidate order and details for both Codex and Claude.
- **SC-014**: Fresh install, legacy upgrade, subprocess failure, interrupt, and termination fixtures leave no `.playwright-mcp`, screenshot, snapshot, trace, log, or storage-state artifact in the target project.
- **SC-015**: Structural readiness and runtime readiness remain independently inspectable, and a structural pass cannot hide an entitlement or runtime-readiness blocker.
- **SC-016**: After one successful integration setup, disabling package resolution during agent startup still permits the managed launcher to answer MCP `initialize` and expose `browser_navigate` and `browser_snapshot` within the host handshake deadline.
- **SC-017**: The real pinned-provider handshake test is a required pull-request CI check, while deterministic local tests exercise the same launcher boundary without network access.
- **SC-018**: An ephemeral Codex app-server thread started from a fresh untrusted project with no `-c` override reports the user-scoped `playwright` server and exposes `browser_navigate`, `browser_snapshot`, and `browser_click` without a model turn.
- **SC-019**: A pre-observation “no headed browser available” scenario writes no `.verifysignal/product-context.yaml` or understanding workflow document and directs the user to repair user-scoped host setup and restart the session.
- **SC-020**: The manual-smoke regression set fails before its corresponding fixes for browser discovery, candidate acceptance, invalid author handoff, invocation syntax, payload contract, readiness scope, missing-prerequisite blockers, entitlement recovery, packaged-runtime trust handoff, generated side-effect policy mode, and permission reporting, then passes on the corrected branch.
- **SC-021**: Inline JSON misuse, invalid reachability, invalid signal kind, and equivalent duplicated candidate aliases each produce one deterministic outcome without silent data loss or trial-and-error persistence.
- **SC-022**: A missing-plan run check includes a non-empty blocker and exact plan recovery, while `entitlement.key-unknown` retains a recovery command that contains neither init nor Core setup.
- **SC-023**: Unavailable and throttled email-delivery fixtures make zero exchange requests and expose their original blocker, while an accepted delivery permits an empty token response that preserves `token-delivery-pending`.
- **SC-024**: With a valid production receipt, key set, and runtime package already cached, initializing against a local entitlement API uses a distinct deterministic namespace and observes none of those production artifacts; the same endpoint reuses its own namespace across runs.
- **SC-025**: When a Codex session exposes the project Playwright MCP navigation and snapshot tools while the Browser Plugin inventory is empty, browser-first understanding uses the MCP and neither reruns setup nor recommends a restart.
- **SC-026**: In a clean user configuration and a new non-Git project, integration initialization followed by the unmodified `codex` or `claude` executable discovers the managed Playwright MCP; the same acceptance fails when initialization is omitted.
- **SC-027**: Static runtime readiness blocks both degenerate-text and unstable-generated-CSS fixtures without opening a browser.
- **SC-028**: A deterministic full-coverage fixture with a side-effect violation reports overall failure and no strict pass.
- **SC-029**: The same fixture cannot rerun under an unchanged policy, may rerun only after an explicit semantic policy change, and reaches strict pass only after a clean subsequent run.
- **SC-030**: Repair may propose selector correction from the same report but never proposes or applies an automatic side-effect allow rule.

## Assumptions

- The user is authorized to inspect and validate the supplied target environment.
- The host integration can provide a headed browser through Playwright MCP or an equivalent browser/Playwright API. VerifySignal installs the pinned host MCP provider ahead of agent startup, but does not replace Core's deterministic browser-validation runtime.
- Same-origin read-safe exploration is sufficient for the first release; broad crawling, arbitrary third-party origins, and whole-product coverage claims are out of scope.
- The user remains present for assisted authentication and candidate approval.
- The existing coverage inventory schema remains the compatibility bridge for downstream specify/plan/tasks/implement stages.
- VerifySignal Core's stateful pre-commit probe capability is the required
  authority for potentially mutating proof. The release gate is satisfied by
  Core main merge `6ea5d7f`, which advertises `verifysignal.probe/v1`.
