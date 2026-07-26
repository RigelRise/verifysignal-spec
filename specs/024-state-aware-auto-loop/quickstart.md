# Quickstart: State-Aware Automatic Authoring Loop

## 1. Observe red adapter and capability tests

```bash
.venv/bin/pytest \
  tests/unit/test_core_adapter.py \
  tests/unit/test_auto_loop.py \
  tests/contract/test_probe_capability_contract.py
```

Expected before implementation: adapter/capability APIs are missing and the
template still mentions unsupported storage-state guidance.

## 2. Implement the public adapter and loop guidance

```bash
.venv/bin/pytest \
  tests/unit/test_core_adapter.py \
  tests/unit/test_auto_loop.py \
  tests/contract/test_probe_capability_contract.py \
  tests/integration/test_probe_command.py \
  tests/integration/test_agent_template_guidance.py
```

## 3. Validate against public Core

```bash
verifysignal core version --json
verifysignal probe <run-request> --skill <main-skill> --json
```

The first response must advertise exact probe v1 metadata. The second must keep
`boundary.executed` and `fullFlowExecuted` false.

## 4. Preserve compatibility and secret safety

```bash
.venv/bin/pytest \
  tests/contract/test_core_public_compatibility_contract.py \
  tests/contract/test_core_public_boundary_contract.py \
  tests/integration/test_runtime_secret_safety.py \
  tests/integration/test_discover_command.py \
  tests/integration/test_run_use_case.py
```

## 5. Cross-agent installation check

Install/upgrade Codex and Claude integrations into temporary projects and
verify both generated automatic-loop skills contain the same probe and legacy
fallback rules and no `discover --storage-state` text.

## 6. Identity-neutral dogfood

Run Core's isolated `stateful-precommit-probe` reference application. It
reproduces only the required functional structure: login, protected project
form, commit boundary, and success state. The probe must create zero resources;
the explicitly invoked normal run must create exactly one local fixture
resource.

Do not use a branded or production application and do not copy any real product
name, domain, content, logo, imagery, colors, typography, or other visual
identity into the dogfood target.

The minimal example remains a smoke regression. The authoritative structural
gate is:

```bash
python scripts/dogfood/authenticated_project_red_green.py \
  --core-repo ../verifysignal
```

It must first prove the unauthenticated discover limitation, then invoke probe
through Spec's public CLI with zero commits, validate with runtime readiness,
verify public run readiness, and invoke normal run exactly once to create one
process-local resource whose rendered title satisfies the planned validation
gate. Invoking this isolated command is the authorization for that local write.
If readiness returns a structured confirmation id, the runner passes only that
id. A red result stops before any product-code adjustment.
