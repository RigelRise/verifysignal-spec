# Implementation Plan: Browser-First Product Understanding

**Branch**: `025-browser-first-understanding` | **Date**: 2026-07-26 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/025-browser-first-understanding/spec.md`

## Summary

Extend VerifySignal Spec's existing understand stage so a host agent can map a
live HTTP(S) product without repository access, persist safe structured
observations in the project-local workspace, rank three to five candidate
journeys when observable, and hand one user-approved journey to the existing
deterministic Core workflow.

The implementation is additive. It introduces a versioned public
`browser-first-understanding/v1` contract, mode-aware normalization and
persistence, age-based browser freshness, generic understanding documents, and
shared agent guidance for bounded headed exploration and assisted login.
Playwright MCP or an equivalent host browser performs exploration; Spec does not
add a browser runtime or private Core integration. The Codex and Claude
adapters install the managed browser capability once in the selected agent's
user scope through that agent's public MCP command. Project configuration
remains a backward-compatible fallback, while an integration-aware invocation
renderer keeps Codex `$verifysignal-*` and Claude Code
`/verifysignal-*` guidance distinct.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: Existing Typer, Rich, PyYAML, Pydantic, pathspec,
packaging, cryptography, standard library URL/date/path handling, bundled agent
templates, and `tomlkit` for comment-preserving project Codex configuration
**Storage**: Existing target-directory `.verifysignal/` YAML and Markdown
workspace artifacts using the compatible `verifysignal-spec-product-context/v1`
schema
**Testing**: pytest unit, contract, integration, CLI, template-installation,
secret-safety, non-Git workspace, regression, and sibling-Core smoke tests
**Target Platform**: macOS/Linux local CLI with Codex, Claude, or another host
capable of providing a headed Playwright-compatible browser
**Project Type**: Packaged Python CLI and integration-neutral workflow/template
layer
**Performance Goals**: Browser payload normalization and validation complete
under 50 ms; workflow capability inspection remains under 500 ms; no added
latency to repository understanding beyond additive field checks
**Constraints**: Public Core CLI JSON only; no private imports; no embedded
browser runtime; same-origin read-safe mapping; no raw browser captures or
secret values in durable state; user-scoped agent configuration only through
the agent's public MCP command; one selected use case maps to one run request
**Scale/Scope**: Default maximum 20 meaningful pages/states, depth 3, three to
five candidates, one approved proof, and a 15-minute host exploration budget
**Public Contract Impact**: `workflow info` gains an `understand` stage payload
contract and `browserFirstUnderstanding` capability projection. Existing
repository persistence inputs and `product-context/v1` remain valid. Existing
command fields keep their schemas but render values using the selected
integration's native invocation syntax. Browser candidates gain additive
grounding and transition metadata, validation readiness identifies structural
scope, and managed MCP configuration invokes a Spec-owned isolated launcher.

## Constitution Check

- **Public Core boundary**: PASS. Exploration creates Spec-owned portable input;
  deterministic discover/probe/run behavior crosses only documented Core CLI
  JSON boundaries. Potentially mutating proof requires public probe v1.
- **Project-local workspace portability**: PASS. Browser-first engagements work
  in non-Git directories and persist only under `.verifysignal/`.
- **Secret safety**: PASS. URL query values, fragments, credentials, cookies,
  storage state, raw DOM/snapshots, screenshots, traces, response bodies, and
  form values are rejected or omitted.
- **Agent-neutral interface**: PASS. A shared public payload contract and
  template define host behavior without making MCP state canonical. Integration
  adapters own user-scoped registration through public host commands,
  compatible project fallback, and invocation syntax.
- **Testable spec-driven delivery**: PASS. Each user story maps to focused
  contract/integration coverage, regression tests, and a local live fixture.

## Project Structure

### Documentation

```text
specs/025-browser-first-understanding/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── browser-understanding-persistence-contract.md
│   └── public-understand-stage-contract.md
├── checklists/
│   └── requirements.md
└── tasks.md
```

### Source Code

```text
src/verifysignal_spec/
├── integrations/
│   ├── base.py
│   ├── invocation.py
│   └── mcp.py
├── templates/
│   ├── agent_guidance.py
│   ├── agent-commands/
│   │   └── verifysignal.understand.md
│   └── workspace/
│       └── product-context.yaml
├── workflows/
│   ├── browser_understanding.py
│   ├── coverage_inventory.py
│   ├── first_run.py
│   ├── models.py
│   ├── prerequisites.py
│   ├── stage_contracts.py
│   ├── stage_documents.py
│   └── stage_persistence.py
└── workspace/
    ├── product_context.py
    └── repository.py

tests/
├── contract/
│   ├── test_browser_first_understanding_contract.py
│   └── test_workflow_stage_persistence_contract.py
├── integration/
│   ├── test_agent_template_guidance.py
│   ├── test_browser_first_understanding.py
│   ├── test_understanding_onboarding.py
│   └── test_workflow_understand.py
└── unit/
    ├── test_browser_understanding.py
    ├── test_understanding_freshness_metadata.py
    └── test_workflow_prerequisites.py
