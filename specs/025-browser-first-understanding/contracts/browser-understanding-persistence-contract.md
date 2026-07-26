# Contract: Browser Understanding Persistence

## Normalization Order

Before writing any workspace artifact, Spec:

1. resolves legacy mode aliases and defaults;
2. validates the mode-specific required fields;
3. sanitizes the target URL and allowed origins;
4. applies and validates exploration-scope defaults;
5. validates product-signal shape and forbidden data;
6. normalizes the existing coverage inventory;
7. derives compatibility fields and understanding metadata;
8. runs existing secret-value validation;
9. writes canonical project-local artifacts.

Any failing step returns an invalid persistence result or existing public error
without partially writing browser content.

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
- `blocked`: no meaningful safe observation can be persisted.
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
