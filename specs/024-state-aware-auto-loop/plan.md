# Implementation Plan: State-Aware Automatic Authoring Loop

**Branch**: `024-state-aware-auto-loop` | **Date**: 2026-07-26 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/024-state-aware-auto-loop/spec.md`

## Summary

Extend VerifySignal Spec to consume Core's optional experimental
`verifysignal.probe/v1` operation through the public CLI JSON boundary. The
automatic loop uses probe for authenticated write/external-notification flows,
preserves credential and session references out of band, requires a
reached-but-not-executed boundary before confirmation, and fails accurately
when an older Core lacks the capability.

The implementation adds a thin adapter/command, exact schema-based capability
detection, first-class `sessionRef` preservation, and shared agent-template
guidance. It removes the invented `discover --storage-state` suggestion while
leaving deterministic workflows and discover-only read paths compatible.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: Existing Typer, Rich, PyYAML, Pydantic, packaging,
cryptography, standard-library subprocess/path handling, and bundled templates;
no new dependency
**Storage**: Existing target-project `.verifysignal/` workspace. Probe output
is returned to the invoking agent and is not persisted as a new artifact
**Testing**: pytest unit, contract, integration, fake-Core CLI fixtures, real
public Core CLI smoke checks, and integration-template installation tests
**Target Platform**: macOS/Linux local CLI with Codex and Claude integrations
**Project Type**: Packaged Python CLI and agent-integration template layer
**Performance Goals**: Capability checks remain local and under 500 ms with a
cached Core; adapter overhead remains under 50 ms excluding Core execution
**Constraints**: Public Core CLI JSON only. No private imports, undocumented
fields, credential/session values, secret files, or direct managed-workspace
writes. One use case maps to one run request
**Scale/Scope**: One probe invocation per use case attempt, ordered repeated
skill flags, two bounded target-repair attempts, optional capability negotiation
**Public Contract Impact**: Spec consumes, but does not redefine,
`verifysignal.probe/v1`. Compatibility is exact on operation name, schema, and
schema version. Probe remains optional and is not added to required operations.

## Constitution Check

- **Public Core boundary**: PASS. `CoreAdapter` shells out to documented CLI
  JSON and parses only public envelopes.
- **Project-local workspace portability**: PASS. Existing run requests, skills,
  credential refs, and session refs remain canonical.
- **Secret safety**: PASS. Adapter argv carries paths/references only; no values
  are copied into persisted state or guidance.
- **Agent-neutral interface**: PASS. One shared template renders equivalent
  Codex and Claude behavior; deterministic CLI flows remain unchanged.
- **Testable spec-driven delivery**: PASS. Adapter, capability, workspace,
  template, compatibility, and secret-safety behavior receive focused tests.

## Project Structure

### Documentation

```text
specs/024-state-aware-auto-loop/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── core-probe-adapter-contract.md
│   └── automatic-loop-decision-contract.md
└── tasks.md
```

### Source Code

```text
src/verifysignal_spec/
├── cli.py
├── commands/
│   └── probe.py
├── core/
│   ├── adapter.py
│   └── contracts.py
├── templates/agent-commands/
│   └── verifysignal.auto.md
└── workspace/
    ├── models.py
    └── validation.py

tests/
├── contract/test_probe_capability_contract.py
├── integration/test_probe_command.py
├── integration/test_agent_template_guidance.py
└── unit/
    ├── test_core_adapter.py
    └── test_auto_loop.py
```

**Structure Decision**: Extend the existing adapter/command/template layers.
Core remains the sole browser runtime and safety authority; Spec owns only
capability negotiation, workspace references, orchestration guidance, and
confirmation policy.

## Existing Behavior Context

- **Related features/specs**: Spec 023 automatic loop, optional discover
  capability, Core executable-contract projection, credential hints,
  side-effect lifecycle, explicit write confirmation, and session-capable Core
  run requests.
- **Affected prior behavior**: `CoreAdapter`, CLI command registration,
  optional capability helpers, automatic-loop template rendering, workspace
  validation, Codex/Claude installation, and Core compatibility fixtures.
- **Regression validation**: Existing discover, run, staged workflow,
  workspace, integration installation, compatibility, and secret-safety suites
  remain green.
- **Intentional behavior changes**: Authenticated write grounding prefers probe.
  Older Core blocks that path with upgrade guidance. Unsupported
  `discover --storage-state` guidance is removed.
- **Dogfood boundary**: Use the identity-neutral Core reference application,
  while preserving the existing minimal smoke example. Add a separate
  structural dogfood reproducing split authentication, protected form, required
  media through an asynchronous modal, commit boundary, and success redirect.
  Exercise it through Spec's public CLI against the real sibling Core. The
  dogfood invocation authorizes one ephemeral loopback write; if Spec readiness
  returns a structured confirmation id, the runner forwards that id. Core
  remains deterministic and unaware of Spec. Do not use a real product name,
  domain, copy, assets, or visual identity.

## Phase 0: Research

Decisions in [research.md](./research.md):

- Probe is optional and exact-schema negotiated.
- Adapter mirrors run's public path/receipt handling.
- `sessionRef` is preserved as an authored reference, never resolved by Spec.
- Legacy authenticated writes block; authenticated read-only flows may retain
  limited discover/source-only behavior.
- Probe success does not authorize a developer-controlled target run; explicit
  developer confirmation remains required. The isolated dogfood command itself
  authorizes its single process-local write.

## Phase 1: Design

- [data-model.md](./data-model.md) defines capability, invocation, outcome,
  session reference, and orchestration decision.
- [contracts/core-probe-adapter-contract.md](./contracts/core-probe-adapter-contract.md)
  defines adapter argv and response handling.
- [contracts/automatic-loop-decision-contract.md](./contracts/automatic-loop-decision-contract.md)
  defines capability branches and safety gates.
- [quickstart.md](./quickstart.md) defines red/green tests and cross-repository
  validation.

## Post-Design Constitution Check

All constitution gates remain PASS. The feature stays additive, uses the public
Core boundary only, introduces no persistence or dependency, and keeps
cross-agent output generated from one template.

## Complexity Tracking

No constitution violations require justification.
