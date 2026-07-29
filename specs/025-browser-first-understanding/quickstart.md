# Quickstart: Browser-First Product Understanding

## 1. Observe red contract and normalization tests

```bash
.venv/bin/pytest \
  tests/unit/test_browser_understanding.py \
  tests/contract/test_browser_first_understanding_contract.py \
  tests/contract/test_workflow_stage_persistence_contract.py
```

Expected before implementation: no understand-stage public contract,
browser-first normalizer, or mode-aware persistence exists.

## 2. Implement safe browser-first persistence

```bash
.venv/bin/pytest \
  tests/unit/test_browser_understanding.py \
  tests/unit/test_understanding_freshness_metadata.py \
  tests/unit/test_workflow_prerequisites.py \
  tests/integration/test_browser_first_understanding.py \
  tests/integration/test_workflow_understand.py
```

The integration fixture starts from a non-Git directory. Assert that target
query/fragment data and every forbidden browser artifact are absent from
`.verifysignal/`.

## 3. Validate the public contract

```bash
verifysignal workflow info verifysignal-use-case --json
verifysignal workflow persist understand \
  --scope all \
  --payload /tmp/browser-understanding.json \
  --json
```

The first response must advertise `browser-first-understanding/v1`. The second
must persist mode-aware context through the existing public command.

## 4. Validate agent-neutral guidance

```bash
.venv/bin/pytest \
  tests/contract/test_agent_command_contract.py \
  tests/contract/test_agent_guidance_contract.py \
  tests/integration/test_agent_template_guidance.py \
  tests/integration/test_workflow_agent_installation.py \
  tests/integration/test_workflow_agent_installation_codex.py
```

Generated Codex and Claude understand commands must share bounded exploration,
assisted authentication, non-persistence, candidate review, browser-lifecycle,
and probe-only mutation rules.

## 5. Preserve repository compatibility and secret safety

```bash
.venv/bin/pytest \
  tests/contract/test_understanding_onboarding_contract.py \
  tests/contract/test_coverage_inventory_contract.py \
  tests/integration/test_understanding_onboarding.py \
  tests/integration/test_workflow_coverage_inventory.py \
  tests/integration/test_workflow_understand_sensitive_files.py \
  tests/integration/test_workflow_secret_non_persistence.py
```

Existing repository payloads and artifacts must remain valid without migration.

## 6. Prove one read-only journey through public Core

Use a local identity-neutral HTTP fixture. Persist browser-first understanding,
select one candidate, author one run request, and invoke only documented Core
operations. Confirm the public executable contract before execution:

```bash
verifysignal core version --json
verifysignal workflow info verifysignal-use-case --json
```

Run read-only validation through the existing Spec/Core flow. For a potentially
mutating fixture, require explicit confirmation and invoke Spec's public
`probe` adapter. Assert `boundary.executed=false`, `fullFlowExecuted=false`, and
zero committed writes.

## 7. Validate smoke-hardening contracts

```bash
.venv/bin/pytest \
  tests/unit/test_browser_understanding.py \
  tests/unit/test_first_run_suitability.py \
  tests/unit/test_first_run_state.py \
  tests/contract/test_browser_first_understanding_contract.py \
  tests/contract/test_first_run_recommendation_contract.py \
  tests/integration/test_browser_first_understanding.py
```

Confirm that:

- canonical and bounded-alias payloads normalize equivalently;
- unknown, conflicting, missing, and invalid references fail atomically;
- only observed read-only candidates qualify for automatic guidance;
- inventory-only acceptance preserves candidate details and resumes through
  the selected integration's `specify` command.

## 8. Validate isolated Playwright MCP and invocation parity

```bash
.venv/bin/pytest \
  tests/contract/test_agent_command_contract.py \
  tests/contract/test_integration_onboarding_guidance_contract.py \
  tests/integration/test_mcp_config.py \
  tests/integration/test_integration_onboarding_guidance.py
```

