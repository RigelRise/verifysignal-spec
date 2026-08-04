# Tasks: Canonical VerifySignal Distribution

**Input**: Design documents from `specs/027-rename-public-interface/`
**Tests**: Required; every automatable behavior uses separate red and green commits. Manual registry/repository transitions require captured evidence.

## Phase 1: Setup

- [ ] T001 Confirm clean worktrees and branch bases for all three release stages against `specs/027-rename-public-interface/contracts/release-cutover.md`
- [X] T002 Inventory all distribution, import, executable, schema, workspace, environment, role, command, skill, repository, and publisher identities in `specs/027-rename-public-interface/contracts/public-identity-compatibility.md`

## Phase 2: Foundational compatibility guardrails

- [X] T003 Add a frozen compatibility inventory test in `tests/contract/test_public_identity_compatibility.py`
- [X] T004 Add package metadata and dual-entry-point expectations in `tests/contract/test_distribution_identity.py`
- [X] T005 Add release-stage and publisher-identity expectations in `tests/contract/test_release_migration_contract.py`
- [X] T006 Run focused tests red and commit the test-only compatibility baseline

## Phase 3: User Story 3a - Final old-name release (P2)

**Goal**: Publish a final migration-aware `verifysignal-spec` patch without breaking old installs.

**Independent Test**: Old artifact metadata remains old-name, both commands work, and public migration notice names the canonical install path.

- [X] T007 [US3] Add a failing final-release migration-notice contract in `tests/contract/test_release_migration_contract.py` on `fix/announce-verifysignal-distribution`
- [X] T008 [US3] Run the notice contract red and commit tests only
- [X] T009 [US3] Add the migration notice to `README.md` and `docs/installation.md`
- [X] T010 [US3] Run focused and full tests green, build/check the old-name artifact, and commit implementation
- [X] T011 [US3] Push and open the old-name patch PR with expected 0.22.1 release evidence

## Phase 4: User Story 1 - Canonical distribution (P1)

**Goal**: Publish `verifysignal` while preserving the complete compatibility surface.

**Independent Test**: Canonical wheel metadata, both commands, stable import, and frozen identities pass in an isolated environment.

- [X] T012 [US1] Bring the final old-name migration commit into `027-rename-public-interface` without losing feature artifacts
- [X] T013 [US1] Run distribution and compatibility contract tests red against the old metadata and commit the test-only change
- [X] T014 [US1] Change only the project distribution name in `pyproject.toml`
- [X] T015 [P] [US1] Update canonical install/product wording in `README.md`, `docs/installation.md`, and active guidance while retaining the live pre-rename repository URL
- [X] T016 [P] [US1] Add the canonical interface manifest alias in `src/verifysignal_spec/repos.py`
- [X] T017 [US1] Run focused tests green and commit the minimal canonical implementation
- [X] T018 [US1] Run full pytest, build, twine check, isolated dual-command/import smoke, and Docker regression
- [ ] T019 [US1] Push and open the canonical feature PR with expected 0.23.0 release evidence

## Phase 5: User Story 3b - Manual canonical publication gate (P2)

- [ ] T020 [US3] Create the pending PyPI trusted publisher for project `verifysignal` and repository `verifysignal-spec` immediately before merge
- [ ] T021 [US3] Merge the canonical PR only after the publisher gate and verify released 0.23.0 from an isolated environment
- [ ] T022 [US3] Rename GitHub to `RigelRise/verifysignal`, preserve the old redirect, and create the new exact trusted publisher binding

## Phase 6: User Story 3c - Post-rename canonical patch (P2)

**Goal**: Prove release automation and source metadata under the renamed GitHub identity.

**Independent Test**: Canonical source URLs and workflow environment metadata are green and 0.23.1 publishes using the new binding.

- [ ] T023 [US3] Add failing canonical repository metadata assertions in `tests/contract/test_docs_install_urls.py` and `tests/contract/test_release_migration_contract.py`
- [ ] T024 [US3] Run focused tests red and commit tests only on `fix/canonical-verifysignal-repository`
- [ ] T025 [US3] Update project URLs, public docs, issue links, release workflow URL/comment, and GitHub templates to `RigelRise/verifysignal`
- [ ] T026 [US3] Run focused/full tests, build/check, isolated install, and Docker regression green; commit implementation
- [ ] T027 [US3] Push/open the post-rename patch PR, verify automated 0.23.1, then retire the old trusted-publisher binding

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T028 Confirm the old PyPI project remains installable, unyanked, and frozen
- [ ] T029 Confirm all 47 distinct versioned schema IDs and all frozen compatibility identifiers are unchanged
- [ ] T030 Update completion and release evidence in `specs/027-rename-public-interface/tasks.md`

## Dependencies

- Phase 3 completes and 0.22.1 is verified before Phase 4 merges.
- T020 blocks canonical merge and first publication.
- Canonical 0.23.0 verification blocks GitHub rename.
- Repository rename and new publisher binding block the post-rename patch.
- Core and backend dependent PRs remain draft until 0.23.1 succeeds.

## Parallel Example

- After T013, T015 and T016 touch independent prose and resolver files while T014 changes packaging metadata.
- Post-rename docs and workflow metadata may be implemented in parallel only after T023-T024 establish the red contract.

## Implementation Strategy

Treat each publication as a separately recoverable increment. Preserve old artifacts, never advance past a failed gate, and keep tests and implementation in distinct commits for every automatable behavior.
