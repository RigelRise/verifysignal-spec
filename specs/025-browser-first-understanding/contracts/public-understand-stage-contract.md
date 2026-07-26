# Contract: Public Understand Stage

## Capability Discovery

Call:

```text
verifysignal workflow info verifysignal-use-case --json
```

The response exposes:

- `stagePayloadContracts.byStage.understand`;
- `stagePayloadContracts.browserFirstUnderstanding`;
- capability identifier `browser-first-understanding/v1`;
- supported modes `repository`, `browser-first`, and `hybrid`;
- default exploration scope;
- forbidden durable browser artifacts;
- browser provider boundary;
- mutation/probe safety rule.

Clients must use this response instead of inspecting installed package source.

## Submission

Call:

```text
verifysignal workflow persist understand \
  --scope all \
  --payload <payload.json> \
  --json
```

The public command remains unchanged. The payload is mode-aware.

## Minimal Browser-First Payload

```json
{
  "understandingMode": "browser-first",
  "productSummary": "A local project tracking application.",
  "targetEnvironment": {
    "kind": "live-url",
    "locator": "http://127.0.0.1:4173/projects",
    "environment": "local",
    "reachabilityStatus": "authentication-required",
    "observedAt": "2026-07-26T18:00:00Z"
  },
  "explorationScope": {
    "allowedOrigins": ["http://127.0.0.1:4173"],
    "maxPagesOrStates": 20,
    "maxDepth": 3,
    "candidateRange": {"minimum": 3, "maximum": 5},
    "softTimeBudgetMinutes": 15,
    "readSafeOnly": true,
    "status": "complete"
  },
  "productSignals": [
    {
      "id": "projects-list",
      "kind": "surface",
      "surface": "/projects",
      "summary": "The signed-in user can view a project list.",
      "evidence": ["A Projects heading and project rows were visible."],
      "provenance": "browser",
      "observedAt": "2026-07-26T18:00:00Z",
      "confidence": "high",
      "inventoryItemRefs": ["surface-projects"]
    }
  ],
  "coverageInventory": {
    "status": "complete",
    "generatedAt": "2026-07-26T18:00:00Z",
    "gitAvailable": false,
    "sourceFilesVisited": 0,
    "sourceTraceabilityStatus": "missing",
    "items": [
      {
        "id": "surface-projects",
        "surfaceType": "route",
        "path": "/projects",
        "title": "Projects",
        "sourceRefs": [],
        "userFacing": true,
        "inventoryStatus": "covered",
        "priority": "high"
      }
    ],
    "candidateUseCases": [
      {
        "alias": "projects-list-visible",
        "surface": "/projects",
        "behavior": "Show the signed-in user's projects.",
        "sourceInventoryItems": ["surface-projects"],
        "rationale": "Core navigation and content are user-visible.",
        "confidence": "high",
        "inventorySourceStatus": "complete",
        "priority": "high",
        "requiresEnvironment": true,
        "knownRuntimeRequirements": ["baseUrl"]
      }
    ]
  }
}
```

The example is structurally minimal, not a claim that one candidate satisfies
the default desired range. A one-candidate mapping must be marked partial with a
reason unless the user explicitly narrowed the range.

## Host Browser Responsibilities

The host:

1. opens a headed browser;
2. enforces allowed origins and scope budgets;
3. pauses for user-entered authentication and explicit completion;
4. uses human-observable pacing;
5. avoids unknown or mutating controls during mapping;
6. synthesizes safe product signals;
7. keeps the browser open until summary acknowledgement.

The host may use Playwright MCP or an equivalent browser/Playwright interface.
Provider-specific output is not part of this contract.

## Proof Handoff

After candidate review:

- read-only selection follows existing specify/plan/tasks/implement/validate/run
  contracts;
- potentially mutating selection requires explicit user confirmation and public
  Core `verifysignal.probe/v1`;
- probe may prove the pre-commit boundary but never authorizes normal run;
- missing browser/Core capabilities return partial or blocked state.
