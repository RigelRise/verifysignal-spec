# Changelog

## Unreleased

### Open-source presentation & packaging

- Rewrote the README around a hero, badges, an evidence-first "see a real run"
  section, a Mermaid architecture diagram, an open-core boundary table, a
  project-status matrix, a comparison table, and a "what it is not" section.
- Added community-health files: `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`,
  `SECURITY.md`, `GOVERNANCE.md`, `CODEOWNERS`, issue/PR templates, and
  Dependabot.
- Added an `examples/` directory with two runnable use cases committed with their
  evidence bundles (`qa-report/v1`), including a write-flow example, guarded by a
  contract test.
- Made the package PyPI-ready — `[project.urls]`, classifiers, and keywords in
  `pyproject.toml` — plus a Trusted-Publishing release workflow and a
  version-consistency test.
- Added brand assets under `docs/assets/`, a documentation index, and a
  `ROADMAP.md`.
- No changes to CLI behavior, schemas, templates, or the public Core contract.

## 0.19.0 - 2026-07-13

- Absorbed Core's new experimental crystallization capability, contract-first and
  additively, following the `discover` (feature 016) precedent:
  - Added `CoreAdapter.crystallize(run_dir, out=..., entitlement_receipt=...)`
    for Core's entitlement-protected `crystallize` operation
    (`verifysignal.crystallize/v1`).
  - Added `record`/`replay` parameters to `CoreAdapter.run()` (`run` stays on
    `verifysignal.run/v1`; the flags are additive).
  - Added `core_supports_crystallize()` optional-capability probe; `crystallize`
    is intentionally NOT part of `REQUIRED_OPERATIONS`, so an older Core without
    it stays compatible.

## 0.10.2 - 2026-06-08

- Fixed Core public contract projection for the current `data.sections` shape:
  network match keys now come from `awaitNetwork.match.keys`, field descriptors
  prefer `path`, artifact schema versions are projected separately from section
  schema versions, credential sources come from `credentialRefs.supportedSources`,
  and browser target composition follows Core-declared metadata.
- Added compatibility findings for divergent canonical and legacy contract
  shapes while keeping canonical Core metadata authoritative.

## 0.10.1 - 2026-06-07

- Fixed implement persistence and authoring coherence checks to use the Core
  public browser contract when validating executable browser intent and network
  evidence.

## 0.10.0 - 2026-06-06

- Added Core public contract driven authoring for run requests, browser skills,
  credential references, report coverage interpretation, and agent guidance.
- Added fail-closed blockers for missing or malformed Core executable contract
  sections and legacy executable artifact schemas.
- Kept Core contract projections ephemeral per command; no Core contract
  snapshots are persisted into target `.verifysignal/` workspaces.
