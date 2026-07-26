# verifysignal (default one-pass loop)

Drive one browser validation use case end to end in a single pass: understand,
author, ground, persist, validate, run, and apply safe repairs. Stop only for a
real unknown, an unsupported authenticated-write capability, or explicit
approval to cross a write boundary. This command orchestrates the staged
workflow; `workflow persist` remains the only path that writes managed
`.verifysignal/` artifacts.

## Preconditions

- Use the installed `verifysignal` executable directly. Do not use `npx` or
  package-runner wrappers.
- Read `verifysignal workflow info verifysignal-use-case --json`. Treat its
  `stagePayloadContracts`, `coreExecutableContract`, and
  `browserAuthoringContract` as the source of truth.
- Read `verifysignal core version --json` and negotiate optional capabilities:
  stateful probing is available only for the exact operation
  `{ name: "probe", schema: "verifysignal.probe/v1", schemaVersion: 1 }`;
  entry-state discovery is available only for
  `{ name: "discover", schema: "verifysignal.discover/v1" }`.
- Perform a Playwright MCP self-check. If `browser_navigate`,
  `browser_snapshot`, `browser_click`, and `browser_type` are available, use
  them as a live authoring aid. Otherwise author from source. The MCP is never
  the validation authority.
- If repository understanding is missing or stale, route through
  `/verifysignal-understand` or Golden Path preparation, then resume.

## One-pass loop

1. Resolve the target `baseUrl` or local start command from repository evidence.
   Never invent a URL. Stop and ask when it cannot be resolved.

2. Draft exactly one run request and its reusable skills from source and,
   optionally, a live MCP accessibility snapshot. Scope MCP access to the target
   application. Prefer stable `testId`, then accessible `label`/`text` or
   `semanticLocator`, and use `css` last. Never copy raw snapshot references
   such as `ref=e17` into a VerifySignal target. On write surfaces, MCP
   exploration stops before `commitStepId`.

3. Preserve authentication only as public run-request `credentialRefs` or
   `sessionRef`. Values remain in the environment and are resolved by Core.
   Never persist or print credentials, cookies, browser storage, storage-state
   files or values, DOM, screenshots, or MCP accessibility snapshots.

4. Classify grounding before execution:

   - For authenticated `write` or `external-notification`, require exact
     `verifysignal.probe/v1`. If it is unavailable, stop before execution,
     explain that this Core cannot statefully ground an authenticated write,
     and recommend upgrading. Do not substitute `discover`, source-only
     guessing, or normal `run`.
   - When probe is available, persist the canonical draft through the staged
     workflow and invoke:
     `verifysignal probe <run-request> --skill <main-skill> [--skill <support-skill> ...] --json`.
     Pass the same run request and ordered skills that normal run will use.
     Accept stateful grounding only when probe passed,
     `data.boundary.reached` is true, `data.boundary.executed` is false, and
     `data.fullFlowExecuted` is false.
   - For an authenticated read-only flow without probe, `discover` may confirm
     only targets reachable from its unauthenticated entry state. State that
     limitation and author protected-state targets from source; validate/run
     remain authoritative.
   - For an unauthenticated read-only flow with discover, use
     `verifysignal discover --url <baseUrl> --skill <drafted-skill> --json`.
     If discover is unavailable, recommend upgrading or continue source-only
     only after clearly stating the missing DOM grounding.

   A probe or discover `suggestedCorrection` wins over an MCP inference when
   the Core result is confident. Never invent a selector. Persist corrections
   only through `workflow persist implement`. If a target remains missing or
   ambiguous without a confident correction, stop and ask which element is
   intended.

5. Persist `specify`, `clarify`, `plan`, `tasks`, and `implement` in order with
   `verifysignal workflow persist <stage>`. Do not pause between successful
   stages. Do not hand-edit managed artifacts.

6. Before mutable execution, require a canonical `sideEffectPolicy`, resolved
   `resourceIdentity`, and valid `commitStepId`. Run
   `verifysignal validate <alias> --runtime-readiness`. Missing credentials are
   supplied through the environment, never persisted.

7. A successful write-flow probe is diagnostic evidence, not authorization.
   Require explicit developer confirmation before
   `verifysignal run <alias> --profile normal`. Only normal `run` may cross the
   commit boundary. Read-only flows run after validation as usual.

8. If run fails, use `verifysignal repair <alias>` and follow each
   recommendation's `autonomy`. Apply `auto-applied` repairs with `--approve`.
   For `propose-only` target changes, edit the staged payload, re-ground through
   the same probe/discover capability branch, and persist implementation again.
   Bound repairs to two attempts; on the third failure or a clarification/plan
   gap, stop with the report path and recommended stage.

## Escalation rules

Stop and ask the developer for:

1. an unresolved target URL or start command;
2. a missing required credential reference;
3. a missing resource identity or side-effect declaration;
4. unresolved or ambiguous target intent;
5. explicit developer confirmation before a mutable normal run;
6. a requirement/product-state decision or a third failed repair.

## Guardrails

- `workflow persist` is the ONLY way to write managed `.verifysignal/`
  artifacts.
- The Playwright MCP is an authoring/repair aid only. Probe/discover is the
  grounding authority for its applicable state, and `run` remains the final
  gate.
- Probe and MCP stop before `commitStepId`; only deterministic `run` crosses
  commit under side-effect gates and explicit developer confirmation.
- Keep one use case mapped to exactly one run request.
- On a strict pass, report one outcome summary and its evidence/report path.
