from __future__ import annotations

BROWSER_TARGET_BEFORE_PLANNING = "Confirm the browser target environment before planning executable artifacts"
RUNTIME_READINESS_BOUNDARY = (
    "workflow check validate reports structural readiness only; runtime readiness separately verifies "
    "target resolution, target reachability, required runtime prerequisites, entitlement, and Core authoring readiness"
)
CONFIRMED_REPAIR_BOUNDARY = "Selector, flow, data, and coverage changes require confirmation"
# SAFE_MECHANICAL_REPAIR_GUIDANCE was deleted here, not rewritten. It claimed selector, wait,
# target-specificity, equivalent-flow, and run-profile repairs "may auto-apply" — only step-ordering
# has a mutator — and it had zero importers, so it was dead prose that could only ever mislead
# whoever wired it up next. The live source of truth is MUTABLE_SAFE_CATEGORIES in
# workflows/repair_recommendations.py; render guidance from that, never from a second hand-written copy.
FIRST_RUN_STAGE_CARD_GUIDANCE = (
    "For Golden Path first-run output, render clear stage cards with a separator, status marker, "
    "one-line summary, why it matters, primary evidence, repair details when present, and next action"
)
REAL_TARGET_FIRST_RECOMMENDATION = (
    "Recommend the simplest stable real-target validation as the first run and state that accepting it is highly recommended; "
    "do not use fake/demo targets as a user-facing fallback"
)
MISSING_UNDERSTANDING_AUTO_PREPARE = (
    "When specify reports missing product understanding with auto-prepare metadata, run safe repository or browser-first understanding, avoid sensitive files, "
    "then resume the original specify flow without requiring the user to manually restart"
)
PUBLIC_WORKFLOW_CONTRACT_BOUNDARY = (
    "Use the public workflow contract from `verifysignal workflow info verifysignal-use-case --json` "
    "and `stagePayloadContracts`; Do not inspect installed package source to infer payload schemas"
)
PLAYWRIGHT_MCP_GUIDANCE = (
    "If you have a Playwright MCP server available (live browser tools such as `browser_navigate` and "
    "`browser_snapshot`), you MAY use it to author and repair browser selectors against the live page instead "
    "of guessing from source — but it is an authoring aid, never a validator: every selector it suggests must "
    "still be confirmed by `verifysignal discover` and the use case must still pass `verifysignal run`, and if the "
    "MCP and `discover` disagree, `discover` wins. Without a Playwright MCP, author from source as usual; the "
    "deterministic grounding and gate are unchanged. The managed MCP launcher isolates provider files in a "
    "private temporary directory; never copy MCP snapshots, DOM, screenshots, logs, cookies, or storage state "
    "into the target project or `.verifysignal/`. On authenticated surfaces preserve auth only as public run-request "
    "`credentialRefs` or `sessionRef` resolved by Core from the environment. For authenticated write surfaces, "
    "use Core's advertised `verifysignal.probe/v1` capability for stateful pre-commit grounding; let the MCP "
    "explore only up to the commit step and never cross it — only the deterministic `run` crosses the commit. "
    "For `browser-first-understanding/v1`, use Playwright MCP or an equivalent headed browser, let the user enter "
    "credentials directly, keep navigation human-observable and read-safe, and keep the browser open until the "
    "user acknowledges the summary"
)
