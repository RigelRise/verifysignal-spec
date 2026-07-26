# Research: State-Aware Automatic Authoring Loop

## Decision 1: Negotiate exact probe compatibility

**Decision**: `core_supports_probe` returns true only for operation `probe`,
schema `verifysignal.probe/v1`, schema version 1.

**Rationale**: Operation-name presence alone cannot guarantee the response shape
or safety semantics.

**Rejected alternative**: Infer probe from Core version numbers. Distribution
versions are less precise than machine-readable capability metadata.

## Decision 2: Keep probe optional

**Decision**: Do not add probe to `REQUIRED_OPERATIONS`.

**Rationale**: Existing deterministic workflows and read-only use cases must
continue to work with older Core versions.

**Rejected alternative**: Raise the global minimum Core requirement. That would
break unrelated workflows for a convenience-path capability.

## Decision 3: Mirror the run adapter

**Decision**: Add `CoreAdapter.probe` using one run-request positional, repeated
ordered `--skill` flags, presentation flags, entitlement receipt, and `--json`.

**Rationale**: Probe intentionally consumes the same artifacts and protected
runtime trust path as run.

**Rejected alternative**: Generate a temporary discover skill or synthesize
credentials on argv. Both duplicate Core semantics and increase secret risk.

## Decision 4: Treat sessionRef as a reference only

**Decision**: Preserve the run-request `sessionRef` object through workspace
loading, validation, and rendering; never resolve its key or path in Spec.

**Rationale**: Core already owns environment/local-config resolution and browser
storage import. Spec's public boundary prohibits private runtime behavior.

**Rejected alternative**: Add a Spec `--storage-state` flag. It would create a
second session contract and repeat the unsupported guidance that caused the
original failure.

## Decision 5: Fail closed for legacy authenticated writes

**Decision**: When probe is unavailable, authenticated write or
external-notification flows stop with upgrade guidance. Authenticated read-only
flows may continue using discover/source-only with an explicit page-state
limitation.

**Rationale**: Static discover cannot cross login or prove protected form
targets, but it can still help with public/read-only entry-state targets.

**Rejected alternative**: Always continue source-only. That recreates false
confidence and lengthy work before the inevitable protected-route block.

## Decision 6: Preserve explicit write confirmation

**Decision**: A successful probe allows the loop to present a confirmation gate;
it never invokes normal run automatically.

**Rationale**: Probe proves selectors and boundary safety, not user authorization
to create a real resource.

**Rejected alternative**: Treat probe success as approval. Diagnostic success
and authorization are distinct decisions.

## Decision 7: Dogfood against an identity-neutral structural twin

**Decision**: Use Core's isolated local reference application for dogfood. It
reproduces only the authenticated state transitions and commit boundary, with no
real product name, domain, copy, assets, styling, or visual identity.

**Rationale**: The capability under test is stateful pre-commit execution. A
neutral structural twin proves zero commits under probe and one commit under
normal run deterministically, without coupling Spec to a product brand,
production data, external availability, or cleanup policy.

**Rejected alternative**: Dogfood against a branded real product. It increases
identity, credential, data, and cleanup risk without adding contract coverage.
