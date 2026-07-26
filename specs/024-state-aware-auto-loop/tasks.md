# Tasks: State-Aware Automatic Authoring Loop

**Input**: Design documents from `/specs/024-state-aware-auto-loop/`
**Tests**: Required by the feature specification and constitution; follow
red → green → refactor.

## Phase 1: Setup

- [x] T001 Verify Python ignore coverage in `.gitignore`
- [x] T002 [P] Add probe capability contract test skeleton in `tests/contract/test_probe_capability_contract.py`
- [x] T003 [P] Add probe command integration test skeleton in `tests/integration/test_probe_command.py`

## Phase 2: Foundational

- [x] T004 Add red adapter argv cases in `tests/unit/test_core_adapter.py`
- [x] T005 Add red capability and orchestration cases in `tests/unit/test_auto_loop.py`
- [x] T006 Run T002-T005 and record the expected red failures before production edits

## Phase 3: User Story 1 — Ground an authenticated write flow safely (P1)

**Goal**: Invoke Core probe with canonical artifacts and reach explicit
confirmation without invoking normal run.

**Independent Test**: Fake Core records one probe argv, zero run argv, preserves
credential/session references, and returns a reached/not-executed boundary.

- [x] T007 [US1] Implement `CoreAdapter.probe` in `src/verifysignal_spec/core/adapter.py`
- [x] T008 [US1] Implement the public probe command wrapper in `src/verifysignal_spec/commands/probe.py`
- [x] T009 [US1] Register probe CLI options in `src/verifysignal_spec/cli.py`
- [x] T010 [US1] Preserve first-class `sessionRef` in `src/verifysignal_spec/workspace/models.py` and `src/verifysignal_spec/workspace/validation.py`
- [x] T011 [US1] Make adapter, command, workspace, and zero-run tests green

## Phase 4: User Story 2 — Fail accurately on older Core versions (P2)

**Goal**: Negotiate exact probe v1 support and choose a safe legacy branch.

**Independent Test**: Probe-capable, discover-only, wrong-schema, and absent
capability fixtures select the documented branch.

- [x] T012 [P] [US2] Expand capability fixtures in `tests/contract/test_probe_capability_contract.py`
- [x] T013 [P] [US2] Add legacy write/read-only template assertions in `tests/unit/test_auto_loop.py`
- [x] T014 [US2] Implement `core_supports_probe` in `src/verifysignal_spec/core/contracts.py`
- [x] T015 [US2] Update `src/verifysignal_spec/templates/agent-commands/verifysignal.auto.md` to use probe, block legacy authenticated writes, retain limited read-only fallback, and remove `discover --storage-state`
- [x] T016 [US2] Run focused capability and automatic-loop tests

## Phase 5: User Story 3 — Preserve deterministic and cross-agent behavior (P3)

**Goal**: Keep probe optional and render identical safe behavior across agents.

**Independent Test**: Codex and Claude installs contain the same probe policy,
existing required-operation checks still pass, and no secret/session values are
persisted.

- [x] T017 [P] [US3] Add cross-agent rendered-template cases in `tests/integration/test_agent_template_guidance.py`
- [x] T018 [P] [US3] Add public Core smoke coverage in `tests/integration/test_probe_command.py`
- [x] T019 [US3] Keep probe outside required operations and expose optional capability helpers in `src/verifysignal_spec/core/contracts.py`
- [x] T020 [US3] Run integration installation, public-boundary, compatibility, and secret-safety regressions

## Phase 6: Polish and Cross-Cutting Validation

- [x] T021 Update Spec version consistently in `pyproject.toml` and `src/verifysignal_spec/__init__.py`
- [x] T022 Run the complete pytest suite
- [x] T023 Perform identity-neutral structural dogfood against Core's isolated reference app: discover reproduces the unauthenticated limitation, Spec-to-Core probe and run readiness create zero local resources, and one authorized normal run creates exactly one local fixture resource
- [x] T024 Mark completed tasks and validate cross-repository contract consistency in `specs/024-state-aware-auto-loop/tasks.md`

## Phase 7: Cross-Repository Structural Dogfood

- [x] T025 Add a red Spec integration invoking the separate structural dogfood against the real sibling Core
- [x] T026 Add a public-CLI dogfood runner that uses temporary canonical workspace persistence and one explicitly authorized isolated write
- [x] T027 Make local fixture entitlement trust available to both Spec and Core without weakening production trust contexts
- [x] T028 Add the dogfood to Core's cross-repository product-truth workflow
- [x] T029 Run the structural gate and stop without product edits if the result is red
- [x] T030 Run the complete Spec suite after a green structural result

## Dependencies

- Setup and Foundational phases block all stories.
- US1 supplies the adapter and command.
- US2 depends on the adapter contract but can develop template fixtures in
  parallel.
- US3 depends on the final capability semantics and template.
- Full suite and dogfood follow both repository implementations.

## Parallel Examples

- T002 and T003 cover independent contract/integration files.
- T012 and T013 cover capability and template behavior separately.
- T017 and T018 cover cross-agent and real-Core paths separately.

## Implementation Strategy

Deliver the public adapter and zero-run confirmation gate first, add exact
legacy behavior second, and finish with cross-agent/real-Core compatibility.
Identity-neutral dogfood uses Core's isolated structural twin and never depends
on a branded or production target.
