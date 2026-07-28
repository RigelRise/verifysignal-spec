# Research: Browser-First Product Understanding

## Decision 1: Separate exploration, understanding, and proof authorities

**Decision**: A host integration explores with Playwright MCP or an equivalent
headed browser interface. VerifySignal Spec validates and persists synthesized
understanding. VerifySignal Core remains the deterministic authority for
discover, probe, and run.

**Rationale**: Each layer already has a public responsibility. Keeping browser
session mechanics out of Spec avoids a second runtime and preserves agent
portability.

**Rejected alternative**: Add a new Core operation for product mapping. That
would couple exploratory, conversational behavior to the deterministic engine
and delay the feature on a new cross-repository API.

## Decision 2: Add modes without a product-context migration

**Decision**: Add `workspaceKind`, `understandingMode`, `targetEnvironment`,
`explorationScope`, `productSignals`, and browser provenance as optional
`product-context/v1` fields. Existing repository fields remain accepted and
imply `repository` mode.

**Rationale**: Existing consumers already tolerate additive YAML content, while
repository workflows depend on current field names and coverage inventory.

**Rejected alternative**: Introduce `product-context/v2`. The first browser
slice does not require a breaking representation and a migration would add risk
without user value.

## Decision 3: Persist synthesized signals, never browser captures

**Decision**: Convert observations into stable, structured product signals that
contain only surface/state descriptions, user-visible evidence summaries,
provenance, confidence, and safe references. Reject raw DOM, snapshots,
screenshots, traces, response bodies, cookies/storage, form values, and secret
material.

**Rationale**: Durable understanding should explain product behavior, not clone
an ephemeral browser session or create a credential-bearing evidence store.

**Rejected alternative**: Save MCP snapshots for later agents. Snapshot formats
are provider-specific, can contain sensitive values, and become stale quickly.

## Decision 4: Sanitize target URLs at the persistence boundary

**Decision**: Accept only HTTP(S), normalize scheme/host/port/path, discard
fragments and the entire query component, and derive allowed origins from the
sanitized URL.

**Rationale**: Query names and values frequently contain session, invitation,
reset, or tenant secrets. Origin and path are enough for product identity and
runtime follow-up.

**Rejected alternative**: Redact only known secret parameter names. Unknown
applications use unknown names, making deny-list redaction unsafe.

## Decision 5: Use bounded, read-safe exploration defaults

**Decision**: Default to one allowed origin, 20 meaningful pages/states, depth
3, three to five candidates, and a 15-minute soft budget. Do not activate
destructive, transactional, state-changing, or unknown controls during mapping.

**Rationale**: The goal is decision-quality candidate discovery, not crawling.
Hard scope metadata also makes partial results explainable and repeatable.

**Rejected alternative**: Explore until the agent judges the product complete.
That creates unbounded cost and an unverifiable whole-product coverage claim.

## Decision 6: Make assisted authentication observable

**Decision**: Default to a headed browser, user-entered credentials, explicit
login-complete acknowledgement, human-observable pacing, and a browser that
stays open until summary acknowledgement.

**Rationale**: Users can verify where credentials are entered and what the agent
does after authentication without putting secret values into chat or workspace
state.

**Rejected alternative**: Ask users to provide credentials or storage state to
Spec. That expands the secret boundary and duplicates Core reference handling.

## Decision 7: Keep coverage inventory as the downstream bridge

**Decision**: Browser observations populate the existing inventory and candidate
structures. Existing `sourceInventoryItems` continues to point to inventory item
IDs even when those items are browser-observed. Add optional signal/provenance
fields without making them mandatory for legacy records.

**Rationale**: Specify, first-run recommendation, planning, and task workflows
already consume the inventory contract.

**Rejected alternative**: Create a separate browser journey catalog. Every
downstream stage would need mode-specific branching and legacy migration.

## Decision 8: Compute freshness from available provenance

**Decision**: All understanding uses the existing age threshold. Repository and
hybrid modes additionally compare Git distance when Git evidence is available.
Browser-first mode never blocks because a directory has no Git repository.

**Rationale**: Browser observations decay with time, not commit distance.

**Rejected alternative**: Set a synthetic Git-unavailable error. That would
reintroduce repository access as a prerequisite.

## Decision 9: Publish an understand-stage capability

**Decision**: `verifysignal workflow info verifysignal-use-case --json`
advertises an `understand` payload contract and
`browser-first-understanding/v1` rules, defaults, modes, prohibited persistence,
and browser-provider boundary.

**Rationale**: Integrations must not inspect installed source to construct a
payload, and a non-AI caller needs the same supported contract.

**Rejected alternative**: Put all behavior only in agent command prose. That
would make the feature agent-specific and impossible to negotiate reliably.

