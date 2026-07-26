# Feature Specification: State-Aware Automatic Authoring Loop

**Feature Branch**: `024-state-aware-auto-loop`
**Created**: 2026-07-26
**Status**: Draft
**Input**: User description: "Align the automatic authoring loop with Core stateful pre-commit probing so authenticated multi-page write flows can be grounded safely, while older Core versions fail closed instead of suggesting unsupported storage-state flags."

## Constitution Alignment

- **Public Core boundary**: Spec consumes `probe` only through the documented public CLI JSON contract and discovers it as an optional capability from Core version metadata. No Core source imports or private report inspection are introduced.
- **Project-local workspace portability**: Existing run requests, skills, credential references, and session references remain project-local. Probe results are attempt-local and are not persisted as new workspace state.
- **Secret safety**: Credential and session values remain out-of-band. Guidance and diagnostics may name references but never persist or print resolved values, cookies, browser storage, or secret-bearing command lines.
- **Agent-neutral interface**: The shared automatic-loop template drives identical behavior for Codex and Claude. Deterministic CLI commands and existing staged workflows remain available.
- **Testable delivery**: Adapter argv, capability negotiation, run-request session support, template branches, legacy fallback, redaction, and a real public Core contract smoke test receive automated coverage.

## User Scenarios & Testing

### User Story 1 - Ground an authenticated write flow safely (Priority: P1)

As a developer authoring an authenticated multi-page write use case, I want the automatic loop to ask Core to exercise only the safe prefix and inspect the real commit state, so selector grounding completes without creating the resource.

**Why this priority**: This is the missing product path that caused the original workflow to stop after lengthy source analysis despite Core already understanding credentials and imported sessions.

**Independent Test**: Against a fake and packaged Core advertising `probe`, prepare a write run request with credentials or a session reference and verify that the loop invokes probe with the same run request and skills, consumes its target diagnostics, and does not invoke `run` before confirmation.

**Acceptance Scenarios**:

1. **Given** Core advertises `verifysignal.probe/v1` and a valid authenticated write run request, **When** the automatic loop reaches stateful grounding, **Then** it invokes probe with that run request and every referenced skill.
2. **Given** probe reaches the commit boundary successfully, **When** the loop prepares execution, **Then** it reports that no commit occurred and asks for explicit confirmation before normal run.
3. **Given** probe returns a confident target correction, **When** the loop repairs the skill, **Then** it persists the correction through the workflow API and probes again within the bounded repair budget.
4. **Given** the run request uses `sessionRef`, **When** the loop validates and probes it, **Then** the reference is preserved as a first-class runtime input and no session value is persisted.

---

### User Story 2 - Fail accurately on older Core versions (Priority: P2)

As a user with a Core version that lacks probe, I want the loop to explain what is and is not possible, so it does not waste time on static discovery or invent unsupported authentication flags.

**Why this priority**: Capability mismatch must be explicit; otherwise the same poor experience recurs under a different command sequence.

**Independent Test**: Feed version responses with discover-only, probe-capable, and neither capability, then verify the exact workflow branch and upgrade guidance.

**Acceptance Scenarios**:

1. **Given** an authenticated write flow and a Core without probe, **When** the loop checks capabilities, **Then** it blocks before mutating execution and recommends upgrading Core.
2. **Given** an authenticated read-only flow and a Core without probe but with discover, **When** the loop checks capabilities, **Then** it may continue with the existing discover/source-only path while stating its page-state limitation.
3. **Given** generated agent guidance, **When** it describes authentication support, **Then** it never suggests a `discover --storage-state` option that the public contract does not expose.

---

### User Story 3 - Preserve deterministic and cross-agent behavior (Priority: P3)

As a maintainer, I want probe support to be optional and additive, so existing Core versions, staged commands, integrations, and deterministic registered-use-case runs remain compatible.

**Why this priority**: The feature must improve the automatic path without turning an optional Core capability into a package-wide installation requirement.

**Independent Test**: Install both Codex and Claude integrations, compare their rendered guidance, and run existing compatibility suites against Core fixtures with and without probe.

**Acceptance Scenarios**:

1. **Given** a Core version without probe, **When** general Spec readiness is checked, **Then** installation remains compatible because probe is optional.
2. **Given** Codex and Claude integration installation, **When** their automatic-loop skills are rendered, **Then** both express the same capability, safety, and confirmation rules.
3. **Given** existing list, validate, and run workflows, **When** probe support is installed, **Then** their public behavior remains unchanged.

### Edge Cases

- Core advertises an operation named `probe` with a different schema; Spec treats it as unsupported.
- Probe reports that the commit boundary was not reached; the loop does not claim the skill is grounded.
- Probe returns a blocking target without a confident correction; the loop stops and asks for target intent.
- The run request references multiple skills; Spec preserves their declared order in Core argv.
- A session reference is structurally present but unresolved by Core; Spec forwards the public failure without reading session material.
- Probe output contains unknown additive fields; Spec ignores them unless required by its documented decision branch.

