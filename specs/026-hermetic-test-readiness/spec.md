# Feature Specification: Hermetic Update and Test Readiness

**Feature Branch**: `026-hermetic-test-readiness`  
**Created**: 2026-07-26  
**Status**: Complete  
**Input**: Make Core updates independent from development checkouts and make a
generated browser use case executable by explicitly confirming its target and
preparing declared test credentials safely.

## Constitution Alignment

- **Public Core boundary**: Spec continues to call Core only through documented
  CLI JSON operations. Core source and private report internals are not read.
- **Project-local portability**: Resolution mode, managed runtime metadata,
  target confirmation, and credential declarations remain portable workspace
  state. Secret values remain outside `.verifysignal/`.
- **Secret safety**: Environment files are opt-in, strict, permission checked,
  ignored by Git, and limited to declared keys. Values are never returned.
- **Agent-neutral interface**: Target confirmation and credential preparation
  are shared CLI/workflow contracts rendered for both supported agents.
- **Testable delivery**: Update isolation, workflow confirmation, dotenv
  handling, compatibility, and an identity-neutral structural dogfood receive
  red/green coverage.

## User Scenarios & Testing

### User Story 1 - Update to the managed Core deterministically (Priority: P1)

As a VerifySignal developer, I want `core update` to ignore local development
Core candidates, so dogfood and acceptance tests exercise the released runtime.

**Independent Test**: Put a newer-looking Core on PATH, in the workspace, in
environment overrides, and in an ancestor sibling; publish another version from
the managed fixture backend; verify update selects only the verified managed
release and reset removes persisted local resolution.

**Acceptance Scenarios**:

1. Given any persisted or discoverable local Core, when `core reset` runs, then
   local resolution is removed and the workspace enters `managed-only` mode.
2. Given an older compatible managed cache, when `core update` runs, then Spec
   queries the latest managed release instead of accepting that cache as final.
3. Given the exact latest verified cache, when update runs, then it reuses that
   cache without downloading it again.
4. Given the latest download fails verification or availability, when a
   previously verified managed runtime exists, then the update reports failure
   and retains that runtime as the active fallback without restoring local
   overrides.
5. Given `integration upgrade`, when integrations are regenerated, then Core is
   neither discovered nor set up and the response reports Core as not checked.

---

### User Story 2 - Confirm the browser target for each workflow (Priority: P1)

As a developer creating a browser use case, I want VerifySignal to ask whether
the inferred test URL is correct, so repository defaults do not silently choose
local, staging, or production.

**Independent Test**: Start a workflow whose repository suggests a local URL;
verify it remains pending with the URL as a recommendation, blocks browser
operations, accepts or replaces the target through clarification, and asks
again for a new workflow run.

**Acceptance Scenarios**:

1. Given a target inferred from repository context, when specification is
   persisted, then it becomes a pending question with candidate and source,
   never an answer.
2. Given a pending target question, when plan or implementation repeats the
   inferred URL, then the workflow remains blocked.
3. Given a direct user confirmation or a URL explicitly present in the current
   command, when clarification is persisted, then the current workflow run may
   discover, probe, and run against that target.
4. Given a later workflow run, when a prior run confirmed a target, then that
   URL may be suggested but must be confirmed again.
5. Given a missing confirmation, when a browser operation is attempted, then
   the structured blocker is
   `clarification.target-environment-confirmation-required`.

---

### User Story 3 - Prepare test credentials without friction or leakage (Priority: P1)

As a developer running an authenticated use case, I want exact missing key
guidance and a safe test environment template, so I can complete validation,
probe, and run without exposing credentials.

**Independent Test**: Declare test credential keys, prepare a Git-ignored
0600 environment file, populate it, and verify validate/probe/run pass only
declared values to Core while output and workspace files contain no values.

**Acceptance Scenarios**:

1. Given a use case with declared credential, session, or environment keys,
   when readiness is checked, then diagnostics name only the exact missing keys.
2. Given user permission, when `credentials prepare` runs, then it creates or
   updates a 0600 file and an exact `.git/info/exclude` entry, preserving
   existing declared values and appending missing declarations.
3. Given Git exclusion or secure permissions cannot be guaranteed, when prepare
   runs, then it blocks before writing the environment file.
4. Given an environment file with undeclared keys, executable syntax,
   interpolation, substitution, duplicate keys, or multiline values, when it is
   loaded, then it blocks without invoking Core.
5. Given a valid explicit environment file, when validate, probe, or run invokes
   Core, then file values override ambient values only for declared keys and the
   parent process environment is unchanged.

