# Data Model: Browser-First Product Understanding

## Understanding Mode

Allowed values:

- `repository`: understanding is derived from safe source/repository inspection;
- `browser-first`: understanding is derived from a live target without source;
- `hybrid`: understanding combines repository and live-browser provenance.

Compatibility rule: absence of `understandingMode` in an existing context means
`repository`.

## Product Context Additions

The existing `verifysignal-spec-product-context/v1` document gains optional:

- `workspaceKind`: `repository`, `engagement`, or `hybrid`;
- `understandingMode`: one of the values above;
- `productSummary`: concise mode-neutral product description;
- `targetEnvironment`: a Target Environment;
- `explorationScope`: an Exploration Scope;
- `productSignals`: ordered Product Signals;
- `understanding.provenanceTraceabilityStatus`: `complete`, `partial`, or
  `conflicted`;
- `understanding.observedAt`: normalized UTC timestamp;
- `understanding.gaps`: secret-safe gap summaries.

Legacy `repositorySummary`, `localStartInstructions`, `safeInspectionPaths`,
`blockedSensitivePaths`, `knownRuntimeRequirements`, `coverageInventory`,
`candidateUseCases`, and existing `understanding` fields remain valid.

## Target Environment

- `kind`: `live-url`;
- `locator`: sanitized HTTP(S) URL containing scheme, authority, and path only;
- `origin`: normalized scheme plus authority;
- `environment`: optional user-facing label such as `local`, `staging`, or
  `production`;
- `reachabilityStatus`: `reachable`, `unreachable`, `authentication-required`,
  or `unknown`;
- `observedAt`: UTC timestamp;
- `allowedOrigins`: non-empty normalized origins; defaults to `origin`.

Invariants:

1. `locator` has no username, password, query, or fragment.
2. Every allowed origin uses HTTP(S).
3. Browser-first persistence has exactly one default allowed origin unless the
   user explicitly narrows or expands the scope.

## Exploration Scope

- `allowedOrigins`: normalized list of approved origins;
- `maxPagesOrStates`: integer 1–100, default 20;
- `maxDepth`: integer 0–10, default 3;
- `candidateRange`: object with `minimum` and `maximum`, default 3 and 5;
- `softTimeBudgetMinutes`: integer 1–60, default 15;
- `readSafeOnly`: boolean, always true during mapping;
- `excludedActions`: synthesized action classes not explored;
- `status`: `complete`, `partial`, or `blocked`;
- `stopReason`: optional stable reason when not complete.

Invariants:

1. Candidate minimum is at least 1 and not greater than maximum.
2. Candidate maximum is at most 10.
3. `readSafeOnly` cannot be false for the understand mapping pass.
4. Reaching a limit yields `partial`, not a fabricated `complete`.

## Product Signal

- `id`: stable slug unique within the product context;
- `kind`: `surface`, `state`, `transition`, `runtime-requirement`, or `gap`;
- `surface`: sanitized route or user-facing area;
- `state`: optional concise state label;
- `summary`: synthesized user-visible observation;
- `evidence`: list of short non-secret evidence summaries;
- `provenance`: `browser`, `repository`, or `hybrid`;
- `observedAt`: UTC timestamp;
- `confidence`: `high`, `medium`, or `low`;
- `inventoryItemRefs`: optional coverage inventory item IDs.

Forbidden keys/content include raw DOM/HTML, snapshots, screenshot data or
paths, traces, response bodies, cookies, storage state, headers containing
authorization, credential values, raw form values, and raw query values.

## Coverage Inventory Compatibility

Existing fields remain canonical. Browser-first semantics are:

- `generatedGitHash`: absent;
- `gitAvailable`: false;
- `sourceFilesVisited`: 0;
- `sourceTraceabilityStatus`: `missing`;
- `items[].sourceRefs`: empty or safe provenance labels;
- `candidateUseCases[].sourceInventoryItems`: coverage inventory item IDs, not
  necessarily source-code references.

Additive optional item/candidate fields may include:

- `productSignalRefs`: supporting Product Signal IDs;
- `provenance`: `browser`, `repository`, or `hybrid`;
- `sideEffectClass`: `none`, `write`, `external-notification`, or `unknown`;
- `proofStatus`: `not-selected`, `selected`, `blocked`, `passed`, or `failed`.

Legacy deserialization ignores absent additions and preserves current behavior.

## Understanding Metadata

- `generatedAt`: durable artifact generation timestamp;
- `observedAt`: latest browser observation timestamp when applicable;
- `generatedGitHash`: nullable;
- `gitAvailable`: boolean;
- `mode`: normalized Understanding Mode;
- `inventoryStatus`: `complete`, `partial`, or `stale`;
- `inventoryScope`: requested persistence scope;
- `candidateCount`: normalized count;
- `sourceTraceabilityStatus`: existing compatibility field;
- `provenanceTraceabilityStatus`: `complete`, `partial`, or `conflicted`;
- `partialInventoryReasons`: list;
- `gaps`: list;
- `staleReasons`: list.

Freshness invariant: age applies to `generatedAt` for every mode. Git
availability/hash is required only when repository provenance claims it.

## Understanding Persistence Request

- `stage`: `understand`;
- `scope`: `all`, `continue`, or another existing supported inventory scope;
- `payload.understandingMode`: explicit for browser-first/hybrid;
- mode-specific fields described by the public contract.

Mode requirements:

- `repository`: legacy `repositorySummary`, `localStartInstructions`,
  `coverageInventory`, and Git hash/unavailable reason;
- `browser-first`: `productSummary`, `targetEnvironment`, `explorationScope`,
  `productSignals`, and `coverageInventory`;
- `hybrid`: repository requirements plus browser target/scope/signals.

## Persistence Result

The existing `verifysignal-spec-workflow-stage-persistence-result/v1` remains.
Its `understandingOnboarding` projection gains optional:

- `understandingMode`;
- `workspaceKind`;
- `targetEnvironment`;
- `productSignalCount`;
- `provenanceTraceabilityStatus`;
- `gaps`.

No secret or raw browser evidence appears in the result.
