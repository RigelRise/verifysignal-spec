# Tasks: Browser-First Product Understanding

**Input**: Design documents from `/specs/025-browser-first-understanding/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Red/green tests are mandatory for the public workflow contract,
workspace normalization/persistence, secret safety, non-Git behavior, freshness,
repository compatibility, cross-agent guidance, and public Core compatibility.

**Organization**: Tasks are grouped by user story so live-product mapping,
approved proof handoff, and compatibility can be validated as independent
increments.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel because it changes different files and has no
  incomplete dependency.
- **[Story]**: `US1`, `US2`, or `US3` from [spec.md](./spec.md).
- Every implementation task names its concrete repository path.

## Phase 1: Setup and Contract Baseline

**Purpose**: Establish test helpers and feature-owned fixtures without changing
production behavior.

- [X] T001 Create reusable browser-first payload builders in `tests/fixtures/workflows/browser_first_understanding.py`
- [X] T002 [P] Record current repository-understanding regression expectations in `tests/integration/test_browser_first_understanding.py`
- [X] T003 [P] Add the 025 public spec exception to `.gitignore` and verify all feature artifacts are visible to Git

---

## Phase 2: User Story 1 - Map a Live Product Without Source Access (Priority: P1) 🎯 MVP

**Goal**: Persist safe, bounded browser-first product understanding in a
non-Git engagement directory and expose ranked candidates through existing
downstream inventory/readiness APIs.

**Independent Test**: Persist the reference browser payload into an initialized
non-Git directory, then verify current understanding, sanitized target, product
signals, partial/complete semantics, inventory candidates, and first-run
recommendation without source files.

### Red Tests for User Story 1

- [X] T004 [P] [US1] Add failing URL, origin, scope-default, product-signal, forbidden-field, and idempotence tests in `tests/unit/test_browser_understanding.py`
- [X] T005 [P] [US1] Add failing public understand-stage and capability projection tests in `tests/contract/test_browser_first_understanding_contract.py`
- [X] T006 [P] [US1] Extend `tests/contract/test_workflow_stage_persistence_contract.py` with browser-first accepted fields and defaults
- [X] T007 [US1] Add failing non-Git persistence, candidate, partial-coverage, secret non-persistence, and atomic-failure tests in `tests/integration/test_browser_first_understanding.py`
- [X] T008 [P] [US1] Add failing browser-mode freshness tests in `tests/unit/test_understanding_freshness_metadata.py` and `tests/unit/test_workflow_prerequisites.py`

### Implementation for User Story 1

- [X] T009 [US1] Implement pure browser understanding normalization and validation in `src/verifysignal_spec/workflows/browser_understanding.py`
- [X] T010 [US1] Extend understanding/inventory model literals and additive browser provenance fields in `src/verifysignal_spec/workflows/models.py`
- [X] T011 [US1] Publish the `understand` stage payload and `browser-first-understanding/v1` capability in `src/verifysignal_spec/workflows/stage_contracts.py`
- [X] T012 [US1] Add mode-aware normalization, required-field validation, compatibility projection, and atomic persistence in `src/verifysignal_spec/workflows/stage_persistence.py`
- [X] T013 [US1] Preserve additive browser fields and compatibility aliases in `src/verifysignal_spec/workspace/product_context.py` and `src/verifysignal_spec/templates/workspace/product-context.yaml`
- [X] T014 [US1] Render mode-neutral target, signal, provenance, and gap summaries in `src/verifysignal_spec/workflows/stage_documents.py`
- [X] T015 [US1] Make understanding freshness mode-aware and remove Git requirements/copy from browser-only paths in `src/verifysignal_spec/workflows/prerequisites.py`
- [X] T016 [US1] Make onboarding and first-run preparation consume browser target/candidates in `src/verifysignal_spec/workflows/first_run.py`
- [X] T017 [US1] Run the focused US1 tests and confirm the non-Git fixture passes with no forbidden durable browser data

**Checkpoint**: Browser-first mapping is usable and independently testable
without source or proof execution.

---

## Phase 3: User Story 2 - Prove One Approved Journey Safely (Priority: P2)

**Goal**: Guide candidate review and deterministic proof while keeping all
mutating behavior behind explicit confirmation and public Core probe.

**Independent Test**: Install the shared agent command, map a local fixture,
select one read-only candidate, and observe a public Core handoff; select a
potentially mutating candidate and observe an explicit probe-only gate.

### Red Tests for User Story 2

- [X] T018 [P] [US2] Add failing candidate-review, headed-login, visible-pacing, browser-lifecycle, and mutation-boundary assertions to `tests/integration/test_agent_template_guidance.py`
- [X] T019 [P] [US2] Add failing command metadata assertions for `--url` discoverability in `tests/contract/test_agent_command_contract.py`
- [X] T020 [P] [US2] Add failing exact public probe capability and blocked-legacy handoff assertions in `tests/contract/test_browser_first_understanding_contract.py`

### Implementation for User Story 2

- [X] T021 [US2] Rewrite the shared understand command flow in `src/verifysignal_spec/templates/agent-commands/verifysignal.understand.md`
- [X] T022 [P] [US2] Add reusable browser-first and probe-only safety guidance in `src/verifysignal_spec/templates/agent_guidance.py`
- [X] T023 [US2] Update public agent command description and argument hint in `src/verifysignal_spec/integrations/base.py`
- [X] T024 [US2] Expose proof-handoff rules through the browser-first capability projection in `src/verifysignal_spec/workflows/stage_contracts.py`
- [X] T025 [US2] Run template installation tests for Codex and Claude and validate exact public Core probe v1 against `/private/tmp/verifysignal-core-018-probe-reference`

**Checkpoint**: One approved journey can be handed to deterministic proof and a
mapping browser cannot silently commit writes.

---

## Phase 4: User Story 3 - Preserve Repository and Agent Portability (Priority: P3)

**Goal**: Keep legacy repository workspaces valid, support hybrid provenance,
and make behavior consistent across public CLI and supported integrations.

**Independent Test**: Persist an unchanged legacy repository payload and a
hybrid payload, inspect both through public workflow commands, and install the
same command into Codex and Claude temporary projects.

### Red Tests for User Story 3

- [X] T026 [P] [US3] Add failing hybrid provenance/conflict tests to `tests/integration/test_browser_first_understanding.py`
- [X] T027 [P] [US3] Add legacy artifact byte/semantic compatibility assertions to `tests/integration/test_understanding_onboarding.py`
- [X] T028 [P] [US3] Add integration-neutral capability assertions to `tests/contract/test_agent_guidance_contract.py`

### Implementation for User Story 3

- [X] T029 [US3] Normalize hybrid provenance and record conflicts as gaps in `src/verifysignal_spec/workflows/browser_understanding.py` and `src/verifysignal_spec/workflows/stage_persistence.py`
- [X] T030 [US3] Generalize residual repository-only user-facing understanding copy in `src/verifysignal_spec/workflows/stages.py`, `src/verifysignal_spec/workflows/engine.py`, and `src/verifysignal_spec/workflows/first_run.py`
- [X] T031 [US3] Verify existing repository payloads require no migration and all integration adapters render equivalent durable-contract guidance

**Checkpoint**: All three modes and supported adapters are independently valid.

---

## Phase 5: Polish, Documentation, and Release Gates

**Purpose**: Complete public communication, versioning, performance, and
cross-repository release validation.

- [X] T032 [P] Update feature-facing workflow/template documentation in `README.md`, `docs/README.md`, and `src/verifysignal_spec/templates/README.md`
- [X] T033 Bump the package minor version from `0.20.0` to `0.21.0` in `pyproject.toml` and all authoritative version fixtures, and record it in `CHANGELOG.md`
- [X] T034 Run secret-safety, workflow-persistence, first-run, agent-installation, and repository-understanding regression suites from `quickstart.md`
- [X] T035 Run the complete pytest suite and package build; resolve all regressions without weakening new assertions
- [X] T036 Validate workflow info and a browser-first persistence payload through the built public CLI
- [X] T037 Validate Core 018 public probe metadata and zero-commit precommit behavior from the isolated sibling worktree; revalidate and record the satisfied release gate on Core main merge `6ea5d7f`
- [X] T038 Run `git diff --check`, placeholder scans, spec/task consistency analysis, and mark every completed task `[X]`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup**: Starts immediately.
- **US1**: Depends on fixture setup and creates the public persistence foundation.
- **US2**: Depends on US1's public capability and persisted candidates.
- **US3**: Depends on US1 normalization and can otherwise be validated
  independently of proof execution.
- **Polish**: Depends on all selected stories.

### Within Each Story

1. Add tests and observe the expected failure.
2. Implement the smallest public behavior that makes the tests pass.
3. Run the focused story suite.
4. Run adjacent regression suites before moving on.

### Parallel Opportunities

- T001–T003 touch independent setup/test files.
- T004–T006 and T008 are independent red-test files.
- T018–T020 are independent contract/template tests.
- T026–T028 are independent compatibility tests.
- T032 can proceed separately from runtime validation once behavior is stable.

---

## Implementation Strategy

### MVP First

Complete T001–T017. This independently delivers safe live-product mapping and
ranked candidates in a non-Git directory.

### Incremental Delivery

1. Add approved proof handoff through T018–T025.
2. Complete repository/hybrid portability through T026–T031.
3. Finish release checks through T032–T038.

### Safety Gates

- Do not make browser exploration output a persisted raw artifact.
- Do not add a Spec browser runtime or private Core import.
- Do not execute a potentially mutating candidate outside explicit confirmation
  plus public probe.
- Claim release readiness only while Core main advertises exact probe v1; this
  condition was satisfied and revalidated at merge `6ea5d7f`.
