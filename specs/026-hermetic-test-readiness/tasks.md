# Tasks: Hermetic Update and Test Readiness

**Input**: Design documents from `/specs/026-hermetic-test-readiness/`  
**Tests**: Required; use red → green → refactor.

## Phase 1: Setup and Contracts

- [x] T001 Create the feature branch from `origin/main`
- [x] T002 Write specification, plan, research, data model, contracts, and quickstart
- [x] T003 Point `AGENTS.md` at the active feature plan
- [x] T004 Validate feature prerequisites and requirements checklist

## Phase 2: Managed Core Lifecycle

- [x] T005 Add red workspace/resolver tests for resolution modes, reset, exact-latest cache, and fallback
- [x] T006 Add red CLI/integration tests for `core reset`, `core update`, accurate `core version`, and pure `integration upgrade`
- [x] T007 Implement additive workspace resolution metadata and migrations
- [x] T008 Implement managed-only latest resolution and verified fallback
- [x] T009 Implement Core lifecycle commands and CLI contracts
- [x] T010 Make integration upgrade Core-independent and run focused regressions

## Phase 3: Workflow Target Confirmation

- [x] T011 Add red model/persistence tests proving suggestions remain pending
- [x] T012 Add red workflow prerequisite tests for current-run confirmation and structured blocker
- [x] T013 Extend authoring questions and workflow runs with suggestion/confirmation state
- [x] T014 Prevent specification, plan, and implementation persistence from self-confirming target
- [x] T015 Accept direct-user/explicit-command clarification and gate browser stages
- [x] T016 Run focused target workflow and compatibility tests

## Phase 4: Secure Credential Readiness

- [x] T017 Add red strict dotenv parser, allowlist, permission, and non-mutation tests
- [x] T018 Add red preparation tests for Git exclusion, 0600, preservation, append, and pre-write failure
- [x] T019 Add red CLI propagation and secret-canary tests for validate/probe/run
- [x] T020 Implement declared-key collection and strict explicit environment loader
- [x] T021 Implement `credentials prepare` and its safe result schema
- [x] T022 Add `--env-file` to runtime readiness, probe, and run
- [x] T023 Run focused credential, session, runtime-input, and redaction regressions

## Phase 5: Agent Experience and Compatibility

- [x] T024 Update shared agent guidance to confirm target and guide credential preparation end to end
- [x] T025 Verify Codex and Claude render identical target/credential guidance
- [x] T026 Verify legacy workspaces, staged workflows, and explicit one-shot Core overrides

## Phase 6: Version and Product Truth

- [x] T027 Bump Spec from `0.20.0` to `0.21.0` consistently
- [x] T028 Add identity-neutral loopback dogfood with a discoverable local Core candidate
- [x] T029 Prove managed update, target confirmation, credential preparation, zero-resource probe, and one-resource run
- [x] T030 Run the complete pytest suite
- [x] T031 Review contracts/tasks, confirm Core requires no change, and mark completion

## Dependencies

- Core lifecycle, target confirmation, and credential preparation can be
  developed independently after contract setup.
- Agent guidance depends on all public CLI shapes.
- Version, full suite, and dogfood follow focused green checkpoints.

## Implementation Strategy

Make the observed contamination and readiness gaps fail independently first.
Preserve legacy resolution for untouched workspaces, then compose the new
managed-only, target-confirmed, explicit-env path in the structural dogfood.
