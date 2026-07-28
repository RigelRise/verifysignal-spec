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
- complete nested field definitions, enums, required fields, bounded aliases,
  and one canonical browser-first example.

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
    "status": "partial",
    "partialInventoryReasons": [
      "Only one read-safe journey was observed."
    ]
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
    },
    {
      "id": "authenticated-session",
      "kind": "runtime-requirement",
      "surface": "/sign-in",
      "summary": "The surface requires an authenticated session.",
      "evidence": ["The user completed sign-in in the headed browser."],
      "provenance": "browser",
      "observedAt": "2026-07-26T18:00:00Z",
      "confidence": "high",
      "inventoryItemRefs": []
    }
  ],
  "coverageInventory": {
    "status": "partial",
    "generatedAt": "2026-07-26T18:00:00Z",
    "gitAvailable": false,
    "sourceFilesVisited": 0,
    "sourceTraceabilityStatus": "missing",
    "partialInventoryReasons": [
      "Only one read-safe journey was observed."
    ],
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
        "knownRuntimeRequirements": ["baseUrl", "authenticated session"],
        "productSignalRefs": ["projects-list", "authenticated-session"],
        "sideEffectClass": "none",
        "groundingStatus": "authentication-required"
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

Before exploring, the host must first inspect the current session for the
project Playwright MCP tools and use them when navigation and snapshot tools
are present. Only when those tools are absent may it inspect an equivalent host
browser. In Codex, `agent.browsers.list()` reports Browser Plugin/in-app
backends only; an empty result does not prove that the project Playwright MCP is
absent. Configuration presence or provider installation alone is likewise
insufficient. The host may report an integration prerequisite only after both
tool inventories lack usable navigation. It must not run provider setup or
recommend a restart while Playwright MCP tools are already available.

If no browser tool is available before any product observation, the host
reports an integration prerequisite, does not invoke `workflow persist
understand`, and does not create or update product understanding. A partial
persisted result requires at least one real product signal.

Managed Codex and Claude installations invoke the provider through
`verifysignal integration playwright-mcp`. This stdio launcher pins the tested
provider version and isolates its cwd/output under a private temporary
directory. Integration setup installs that pinned provider into a private
versioned user cache before the agent starts; the launcher executes the cached
binary without registry access. If setup cannot prepare it, the public
`verifysignal integration setup-playwright-mcp --json` command reports the
blocked prerequisite and can be retried. Existing user-owned Playwright MCP
configuration is preserved. Integration initialization registers the managed
launcher in the selected agent's user scope through the agent's public MCP
command. The exact managed project entry remains a compatibility fallback.

The managed Codex project fallback is `required = true`. Pull-request
acceptance starts an ephemeral Codex app-server from a fresh untrusted project,
without `-c` or a trust override, and requires the user-scoped `playwright`
server to expose browser navigation, snapshot, and click tools. Claude
acceptance registers in an isolated user config and discovers the server from
a second clean project.

## Proof Handoff

After candidate review:

- read-only selection follows existing specify/plan/tasks/implement/validate/run
  contracts;
- potentially mutating selection requires explicit user confirmation and public
  Core `verifysignal.probe/v1`;
- probe may prove the pre-commit boundary but never authorizes normal run;
- missing browser/Core capabilities return partial or blocked state.
- candidate presentation uses `workflow recommend-first-run` ordering;
- acceptance can target an inventory-only candidate and resumes through
  `$verifysignal-specify` in Codex or `/verifysignal-specify` in Claude.