## Decision 10: Require user-approved proof and Core probe for mutations

**Decision**: Mapping stops at candidate review. One selected read-only journey
may proceed through normal deterministic author/validate/run flow. A potentially
mutating journey requires explicit confirmation and Core probe v1; probe success
does not authorize a committing run.

**Rationale**: Exploration confidence and authorization to change customer data
are separate decisions.

**Rejected alternative**: Let the exploring browser click a candidate flow to
verify it. That bypasses Core safety and can commit an unintended action.

## Decision 11: Keep backend out of scope

**Decision**: Do not send product understanding or browser signals to the
VerifySignal backend and do not change backend APIs.

**Rationale**: The feature is self-service and project-local. Existing telemetry
contains command/outcome metadata only and does not need product payloads.

**Rejected alternative**: Add hosted synchronization before local behavior is
proven. It would add privacy, entitlement, retention, and migration work to the
critical path.

## Decision 12: Publish strict canonical shapes with bounded aliases

**Decision**: Publish complete nested understand shapes and accept only a
documented alias set at the persistence boundary. Normalize aliases before
model construction, reject conflicting canonical/alias values, reject unknown
or missing required fields with exact paths, and perform no writes on failure.

**Rationale**: The smoke workflow constructed plausible fields from the public
projection and persistence silently defaulted or discarded them. A bounded
compatibility layer preserves practical agent output without turning arbitrary
input into an undocumented API.

**Rejected alternative**: Accept arbitrary near-matching payloads. That makes
loss detection impossible and creates unstable implicit schemas.

## Decision 13: Make browser journey grounding explicit

**Decision**: Add candidate `groundingStatus` and structured transition
`fromSurface`/`toSurface` fields. Multi-surface observed candidates require a
referenced matching transition. Authentication-required, partial, blocked, and
unknown candidates remain reviewable but are not safe to auto-guide.

**Rationale**: Seeing two pages independently does not prove the user journey
between them. The distinction is required to prevent direct-URL navigation from
being authored as a verified click transition.

**Rejected alternative**: Rely on prose instructions alone. The CLI could not
detect or reject contradictory persisted evidence.

## Decision 14: Use one first-run ranking and staged handoff

**Decision**: The existing recommendation API owns ordering. Its score consumes
declared side effects and grounding, uses original inventory order for exact
ties, accepts candidates directly from product context, and resumes through the
integration-native `specify` skill.

**Rationale**: Independent agent ranking and a legacy `author` handoff produced
different recommendations and an unusable next command.

**Rejected alternative**: Keep agent-authored ranking or pre-create a use case
before acceptance. Both duplicate product logic and break the intended review
boundary.

## Decision 15: Isolate a pinned host MCP behind a Spec launcher

**Decision**: Managed Codex and Claude configurations invoke
`verifysignal integration playwright-mcp`. The command proxies stdio to
`@playwright/mcp@0.0.78` with `--isolated`, using a mode-0700 temporary cwd and
output directory and cleaning it on normal and signaled termination.

**Rationale**: The tested upstream MCP still creates console and snapshot files
despite its stdout option. Changing its cwd/output boundary is the only
deterministic way to keep provider artifacts out of the target project.

**Rejected alternative**: Continue using `@latest` or rely on
`--output-mode stdout`. Both leave behavior mutable, and the tested upstream
version does not honor the documented output option consistently.

## Decision 16: Keep structural and runtime readiness separate and explicit

**Decision**: Preserve the existing structural check command and schema while
adding an explicit scope and next runtime-readiness action. Entitlement trust
remains owned by feature 026 and is exercised only in the cross-branch release
smoke.

**Rationale**: The layers are valid, but the current wording lets an agent
describe a structural pass as full readiness.

**Rejected alternative**: Fold entitlement execution into the structural
check. That would change a fast read-only contract and duplicate runtime
authority.

## Decision 17: Prepare the MCP provider before agent startup

**Decision**: Integration install/upgrade resolves
`@playwright/mcp@0.0.78` once with npm into a mode-0700, versioned
VerifySignal user cache. `verifysignal integration playwright-mcp` executes the
cached binary directly; it never invokes `npx` or contacts a package registry
inside the Codex/Claude MCP startup process. A retryable
`integration setup-playwright-mcp` command repairs setup independently.

**Rationale**: The first isolated-launcher smoke used a fake `npx` process and
missed the real host boundary. In a network-restricted Codex session, `npx`
waited on registry resolution until Codex abandoned the MCP handshake, leaving
no browser tools. A deterministic stdio test now covers `initialize` and
`tools/list`, and pull-request CI repeats it against the real pinned package.

**Rejected alternative**: Keep resolving the package through `npx` at every
agent startup or merely increase the MCP timeout. Both keep browser
availability dependent on registry access and can reproduce the same silent
tool-discovery failure.

