<!-- SPECKIT START -->
Follow `.specify/memory/constitution.md` as the governing project rules.
For additional context about technologies to be used, project structure,
shell commands, and other important information for the active feature, read
`specs/026-hermetic-test-readiness/plan.md`.

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
- Before finishing code, behavior, CLI, schema, template, or packaging changes,
  check the current package version from `pyproject.toml` and
  `src/verifysignal_spec/__init__.py`.
- Decide whether the completed change requires a version bump. Use patch for
  fixes and internal-compatible refinements, minor for new backwards-compatible
  capabilities, and major for intentional breaking changes.
- If a bump is required, update all version declarations consistently and note
  the old and new versions in the final response. If no bump is required, state
  why the version remains unchanged.
