# Core Runtime Lifecycle Contract

## Commands

```text
verifysignal core reset [--project PATH] --json
verifysignal core update [--project PATH] [--api-base-url URL] --json
```

`reset` emits `verifysignal-spec-core-reset/v1`. It reports the resulting mode
and names removed metadata fields, never removed values.

`update` emits `verifysignal-spec-core-update/v1`. It reports requested/latest
version, selected managed version, verified source, cache reuse, fallback, safe
attempt diagnostics, and blockers.

## Resolution Policy

| Mode/context | Explicit invocation `--core-cmd` | Workspace command | Env/PATH/sibling | Managed |
|---|---:|---:|---:|---:|
| `legacy-auto` | yes | yes | yes | yes |
| `development-override` | yes | yes | no | fallback |
| `managed-only` | yes | no | no | yes |
| `core update` | no | no | no | latest only |

The update row also ignores managed version pins. Exact latest cache reuse still
requires verification.

## Upgrade Purity

`integration upgrade` may read stored non-secret workspace metadata to render
guidance. It must not execute candidate commands, query PATH, search ancestors,
call the managed backend, or persist Core selection. Its existing Core response
slot reports `status: not-checked`.
