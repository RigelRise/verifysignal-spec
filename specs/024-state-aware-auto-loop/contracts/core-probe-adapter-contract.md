# Contract: Core Probe Adapter

## Public Boundary

`CoreAdapter.probe` invokes:

```text
<core-cmd> probe <run-request>
  --skill <main-skill>
  [--skill <support-skill> ...]
  [--headed]
  [--slow-mo <ms>]
  [--entitlement-receipt <path>]
  --json
```

The adapter:

1. preserves skill order;
2. uses the existing executable resolver;
3. uses the existing entitlement-receipt resolution path;
4. parses one JSON object;
5. returns the public envelope unchanged;
6. maps process failures through existing Core error handling.

It never adds credentials, session values, storage-state paths, environment
contents, or output directories to argv.

## Capability Helper

```python
core_supports_probe(version_response) -> bool
```

Returns true only when `data.operations` contains:

```json
{
  "name": "probe",
  "schema": "verifysignal.probe/v1",
  "schemaVersion": 1
}
```

Missing fields, wrong schema/version, malformed envelopes, and absent operations
return false.

## Compatibility

Probe remains outside globally required operations. An unsupported probe is an
orchestration branch, not an installation-wide incompatibility.