The managed MCP entry must invoke
`verifysignal integration playwright-mcp`. Its provider version is pinned and
its cwd/output are private temporary paths removed after success, failure,
interrupt, or termination. Codex output uses `$verifysignal-*`; Claude output
uses `/verifysignal-*`.

Integration setup must also report the provider as `offlineReady: true`.
Exercise the repair/setup command directly when needed:

```bash
verifysignal integration setup-playwright-mcp --json
```

The launcher must not call `npx` after setup. Run the deterministic handshake
regression locally:

```bash
.venv/bin/pytest \
  tests/integration/test_mcp_config.py::test_managed_cli_launcher_completes_real_mcp_handshake_without_npx
```

CI additionally sets `VERIFYSIGNAL_RUN_REAL_MCP_TESTS=1` and requires the same
`initialize`/`tools/list` exchange against the real pinned provider. To repeat
that networked acceptance locally:

```bash
VERIFYSIGNAL_RUN_REAL_MCP_TESTS=1 \
  .venv/bin/pytest \
  tests/integration/test_mcp_config.py::test_pinned_playwright_provider_initialize_and_tools_list
```

## 9. Validate structural/runtime readiness separation

```bash
.venv/bin/pytest \
  tests/contract/test_validation_readiness_contract.py \
  tests/integration/test_workflow_runtime_readiness.py \
  tests/integration/test_workflow_performance.py
```

`workflow check validate` must report `readinessScope: structural`,
`runtimeReadinessStatus: not-run`, and an exact runtime-readiness command. A
structural pass is not an entitlement or protected-runtime pass.

## 10. Re-run the manual-smoke regression matrix

Every product defect observed in the PR smoke has a stable automated owner:

