# Specs — how VerifySignal is built

VerifySignal is developed **spec-first**. Each feature starts as a specification
(problem, user scenarios, acceptance criteria) governed by the project
[constitution](../.specify/memory/constitution.md), then a plan, then tasks, then
code — with contract tests pinning the public boundary at every step.

Most feature specs stay local to keep the repository focused. A curated set is
published here as a window into the design history and method:

- [`009-golden-path-productization/`](009-golden-path-productization/)
- [`010-golden-path-onboarding/`](010-golden-path-onboarding/)
- [`023-auto-loop/`](023-auto-loop/)

Each published spec contains at least `spec.md` (with a **Constitution Alignment**
section and prioritized user stories), `plan.md`, and `tasks.md`; larger features
add `data-model.md`, `research.md`, `contracts/`, and `checklists/`.

This is the transparency counterpart to the open-core boundary: you can see not
just *what* VerifySignal does, but *how* each capability was reasoned about before
it shipped.
