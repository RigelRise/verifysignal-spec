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