| Manual symptom | Regression coverage |
|---|---|
| Codex started with no browser backend despite project setup | `tests/integration/test_mcp_config.py::test_codex_managed_playwright_is_required_but_claude_entry_is_not`; `tests/integration/test_codex_mcp_session.py::test_trusted_codex_session_discovers_required_playwright_tools` |
| Codex treated an empty Browser Plugin inventory as proof that the loaded project Playwright MCP was unavailable | `tests/contract/test_agent_command_prerequisite_contract.py::test_understand_uses_loaded_playwright_mcp_when_codex_browser_plugin_is_empty`; `tests/integration/test_codex_mcp_session.py::test_trusted_codex_session_discovers_required_playwright_tools` |
| A host browser failure was reported/persisted as blocked product understanding | `tests/contract/test_agent_command_prerequisite_contract.py::test_understand_host_browser_failure_is_setup_not_product_state`; `tests/integration/test_browser_first_understanding.py::test_zero_observation_host_failure_never_becomes_product_understanding` |
| Raw inline JSON passed to `--payload` became a path/empty payload | `tests/contract/test_workflow_cli_contract.py::WorkflowCliContractTests::test_inline_json_passed_as_payload_reports_stdin_recovery` |
| Reachability, signal kind, aliases, and duplicated candidates required trial-and-error edits | `tests/contract/test_browser_first_understanding_contract.py::test_public_workflow_contract_advertises_browser_first_understanding_v1`; `tests/unit/test_browser_understanding.py::test_documented_aliases_normalize_to_the_canonical_payload`; `tests/unit/test_browser_understanding.py::test_equivalent_top_level_candidate_alias_does_not_duplicate_state`; `tests/unit/test_browser_understanding.py::test_manual_smoke_enum_errors_name_the_allowed_values` |
| Selecting an inventory candidate returned “Use case not found” | `tests/contract/test_first_run_recommendation_contract.py::FirstRunRecommendationContractTests::test_accepts_inventory_only_candidate_and_resumes_codex_specify` |
| Accepted first run returned an invalid `verifysignal author <alias> --json` handoff | `tests/contract/test_first_run_recommendation_contract.py::FirstRunRecommendationContractTests::test_accept_first_run_json_contract` |
| Codex responses used slash-prefixed agent commands | `tests/contract/test_workflow_cli_contract.py::WorkflowCliContractTests::test_workflow_info_json_contract`; `tests/contract/test_first_run_recommendation_contract.py::FirstRunRecommendationContractTests::test_accept_first_run_json_contract` |
| `workflow check run` blocked on missing plan while returning `blockers: []` | `tests/integration/test_workflow_later_stage_prerequisites.py::test_run_missing_plan_is_an_explicit_blocker_with_recovery` |
| Structural validation was described as protected-runtime readiness | `tests/contract/test_validation_readiness_contract.py::ValidationReadinessContractTests::test_structural_readiness_exposes_runtime_boundary_and_exact_next_action` |
| `entitlement.key-unknown` triggered repeated init/forced-init/Core-setup attempts | `tests/contract/test_agent_command_guardrail_contract.py::test_validate_does_not_loop_setup_for_key_unknown_entitlement`; `tests/integration/test_managed_runtime_override_entitlement.py::test_runtime_readiness_reports_key_unknown_when_fetched_keys_omit_receipt_key` |
| Sandbox permission denial surfaced as an unstructured exception | `tests/contract/test_workflow_cli_contract.py::WorkflowCliContractTests::test_json_init_permission_failure_is_structured_and_actionable` |
| CLI requested/exchanged a token even when email delivery failed or was throttled | `tests/integration/test_managed_runtime_override_entitlement.py::test_init_cli_does_not_prompt_for_token_when_delivery_was_not_accepted`; `tests/integration/test_managed_runtime_override_entitlement.py::test_init_cli_preserves_pending_delivery_when_token_did_not_arrive` |
| Local initialization reused a production receipt/key/runtime cache and failed with misleading trust errors | `tests/unit/test_runtime_cache_namespace.py` |
| A managed-stable packaged runtime rejected Spec's automatically injected cached key even though the same trusted key was packaged in the runtime | `tests/unit/test_core_adapter.py::CoreAdapterTests::test_packaged_runtime_uses_packaged_trust_instead_of_cached_environment_keys`; `tests/unit/test_core_adapter.py::CoreAdapterTests::test_source_runtime_keeps_cached_environment_key_handoff` |
| A generated read-only run request omitted Core-required `sideEffectPolicy.mode` and blocked authoring readiness | `tests/contract/test_side_effect_policy_compatibility_contract.py::test_generated_run_request_materializes_core_required_policy_mode` |
| A `Teams` text target matched multiple elements and generated CSS was accepted until the browser run | `tests/unit/test_core_contract_projection.py`; Core `tests/unit/authoring-target-warning.test.ts` and `tests/integration/authoring-check-command.test.ts` |
| Core/browser and coverage passed while an observed side-effect policy violation was summarized too weakly | `tests/unit/test_first_run_state.py`; `tests/integration/test_guided_first_run_flow.py` |
| A failed run could be retried under the unchanged policy or “repaired” by silently allowing traffic | `tests/unit/test_side_effect_declaration.py`; `tests/integration/test_repair_from_report.py` |
| A read-only GraphQL query over POST was conservatively reported as a write without protocol evidence | Core `tests/unit/side-effect-observation.test.ts` and `tests/integration/side-effect-contract-example.test.ts` |
| A multi-surface candidate was claimed without proving the transition | `tests/unit/test_browser_understanding.py::test_observed_multi_surface_candidate_requires_matching_transition_signal` |
| Registry-dependent `npx` startup lost the MCP silently | `tests/integration/test_mcp_config.py::test_managed_cli_launcher_completes_real_mcp_handshake_without_npx`; `tests/integration/test_mcp_config.py::test_pinned_playwright_provider_initialize_and_tools_list` |

The endpoint-isolation regression can also be run independently:

```bash
.venv/bin/pytest -q tests/unit/test_runtime_cache_namespace.py
```

