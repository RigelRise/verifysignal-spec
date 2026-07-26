# Governance

VerifySignal is open-core. This states what is open, what is managed, and how
decisions are made, so you can depend on the boundary before you build on it.

## What is open

This repository is Apache-2.0 and is the open half of VerifySignal:

- the `verifysignal` CLI (authoring, gates, workflow state, side-effect and credential guardrails, repair);
- the project-local `.verifysignal/` workspace format;
- the agent skills for Claude Code and Codex;
- the versioned public contract the CLI speaks to the runtime.

You can fork it, run it, read every line, and (because the repo ships a full fake
Core) test all of it without any proprietary component.

## What is managed

The execution engine, VerifySignal Core, is a signed package the CLI downloads
after a free, no-account email unlock. It owns deterministic execution, evidence
capture, and redaction. It is not part of this repository.

The two halves meet only at the `verifysignal-public-cli-json/v1` contract. The
open CLI never imports Core internals, and that boundary is enforced by contract
tests here.

## Why open-core

Authoring, safety guardrails, secret handling, and the review surface should be
inspectable and forkable. The runtime stays managed and signed so that "green"
means the same deterministic thing for everyone, not a behavior that drifts per
install.

## Decisions

The project is maintainer-led. The maintainers ([CODEOWNERS](CODEOWNERS)) own the
roadmap, releases, and the integrity of the public contract.

- Small changes (fixes, docs, additive tests): open a PR.
- Behavior, schema, CLI, or contract changes: open an issue or discussion first, so the design and its compatibility impact are agreed before code.
- Breaking changes to the contract, workspace format, or CLI are made deliberately, with a version bump and migration coverage, never silently.

Direction is tracked in the [roadmap](ROADMAP.md). As the community grows we
intend to formalize a documented maintainer process.

All changes are held to the project
[constitution](.specify/memory/constitution.md): public Core boundary, workspace
portability, secret safety, agent-neutral interface, and testable spec-driven
delivery.