## Requirements

### Functional Requirements

- **FR-001**: `CoreAdapter` MUST expose `probe(run_request, skills, ...)` through the public Core CLI JSON contract.
- **FR-002**: Spec MUST provide capability detection that returns true only when Core advertises operation `probe` with schema `verifysignal.probe/v1`.
- **FR-003**: Probe MUST remain optional and MUST NOT be added to the globally required Core operations.
- **FR-004**: The automatic loop MUST use probe for authenticated `write` and `external-notification` flows when available.
- **FR-005**: The automatic loop MUST pass the existing run request and all referenced skills to probe without copying resolved credential or session values into argv or workspace state.
- **FR-006**: The automatic loop MUST require a successful reached-but-not-executed commit boundary before describing the write flow as statefully grounded.
- **FR-007**: After a successful write-flow probe against a developer-controlled target, the automatic loop MUST require explicit user confirmation before invoking normal `run`. Invoking the isolated structural dogfood is itself explicit authorization for its single ephemeral local write.
- **FR-008**: When probe is unavailable, authenticated write flows MUST block with upgrade guidance; authenticated read-only flows MAY use discover or source-only authoring with an explicit limitation notice.
- **FR-009**: Agent templates MUST NOT document nonexistent Core options, including `discover --storage-state`.
- **FR-010**: Workspace models, validation, and rendering MUST preserve public `sessionRef` values as references without resolving or persisting session data.
- **FR-011**: Probe target repair MUST use existing workflow persistence and bounded repair rules.
- **FR-012**: Existing staged commands, deterministic run paths, Core compatibility checks, and integration installation behavior MUST remain compatible.

### Quality and Operability Requirements

- **NFR-001**: Adapter and capability behavior MUST have unit and contract tests for compatible, incompatible-schema, and absent probe operations.
- **NFR-002**: Template tests MUST cover probe-capable write, legacy write, legacy read-only, explicit confirmation, and removal of unsupported flags.
- **NFR-003**: Credential and session values MUST not appear in persisted workspace files, rendered commands, histories, or public summaries.
- **NFR-004**: A real public Core CLI smoke test MUST validate capability negotiation without private imports.
- **NFR-005**: Existing integration, workspace, and deterministic-run regression suites MUST remain green.
- **NFR-006**: Feature dogfood MUST use an identity-neutral structural twin and MUST NOT reference or reproduce a real target product's name, domain, copy, logo, imagery, color system, typography, or other visual identity.
- **NFR-007**: The structural dogfood MUST invoke Spec's public probe command against the real sibling Core, preserve the existing minimal Core example, and execute exactly one explicitly authorized local normal run. If public run readiness requires a structured confirmation, the dogfood MUST pass only the returned confirmation id.
- **NFR-008**: A red structural-dogfood result MUST stop before product-code changes and retain safe diagnostics for review.

### Key Entities

- **Probe Capability**: Optional Core operation identity, schema version, and compatibility status.
- **Probe Invocation**: One run request, ordered skill paths, optional runtime presentation flags, and entitlement receipt.
- **Stateful Grounding Outcome**: Whether the boundary was reached, proof that it was not executed, target diagnostics, and deferred work.
- **Legacy Capability Decision**: Safe branch selected when probe is absent based on side-effect class and authentication needs.

## Success Criteria

### Measurable Outcomes

- **SC-001**: A probe-capable authenticated write fixture reaches the confirmation gate with zero normal-run invocations.
- **SC-002**: One hundred percent of authenticated write fixtures using a Core without probe stop with upgrade guidance before execution.
- **SC-003**: All installed automatic-loop templates contain zero references to unsupported `discover --storage-state`.
- **SC-004**: Credential/session leak assertions pass for adapter argv, workspace files, and rendered guidance.
- **SC-005**: Existing compatibility and deterministic workflow suites remain green with probe absent or present.
- **SC-006**: Cross-repository structural dogfood proves the unauthenticated discover limitation, zero commits after probe and run readiness, and exactly one commit after one authorized isolated run.

## Assumptions

- Core owns browser execution, credential/session resolution, side-effect observation, and the invariant that probe never executes the commit step.
- Spec owns capability negotiation, orchestration policy, workspace references, repair persistence, and user-facing guidance.
- Core remains unaware of Spec. The isolated dogfood invocation authorizes only its loopback, process-local resource write and does not alter normal target authorization guidance.
- Probe is entitlement-protected by Core; Spec forwards the receipt through its existing public invocation pattern.
- Static `discover` remains useful for public/read-only entry-state targets but is not an authenticated multi-step substitute.
- The isolated Core reference application is sufficient dogfood for this feature because it preserves the authenticated write-flow structure without coupling validation to a branded or production product.
