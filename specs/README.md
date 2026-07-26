# Specs: how VerifySignal is built

VerifySignal is developed spec-first. Each feature starts as a specification
(problem, user scenarios, acceptance criteria) governed by the
[constitution](../.specify/memory/constitution.md), then a plan, then tasks, then
code, with contract tests pinning the public boundary at every step.

Most feature specs stay local. A curated set is published here as a window into
the design method:

- [`009-golden-path-productization/`](009-golden-path-productization/)
- [`010-golden-path-onboarding/`](010-golden-path-onboarding/)
- [`023-auto-loop/`](023-auto-loop/)

Each holds at least `spec.md` (with a Constitution Alignment section and
prioritized user stories), `plan.md`, and `tasks.md`. Larger features add
`data-model.md`, `research.md`, `contracts/`, and `checklists/`.

You can see not just what VerifySignal does, but how each capability was reasoned
about before it shipped.