The selected regression set was overlaid onto original PR head
`438132c54ed54f191599d430dc3d205ac803879e`: thirteen defect tests failed and the
pre-existing zero-signal persistence guard passed. This proved that the false
blocked-understanding regression was in host guidance/session readiness, not
the low-level normalizer alone. The same tests must be GREEN on the corrected
branch. The packaged-runtime trust-source and generated policy-mode regressions
were subsequently observed RED on the pre-fix working tree, then made GREEN
before the real local `authoring-check` smoke passed.

Run the deterministic matrix:

```bash
.venv/bin/pytest -q \
  tests/unit/test_browser_understanding.py \
  tests/contract/test_browser_first_understanding_contract.py \
  tests/contract/test_agent_command_prerequisite_contract.py \
  tests/contract/test_agent_command_guardrail_contract.py \
  tests/contract/test_workflow_cli_contract.py \
  tests/contract/test_first_run_recommendation_contract.py \
  tests/contract/test_side_effect_policy_compatibility_contract.py \
  tests/contract/test_validation_readiness_contract.py \
  tests/unit/test_side_effect_declaration.py \
  tests/unit/test_first_run_state.py \
  tests/unit/test_core_contract_projection.py \
  tests/integration/test_guided_first_run_flow.py \
  tests/integration/test_repair_from_report.py \
  tests/integration/test_browser_first_understanding.py \
  tests/integration/test_workflow_later_stage_prerequisites.py \
  tests/integration/test_mcp_config.py \
  tests/unit/test_core_adapter.py
```

Run the real Codex session gate after the provider cache is prepared:

```bash
VERIFYSIGNAL_RUN_REAL_CODEX_TESTS=1 \
  .venv/bin/pytest -q \
  tests/integration/test_codex_mcp_session.py
```

The acceptance makes npm offline and points it at an empty ordinary package
cache after managed setup. Tool discovery therefore proves that Codex starts
the pinned provider from the VerifySignal cache without an `npx` or registry
fallback.

The same acceptance uses an isolated Codex user directory, initializes a fresh
non-Git project, starts `codex app-server` without `-c`, and requires the
managed Playwright navigation, snapshot, and click tools. It must not inject
project trust or any launch-time configuration override.

## 11. Full regression, package, and clean Codex smoke

```bash
.venv/bin/pytest
.venv/bin/python -m build
git diff --check
```

When offline, use `.venv/bin/python -m build --no-isolation` with the existing
development environment.

Run the real Core/Spec boundary from sibling checkouts:

```bash
(cd ../verifysignal && npm run runtime:acceptance)

CORE_REPO=../verifysignal

VERIFYSIGNAL_REAL_CORE_REPOSITORY="$CORE_REPO" \
  .venv/bin/pytest -q \
  tests/contract/test_required_operations_track_core.py \
  tests/integration/test_probe_command.py

VERIFYSIGNAL_REAL_CORE_ARTIFACT="$CORE_REPO/dist/runtime/verifysignal-core-0.6.1-darwin-arm64.tar.gz" \
  .venv/bin/pytest -q tests/integration/test_real_core_artifact_install.py
```

These checks use the public Core CLI/contract and a locally packaged runtime;
they do not require the backend or a production token.

For the clean smoke, initialize a temporary Codex workspace, persist the public
browser-first example, run `workflow recommend-first-run`, accept the selected
inventory candidate, and confirm that the returned handoff is
`$verifysignal-specify <alias>`. The temporary project must contain the managed
Codex MCP entry and no Playwright snapshots, screenshots, traces, logs, or
storage state.

The probe baseline was satisfied by Core main merge `6ea5d7f`. This patch's
cross-repository release gate additionally targets the locally built Core
`0.6.1`: it must advertise exact public `verifysignal.probe/v1` compatibility,
blocking authoring-warning metadata, and side-effect report attribution, and
its packaged runtime must install through the Spec integration test.
Entitlement trust remains owned by feature 026 and is validated only in the
cross-branch release smoke.
