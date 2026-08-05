# Browser-First Understanding

Browser-first understanding lets VerifySignal identify useful validation
journeys from a live product when customer source or repository access is not
available. It is an exploratory authoring step; deterministic proof still runs
through the public VerifySignal Core contract.

## Start from a Local Engagement Directory

The directory does not need to be a Git repository:

```sh
mkdir product-validation
cd product-validation
verifysignal init --here --integration claude
```

In the installed agent, provide the URL conversationally or invoke:

```text
/verifysignal-understand --url https://staging.example.com
```

The public non-agent contract is discoverable with:

```sh
verifysignal workflow info verifysignal-use-case --json
```

Look for `stagePayloadContracts.browserFirstUnderstanding` with capability
`browser-first-understanding/v1`.

## What the Agent Does

The agent uses Playwright MCP or an equivalent host browser interface to:

1. open a headed browser;
2. stay within the user-approved origins;
3. let the user enter credentials directly and explicitly confirm login;
4. explore read-safe surfaces with human-observable pacing;
5. map up to 20 meaningful pages/states and depth 3 by default;
6. identify three to five candidate journeys when safely observable;
7. record partial coverage and gaps when the range cannot be met;
8. keep the browser open until the user acknowledges the summary.

The default soft exploration budget is 15 minutes. These are bounded mapping
defaults, not a whole-product coverage claim.

## Durable State

VerifySignal persists the result under `.verifysignal/` using the existing
`verifysignal-spec-product-context/v1` schema. Additive browser fields include:

- `understandingMode` (`repository`, `browser-first`, or `hybrid`);
- sanitized `targetEnvironment`;
- explicit `explorationScope`;
- synthesized `productSignals`;
- compatible coverage inventory and candidate journeys;
- evidence provenance, observation time, status, and gaps.

Browser-first target URLs retain only HTTP(S) origin and path. Query values and
fragments are removed. Browser-first freshness is age-based and does not depend
on Git.

## Data That Is Never Persisted

Browser mapping must not persist or print:

- credentials, authorization values, cookies, or browser storage;
- storage-state files or contents;
- entered form values;
- raw DOM/HTML or MCP snapshots;
- screenshots, traces, HAR, headers, or response bodies;
- raw URL query values;
- provider-specific browser capture references.

Authentication happens directly in the visible browser. If the session expires,
the agent pauses for the user instead of trying to recover secret material.

## Mapping Versus Proof

Mapping does not activate mutating, transactional, destructive, or
unknown-safety controls. It produces candidate journeys for review.

After the user selects one journey:

- read-only behavior can continue through the normal public
  specify/plan/tasks/implement/validate/run workflow;
- potentially mutating behavior requires explicit confirmation and the exact
  public `verifysignal.probe/v1` capability;
- probe must stop at the pre-commit boundary and must not commit the write;
- probe success never authorizes a normal committing run.

VerifySignal never imports private Runtime code. `workflow info`, `core
version`, `discover`, `probe`, and `run` public JSON contracts remain the
integration boundary.

## Modes

- `repository`: existing safe repository understanding; this remains the
  compatibility default.
- `browser-first`: live observations without source or Git requirements.
- `hybrid`: source and live observations together, with explicit provenance.

When hybrid evidence conflicts, VerifySignal records a gap rather than silently
choosing one source.

## Current Limits

The first release is same-origin and browser-host dependent. It is not a
general crawler, does not promise whole-application coverage, and does not send
browser understanding to the VerifySignal backend. A host without Playwright MCP
or an equivalent browser capability reports an actionable blocker and leaves
the project-local workspace valid.