## Requirements

### Functional Requirements

- **FR-001**: Spec MUST expose `verifysignal core reset --json`.
- **FR-002**: Spec MUST expose `verifysignal core update --json`.
- **FR-003**: Update MUST ignore workspace local commands,
  `VERIFYSIGNAL_CORE_CMD`, `VERIFYSIGNAL_CORE_VERSION`, PATH Core, and
  ancestor-sibling discovery.
- **FR-004**: Update MUST resolve the managed backend's latest version before
  cache selection and MUST verify any selected distribution.
- **FR-005**: Update failure MUST keep local overrides removed and MAY retain
  only a previously verified managed runtime as fallback.
- **FR-006**: Workspace `coreResolutionMode` MUST support `legacy-auto`,
  `managed-only`, and `development-override`; absence MUST preserve legacy
  behavior.
- **FR-007**: `--core-cmd` MUST remain an invocation-only override, except
  `core setup --core-cmd`, which explicitly persists development override.
- **FR-008**: `integration upgrade` MUST regenerate integrations without Core
  resolution or setup.
- **FR-009**: Inferred browser targets MUST remain unconfirmed suggestions.
- **FR-010**: Target confirmation MUST be scoped to one `WorkflowRun`.
- **FR-011**: Browser discover, probe, and run MUST block until the current run
  has a direct-user or explicit-command target confirmation.
- **FR-012**: Plan and implementation artifacts MUST NOT self-confirm a target.
- **FR-013**: Spec MUST expose
  `verifysignal credentials prepare <alias> --env-file <path> --json`.
- **FR-014**: Validate runtime-readiness, probe, and run MUST accept
  `--env-file`.
- **FR-015**: Spec MUST never automatically read `.env` or `.env.local`.
- **FR-016**: Prepare MUST derive its allowlist from declared credential,
  session, and environment runtime keys.
- **FR-017**: Prepare MUST guarantee Git exclusion and owner-only file
  permissions before writing secret placeholders or values.
- **FR-018**: Environment parsing MUST use a non-executable, single-line dotenv
  subset with no interpolation or substitution.
- **FR-019**: Environment files MUST reject undeclared and duplicate keys.
- **FR-020**: Secret values MUST never appear in JSON output, persisted
  workflow state, logs, or generated guidance.
- **FR-021**: Preparation output MUST use
  `verifysignal-spec-credential-preparation/v1`.
- **FR-022**: Agent guidance MUST follow: confirm target, author, report exact
  missing keys, offer preparation with permission, validate, probe, obtain write
  authorization, and run.

### Quality and Operability Requirements

- **NFR-001**: Existing workspaces without `coreResolutionMode` remain valid.
- **NFR-002**: Existing staged commands and direct registered-use-case runs
  remain compatible.
- **NFR-003**: No new dependency is required for dotenv parsing.
- **NFR-004**: The feature dogfood MUST use a loopback, identity-neutral
  structural application and MUST not use any real product URL or identity.
- **NFR-005**: Dogfood MUST prove a discoverable local Core is ignored by
  update, a suggested target blocks until confirmed, preparation creates a
  secure file, probe creates zero resources, and one authorized run creates one
  resource.

## Edge Cases

- Workspace contains a stale `coreCommand` but already says `managed-only`.
- Managed metadata points to a cache entry whose digest no longer verifies.
- Environment file exists with correct contents but group-readable mode.
- `.git` is a worktree pointer rather than a directory.
- Suggested URL and confirmed URL are textually equal.
- Two workflow runs for the same alias overlap; confirmation belongs only to
  its referenced run.
- A declared key is present with an empty value; it remains structurally
  prepared but Core may report it missing according to its public contract.

## Success Criteria

- **SC-001**: Every local candidate source is ignored in managed update tests.
- **SC-002**: A failed update never reactivates a local override.
- **SC-003**: All browser gates reject an inferred-only target for the current
  run and accept direct confirmation.
- **SC-004**: All malicious dotenv fixtures block before Core invocation.
- **SC-005**: Secret canary values occur zero times in output and workspace.
- **SC-006**: The full suite and cross-repository structural dogfood are green.

## Assumptions

- The managed distribution backend already signs releases and cache metadata.
- Core already owns the final credential/session resolution semantics and
  returns safe missing-reference diagnostics.
- Users may intentionally use local Core via explicit one-shot `--core-cmd` or
  persisted `core setup --core-cmd`; `core update` intentionally exits that
  development mode.
