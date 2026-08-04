# Feature Specification: Canonical VerifySignal Distribution

**Feature Branch**: `027-rename-public-interface`
**Created**: 2026-08-04
**Status**: Draft
**Input**: Rename the public open-source interface from VerifySignal Spec to VerifySignal while preserving compatibility and using a staged PyPI and GitHub migration.

## Constitution Alignment *(mandatory)*

- **Public Core boundary**: The interface continues to obtain and invoke the private Runtime only through documented release and CLI contracts; no Core source import is introduced.
- **Project-local workspace portability**: `.verifysignal/`, its persisted schemas, and existing workspace interpretation remain unchanged across package names.
- **Secret safety**: The migration changes names and release metadata only; credential handling, redaction, and ignored secret files remain untouched and covered by regression tests.
- **Agent-neutral interface**: The `verifysignal` CLI remains the canonical non-agent interface; integrations and legacy skill aliases continue to delegate to it.
- **Testable delivery**: Packaging, entry-point, identity, schema, workspace, integration, build, and isolated-install contracts receive explicit red/green and regression evidence.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Install VerifySignal by its product name (Priority: P1)

A new user can install `verifysignal` from PyPI, run `verifysignal`, and receive the same open-source interface and managed Runtime behavior that existing users receive.

**Why this priority**: Removing `-spec` from the acquisition path is the direct marketing and onboarding outcome of the migration.

**Independent Test**: Build the canonical wheel, install it into an isolated environment by distribution artifact, run the CLI, and verify package metadata and Runtime setup behavior.

**Acceptance Scenarios**:

1. **Given** the canonical distribution is published, **When** a new user runs `uv tool install verifysignal`, **Then** the `verifysignal` executable is installed and operational.
2. **Given** the canonical wheel, **When** metadata is inspected, **Then** its project name is `verifysignal` and its public product wording is VerifySignal.
3. **Given** the canonical interface invokes a managed private executable, **When** public guidance describes that component, **Then** it calls it “VerifySignal Runtime”.

---

### User Story 2 - Upgrade without breaking persisted or automated contracts (Priority: P1)

An existing `verifysignal-spec` user can move to `verifysignal` without changing imports, commands, workspace files, schema identifiers, environment variables, workflow roles, or legacy integration aliases.

**Why this priority**: The package rename is safe only if public and persisted behavior survives independently of the distribution label.

**Independent Test**: Compare the old and canonical artifacts and run contract fixtures proving preserved module imports, both executable entry points, all versioned schema identifiers, `.verifysignal/` state, `VERIFYSIGNAL_SPEC_*` variables, the `spec` role, and legacy skill aliases.

**Acceptance Scenarios**:

1. **Given** code imports `verifysignal_spec`, **When** the canonical distribution is installed, **Then** the import succeeds unchanged.
2. **Given** automation invokes `verifysignal-spec`, **When** the canonical distribution is installed, **Then** the legacy executable alias invokes the same CLI.
3. **Given** an existing `.verifysignal/` workspace containing `verifysignal-spec-*/v1` artifacts, **When** the canonical CLI reads it, **Then** no schema migration or rewrite is required.
4. **Given** existing environment variables, workflow role `spec`, `/verifysignal-specify`, or `verifysignal-spec-*` skill aliases, **When** integrations run, **Then** those identifiers remain accepted.

---

### User Story 3 - Complete a recoverable registry and repository cutover (Priority: P2)

A maintainer can publish one final old-name release, establish the canonical PyPI project, rename the GitHub repository, and publish a post-rename patch without deleting the recovery path.

**Why this priority**: PyPI project identity and trusted publishing do not follow a GitHub rename automatically, so release order is a functional safety property.

**Independent Test**: Exercise static workflow contracts and isolated artifact smoke tests for each stage, with manual evidence for trusted-publisher and repository operations.

**Acceptance Scenarios**:

1. **Given** the old project is still canonical, **When** the final `verifysignal-spec` patch is published, **Then** it announces the move and the old project remains installable but receives no later feature releases.
2. **Given** a pending trusted publisher for PyPI project `verifysignal` tied to repository `verifysignal-spec`, **When** canonical 0.23.0 publishes, **Then** it uses the existing repository slug and is smoke-tested before rename.
3. **Given** canonical 0.23.0 is verified, **When** GitHub is renamed to `RigelRise/verifysignal`, **Then** a new exact trusted-publisher binding is created before publishing the post-rename patch.
4. **Given** post-rename publishing succeeds, **When** public metadata is inspected, **Then** source URLs use `RigelRise/verifysignal` and the old PyPI project remains present and not yanked.

### Edge Cases

