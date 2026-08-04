<!-- SPECKIT START -->
Follow `.specify/memory/constitution.md` as the governing project rules.
For additional context about technologies to be used, project structure,
shell commands, and other important information for the active feature, read
`specs/027-rename-public-interface/plan.md`.

Write project documentation, specs, plans, tasks, generated agent instructions,
runtime guidance, run requests, and skills in English.

Use pt-BR for chat with the project owner unless they ask otherwise.

VerifySignal Spec is the open interface layer over VerifySignal Core. Keep Core
interaction behind the documented public CLI JSON contract; do not import
private VerifySignal Core packages or read undocumented report internals.

Keep target-project state under `.verifysignal/`. Use cases reference exactly one
run request, while skills are decoupled reusable artifacts that may be shared by
multiple run requests.
<!-- SPECKIT END -->

## Delivery Guardrails

Use red/green TDD for behavior changes whenever feasible:
- Write or update the test that describes the expected behavior before changing
  production code.
- Run the focused test and confirm it fails for the expected reason (red).
- Implement the smallest coherent change that makes the focused test pass
  (green), then refactor only while keeping tests green.
- Do not weaken assertions, delete meaningful coverage, or rewrite tests merely
  to match the current implementation. If the expected behavior changed, update
  the spec/plan first and make that intent explicit.
- If a true red step cannot be demonstrated because of tooling or harness
  limits, state the reason before implementation and add the closest regression
  coverage available.

Preserve existing features by default:
- Treat existing tests, documented behavior, CLI flags, schemas, templates,
  commands, run-request formats, skill formats, and workspace semantics as
  compatibility contracts.
- New changes must be additive or intentionally migrated. Do not remove,
  narrow, or silently replace existing behavior without explicit product
  direction and regression coverage for the old and new paths.
- When touching shared code, run focused tests for the changed behavior plus
  relevant regression tests for adjacent behavior that could be affected.

Evaluate version impact after changes:
- Version bumps are AUTOMATED. When a PR merges to `main`, the version-bump
  workflow classifies the merged-PR title (`!` -> major; feat -> minor;
  fix/perf -> patch; docs/test/ci/chore/refactor/build/style -> none), rewrites
  `pyproject.toml`, `src/verifysignal_spec/__init__.py`, and `CHANGELOG.md`
  together, tags `vX.Y.Z`, and the tag triggers the PyPI release.
- Do NOT hand-bump the version in a PR. Declare the intended release class
  through the PR title (enforced by the pr-title check) and the template's
  "Type of change" checkbox. If a hand-bump lands anyway, the automation
  reconciles by tagging the declared version instead of bumping again.
- Still state the expected version impact in the final response: which class
  the PR title carries and why (or why it correctly classifies as none).