## Decision 18: Gate the host session, not only the provider process

**Decision**: Mark the managed Codex Playwright server as `required`, migrate
only the exact previously managed entry, and initially add a pull-request test
that starts a trusted ephemeral Codex app-server thread and queries
`mcpServerStatus/list`. Browser-first guidance performs an actual
current-session tool preflight before navigation. If no headed browser exists
before the first product observation, that is host setup state and is never
persisted as product understanding.

Decision 20 supersedes the trust-assisted test setup with user-scoped
registration and a clean untrusted-project acceptance.

**Rationale**: A successful provider stdio handshake proved the package itself
but did not prove that Codex loaded the project configuration, trusted the
project, or exposed the tools to the active session. The manual smoke regressed
despite the lower-level test. The app-server boundary exercises the same
project/trust/discovery path without invoking a model.

**Rejected alternatives**:

- Treat `codex mcp list` as project discovery. It reports global configuration
  and does not prove the active project session.
- Persist a blocked browser-first inventory with zero observations. Host
  availability is not product evidence and downstream workflows could mistake
  the artifact for grounded understanding.
- Overwrite `required = false` or other custom Playwright entries. A differing
  entry is user-owned and must be preserved.

## Decision 19: Keep MCP and Browser Plugin inventories distinct

**Decision**: Browser-first guidance checks the current session for project
Playwright MCP navigation and snapshot tools first. It checks an equivalent
host browser only when those MCP tools are absent. In Codex,
`agent.browsers.list()` is explicitly treated as the Browser Plugin/in-app
inventory, not as evidence about project MCP availability. Setup or restart
guidance is allowed only after both inventories lack usable navigation.

**Rationale**: A manual smoke had a loaded project Playwright MCP with all
required tools, while the unrelated Browser Plugin inventory returned an empty
list. The agent generalized that narrow result into “no browser available,”
reran an already-ready setup, and blocked before observation. Provider
handshake and app-server discovery tests were green, so the missing regression
was the agent-facing backend-selection contract.

**Rejected alternatives**:

- Treat any empty browser inventory as a global browser failure. Host browser
  inventories are not interchangeable.
- Always prefer the bundled Browser Plugin. The managed project Playwright MCP
  is the integration installed and verified by VerifySignal.
- Retry setup when MCP tools are already exposed. Setup cannot repair a
  selection error and adds an unnecessary restart loop.

## Decision 20: Register the managed MCP in agent user scope

**Decision**: `init` and integration install/upgrade use the selected agent's
public MCP command to register the VerifySignal-managed `playwright` server in
user scope. Codex uses `codex mcp add`; Claude uses
`claude mcp add --scope user`. Registration is idempotent, preserves a
different user-owned server, and is part of readiness. Existing exact
project-scoped entries remain a compatibility fallback.

**Rationale**: Project-scoped Codex MCP configuration is ignored until the
exact project is trusted. The previous real-session test injected trust with
`-c`, so it passed while a new user starting plain `codex` still saw no browser.
The backend development helper must stop before agent launch and cannot safely
repair this product-layer problem. User-scoped registration makes the real and
maintainer flows identical after initialization.

**Rejected alternatives**:

- Inject `projects={...trust_level="trusted"}` into a maintainer launch
  command. That only hides the production regression and weakens the trust
  boundary.
- Modify Codex trust configuration silently. Trust is owned by Codex and must
  remain a user decision.
- Require a VerifySignal wrapper around every `codex` or `claude` invocation.
  That creates a second launch path and does not match the installed product.

## Decision 21: Preserve side-effect attribution across static readiness and reruns

**Decision**: Consume Core's public blocking authoring-warning metadata during
static runtime readiness, and reconcile every observed side-effect violation
against a secret-safe semantic snapshot of the policy used for that run. A
violation makes the Spec result fail. The same or unknown prior policy blocks a
rerun; an explicit owner policy change permits one warned attempt; only a clean
later run restores strict pass. Repair may independently propose a selector
correction but never edits side-effect policy automatically.

**Rationale**: The manual run proved that browser execution and UI coverage can
look successful while the declared read-only boundary is violated. Treating
that as a warning loses the true failure owner, while automatically allowing
observed traffic turns repair into policy escalation. A policy snapshot makes
the owner decision deterministic without persisting secrets or browser payloads.

**Rejected alternatives**:

- Navigate during runtime readiness to discover ambiguity. Static validation
  must remain browser-free and consume the public Core contract instead.
- Treat every GraphQL POST as a write in Spec. Core owns transient protocol
  classification and can prove query-only traffic without exposing bodies.
- Auto-add an allow rule during repair. Policy is product intent and requires
  an explicit owner decision.