```

**Structure Decision**: Extend the existing workflow persistence, freshness,
document, inventory, and shared-template layers. Add one small pure
normalization module for browser payload safety. Keep browser execution in the
host integration and Core execution in the sibling Core repository.

## Existing Behavior Context

- **Related features/specs**: Existing repository understanding and inventory
  onboarding, Spec 023 automatic loop, Spec 024 state-aware pre-commit probe,
  public workflow contracts, and project-local workspace validation.
- **Affected prior behavior**: understand-stage payload normalization and
  persistence, product-context rendering, readiness/freshness messages, first-run
  candidate selection, workflow-info output, agent command installation, and
  package version.
- **Regression validation**: Existing repository-understanding, workflow
  persistence, first-run, secret-safety, integration portability, and complete
  pytest suites remain green.
- **Intentional behavior changes**: Understand persistence is mode-aware;
  non-Git browser engagements are first-class; freshness and user-facing copy
  use generic product understanding; workflow info includes understand.
- **Cross-repository boundary**: No VerifySignal Core production change is
  planned. Validate against the public stateful probe contract from the isolated
  Core 018 worktree. The release gate was subsequently satisfied and
  revalidated on Core main merge `6ea5d7f`, which advertises exact public
  `verifysignal.probe/v1`.
- **Backend boundary**: No backend change. Browser observations stay local and
  existing telemetry does not transmit their contents.

## Phase 0: Research

Decisions in [research.md](./research.md):

- Host-owned headed browser exploration is separated from Spec-owned durable
  understanding and Core-owned deterministic proof.
- Mode-aware additive fields preserve `product-context/v1`.
- Browser observations are normalized into safe structured signals; raw captures
  never become workspace artifacts.
- Coverage inventory remains the downstream compatibility bridge.
- Browser freshness is age-based; Git checks apply only when mode/provenance
  includes repository evidence.
- The understand contract is public and versioned through workflow info.

## Phase 1: Design

- [data-model.md](./data-model.md) defines mode, target environment, exploration
  scope, product signals, provenance, inventory extensions, and invariants.
- [contracts/public-understand-stage-contract.md](./contracts/public-understand-stage-contract.md)
  defines discovery and submission through public workflow commands.
- [contracts/browser-understanding-persistence-contract.md](./contracts/browser-understanding-persistence-contract.md)
  defines normalization, forbidden data, compatibility, and persistence results.
- [quickstart.md](./quickstart.md) defines red/green, regression, agent-template,
  non-Git, and sibling-Core validation.

## Implementation Phases

1. Add failing tests for the public contract, safe normalization, mode-aware
   persistence, freshness, non-Git onboarding, and agent behavior.
2. Add browser-understanding value objects/normalizers and extend public stage
   contracts and model literals.
3. Extend persistence and product context with additive fields and compatibility
   aliases; make freshness and documents mode-aware.
4. Update shared agent templates/integration metadata with bounded exploration,
   assisted authentication, candidate review, and probe-only mutation rules.
5. Bump Spec minor version to `0.21.0`, update public documentation, and validate
   all regressions plus the Core 018 public contract.
6. Add the Codex parity correction: project-scoped MCP installation,
   integration-native invocation rendering, upgrade compatibility, and a
   `0.21.1` patch release.
7. Harden the smoke-tested integration through lossless bounded aliases,
   strict field-path validation, explicit journey grounding, authoritative
   side-effect ranking, inventory-first Golden Path acceptance, isolated pinned
   Playwright MCP execution, and explicit structural/runtime readiness copy.
8. Close the Codex startup regression with a red/green stdio acceptance
   boundary: install the pinned MCP provider during integration setup, execute
   only the verified user-cache binary during agent startup, and require a real
   `initialize` plus `tools/list` handshake in pull-request CI.
9. Convert every failed manual PR smoke observation into an explicit
   regression: require the Codex server at session startup, initially query its
   tools through a trusted ephemeral app-server thread, distinguish
   pre-observation host failure from product state, make prerequisite/runtime
   recovery unambiguous, and prove RED on the original PR head before GREEN.
   Phase 11 replaces that trust-assisted acceptance with clean user-scope
   startup.
10. Close the false browser-unavailable regression by defining MCP-first
    backend selection, distinguishing Codex's Browser Plugin inventory from
    project MCP discovery, and allowing setup/restart recovery only after both
    inventories lack usable navigation.
11. Close the clean-user startup regression by registering the managed MCP
    through Codex and Claude's public user-scope commands, proving plain agent
    startup without trust/config overrides, and keeping local backend setup
    outside the agent launch boundary.
12. Close protected validation regressions by preserving packaged-runtime trust
    ownership and materializing Core-required side-effect policy modes.
13. Close the selector/side-effect attribution regression across Core and Spec:
    consume public blocking authoring-warning metadata statically, fail Spec
    results on policy violations, persist a secret-safe policy snapshot, block
    unchanged reruns, require explicit owner review for policy changes, and
    restore strict pass only after a clean rerun.

## Post-Design Constitution Check

All gates remain PASS after design. The feature adds no browser inference or
deterministic validation runtime. Integration setup installs the host-owned
pinned Playwright MCP package into a private versioned user cache; the small
stdio launcher executes that verified cache entry without network resolution,
isolates provider output, and cannot persist provider output into the target
project. The feature stores no provider-specific capture, keeps durable product
state project-local, preserves repository mode, and treats public Core
capability detection as a release gate rather than implementing Core behavior
in Spec. The new readiness and rerun behavior consumes only public Core contract,
run, and report-inspection fields; it does not import Core internals or navigate
during static validation. Agent MCP registration uses only the selected host's documented public
MCP command, preserves conflicting user-owned entries, and records no
credentials. The real Codex acceptance invokes only app-server initialization,
an ephemeral read-only thread, and MCP status inspection; it does not send a
model turn or navigate a product.

## Complexity Tracking

No constitution violations require justification.