- The PyPI name appears public but ownership is not authenticated or reservable.
- A pending trusted publisher does not reserve the canonical PyPI project until first publication.
- GitHub redirects repository URLs but GitHub Actions and trusted-publisher identity use exact repository names.
- Both distribution artifacts expose the same console scripts and import package.
- An internal schema contains `verifysignal-spec` and must not be renamed as marketing copy.
- A generated integration includes a legacy alias intentionally while user-facing prose should use VerifySignal.
- A contributor has an old local sibling directory after the GitHub repository rename.
- Release versioning is derived from PR titles and must not be hand-edited in a feature PR.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The canonical PyPI project MUST be named `verifysignal`.
- **FR-002**: The canonical distribution MUST expose the `verifysignal` executable.
- **FR-003**: The canonical distribution MUST retain the `verifysignal-spec` executable as a compatibility alias.
- **FR-004**: The Python import package `verifysignal_spec` MUST remain unchanged.
- **FR-005**: Every existing `verifysignal-spec-*/v1` schema identifier MUST remain byte-for-byte unchanged unless separately versioned in a future feature.
- **FR-006**: `.verifysignal/` workspace paths and interpretation MUST remain unchanged.
- **FR-007**: Existing `VERIFYSIGNAL_SPEC_*` environment variables MUST remain accepted.
- **FR-008**: Existing workflow role `spec`, `/verifysignal-specify`, `verifysignal-spec`, and legacy `verifysignal-spec-*` skill aliases MUST remain accepted where currently public.
- **FR-009**: Canonical onboarding MUST use `uv tool install verifysignal`.
- **FR-010**: Public product wording MUST use VerifySignal and MUST describe the private executable as VerifySignal Runtime; narrowly technical implementation documents MAY use Core.
- **FR-011**: The old `verifysignal-spec` PyPI project MUST receive one final patch release announcing migration, then remain available, frozen, and not yanked.
- **FR-012**: Canonical 0.23.0 MUST publish before the GitHub repository is renamed.
- **FR-013**: GitHub MUST be renamed from `RigelRise/verifysignal-spec` to `RigelRise/verifysignal` only after canonical 0.23.0 passes isolated installation and runtime smoke tests.
- **FR-014**: A new exact PyPI trusted-publisher binding for repository `verifysignal` MUST be active before the first post-rename publish.
- **FR-015**: A post-rename patch MUST update repository metadata and prove publishing under the renamed slug before the old publisher binding is removed.
- **FR-016**: Release versions MUST continue to be derived by release automation from merged PR titles; implementation PRs MUST NOT hand-edit the version field.
- **FR-017**: Repository identity detection MUST accept both `verifysignal` and `verifysignal-spec` sibling checkout names during migration.
- **FR-018**: Every behavior change MUST begin with a failing focused test and retain that test after implementation.
- **FR-019**: Existing CLI, Runtime resolution, entitlement, browser, secret-safety, and agent-neutral regression suites MUST remain green.
- **FR-020**: Canonical distribution and repository changes MUST be independently reversible until each publication stage is verified.

### Key Entities

- **Distribution Identity**: PyPI project name and built artifact metadata; old `verifysignal-spec` and canonical `verifysignal` are distinct immutable registry identities.
- **Import Identity**: Stable Python package `verifysignal_spec` shared by both distributions for compatibility.
- **Executable Identity**: Canonical `verifysignal` command plus legacy `verifysignal-spec` alias.
- **Persisted Contract Identity**: Stable workspace paths, schema identifiers, environment variables, roles, commands, and skill aliases that are not marketing labels.
- **Repository Identity**: GitHub owner/slug and local sibling aliases before and after rename.
- **Trusted Publisher Binding**: Exact PyPI-to-GitHub Actions identity including owner, repository, workflow, and environment.
- **Migration Release**: Final old-name patch, first canonical minor, and first post-rename canonical patch, each with distinct acceptance evidence.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An isolated `uv tool install verifysignal` produces a working `verifysignal` command from the canonical release.
- **SC-002**: 100% of recorded versioned schemas, persisted workspace fixtures, supported environment variables, roles, and compatibility aliases remain accepted.
- **SC-003**: The canonical artifact contains both console entry points and the unchanged `verifysignal_spec` import package.
- **SC-004**: The final old-name, first canonical, and post-rename releases each pass artifact build, metadata, isolated-install, CLI, and managed-Runtime smoke validation.
- **SC-005**: Public repository metadata and onboarding use `RigelRise/verifysignal` after rename, while the old GitHub URL redirects and the old PyPI project remains installable.
- **SC-006**: Full unit, contract, integration, Docker, and cross-repository regression suites remain green at the appropriate migration gates.
- **SC-007**: No release step relies on an outdated trusted-publisher repository identity.

## Assumptions

- The authenticated maintainer can create trusted-publisher bindings for both GitHub repository slugs during the staged cutover.
- Public availability checks do not prove authenticated ownership; manual authenticated confirmation remains required.
- PyPI project names cannot be renamed, so old and canonical distributions are separate projects.
- GitHub repository redirects are retained by never reusing the old slug.
- Version 0.22.1 is the intended final old-name patch, 0.23.0 the first canonical release, and 0.23.1 the first post-rename patch, subject to existing automated release calculation.
- Cross-repository Core and backend PRs merge only after the canonical package and repository gates they reference are live.
