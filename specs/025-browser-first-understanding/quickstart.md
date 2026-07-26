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

## 7. Full regression and package checks

```bash
.venv/bin/pytest
python -m build
```

The cross-repository release gate is satisfied by Core main merge `6ea5d7f`.
Core `0.6.0` advertises exact public `verifysignal.probe/v1` compatibility, and
the merged main passed the focused probe contract and integration suites.
