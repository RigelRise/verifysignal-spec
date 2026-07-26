# Governance

VerifySignal is an **open-core** project. This document states plainly what is
open, what is managed, and how decisions are made — so you can depend on the
boundary before you build on it.

## What is open

This repository is licensed **Apache-2.0** and is the open half of VerifySignal:

- the `verifysignal` CLI (authoring, validation gates, workflow state,
  side-effect and credential guardrails, repair orchestration);
- the project-local `.verifysignal/` workspace format;
- the agent skills and command templates installed into Claude Code and Codex;
- the versioned public contract the CLI speaks to the runtime.

You can fork it, run it, read every line, and — because the repository ships a
full fake Core — develop and test all of it without any proprietary component.

## What is managed

The execution engine, **VerifySignal Core**, is a signed package the CLI
downloads and caches after a free, no-account email unlock. It owns deterministic
browser execution, evidence capture, and redaction. It is not part of this
repository.

The two halves meet only at the versioned **`verifysignal-public-cli-json/v1`**
contract. The open CLI never imports Core internals; Core never reaches into your
workspace outside the contract. That boundary is the load-bearing promise of the
project, and it is enforced by contract tests in this repo.

## Why open-core

The open layer is where trust is earned: authoring, safety guardrails, secret
handling, and the review surface should be inspectable and forkable. The runtime
is kept managed and signed so that "green" means the same deterministic thing for
everyone — a result you can audit rather than a behavior that drifts per install.

## Decision-making

The project currently follows a **maintainer-led** model. The maintainers
([CODEOWNERS](CODEOWNERS)) are responsible for the roadmap, releases, and the
integrity of the public contract.

- **Small changes** (fixes, docs, additive tests) → open a PR.
- **Behavior, schema, CLI, or contract changes** → open an issue or discussion
  first so the design and its compatibility impact can be agreed before code.
- **Breaking changes** to the public contract, workspace format, or CLI are made
  deliberately, with a version bump and migration coverage — never silently.

Direction is tracked in the [roadmap](ROADMAP.md). As the community grows we
intend to formalize this into a documented maintainer/committer process.

## Principles

All changes are held to the project [constitution](.specify/memory/constitution.md):
public Core boundary, workspace portability, secret safety, agent-neutral
interface, and testable spec-driven delivery.
