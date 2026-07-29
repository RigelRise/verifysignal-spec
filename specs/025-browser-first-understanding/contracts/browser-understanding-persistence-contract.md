# Contract: Browser Understanding Persistence

## Normalization Order

Before writing any workspace artifact, Spec:

1. resolves legacy mode aliases and defaults;
2. validates the mode-specific required fields;
3. sanitizes the target URL and allowed origins;
4. applies and validates exploration-scope defaults;
5. validates product-signal shape and forbidden data;
6. resolves bounded aliases and rejects conflicts/unknown fields;
7. validates signal, inventory, candidate, and grounding references;
8. derives compatibility fields and understanding metadata;
9. runs existing secret-value validation;
10. writes canonical project-local artifacts.

Any failing step returns an invalid persistence result or existing public error
with the exact failing field path and without partially writing browser content.

## Bounded Aliases

The public compatibility aliases are:

- inventory `surface`, `summary`, `kind`, and `status`;
- candidate `id`, `title`, `expectedOutcome`, and `sideEffects.class`;
- signal `inventoryReferences`;
- top-level `candidateUseCases` when the canonical nested field is absent.

When canonical and alias fields both exist they must be equivalent. All other
unknown fields fail validation rather than being ignored.

## Grounding

- Candidate grounding values are `observed`, `partial`,
  `authentication-required`, `blocked`, and `unknown`.
- An observed multi-surface journey requires a referenced transition signal
  with matching `fromSurface` and `toSurface`.
- An authentication-required candidate requires a referenced
  runtime-requirement or gap signal.
- Legacy candidates without grounding normalize to `unknown` and are not safe
  for automatic first-run guidance.

## URL Rules

- Schemes: `http` or `https`.
- Credentials in authority: rejected.
- Query and fragment: discarded from durable locator.
- Origin: lowercase scheme/host with explicit non-default port retained.
- Path: retained and normalized to begin with `/`.
- Allowed origins: normalized and deduplicated.
- Redirected origins: not added implicitly.

## Forbidden Durable Fields

Keys are rejected case-insensitively when they represent raw:

- DOM or HTML;
- browser/MCP snapshots;
- screenshot image data or paths;
- traces, HAR, network response bodies, or request/response headers;
- cookies, local/session storage, or storage-state content/path;
- credentials, authorization values, access/refresh/session tokens;
- entered form values;
- raw URL query strings or query parameter values.

Short synthesized evidence text is allowed after existing secret-value
validation.

## Compatibility Projection

For `browser-first`:

- `workspaceKind` defaults to `engagement`;
- `repositorySummary` mirrors `productSummary` for legacy readers;
- `localStartInstructions` remains an empty string unless supplied safely;
- `knownRuntimeRequirements` includes a structured `baseUrl` requirement derived
  from the sanitized target locator;
- Git fields remain unavailable without creating an error;
- inventory candidates remain available through `candidateUseCases`.

For `repository`, current persistence is unchanged.

For `hybrid`, repository and browser fields coexist. Conflicting evidence sets
`provenanceTraceabilityStatus=conflicted` and records a gap.

## Status Rules

- `complete`: requested scope completed and candidate minimum met.
- `partial`: scope/coverage/authentication limit reached, candidate minimum not
  met, or recoverable capability unavailable.
- `blocked`: observed product evidence exists but cannot safely progress.
- a host browser failure before the first product signal is not a persistable
  understanding status; persistence rejects zero-signal browser payloads.
- Existing `stale` status remains a later freshness evaluation.

The system never upgrades a caller's partial/blocked evidence to complete.

## Idempotence

Given the same normalized payload and existing inventory scope, repeated
persistence produces equivalent target, scope, signal IDs, inventory items,
candidates, provenance, and gaps. Timestamps supplied by the caller remain
stable; generated-at behavior follows existing inventory merge semantics.

## Write Atomicity and Secret Safety

Canonical product context and understanding Markdown are written only after
normalization succeeds. Existing product-context secret validation remains the
final guard. Browser session artifacts are never copied into `.verifysignal/`.
