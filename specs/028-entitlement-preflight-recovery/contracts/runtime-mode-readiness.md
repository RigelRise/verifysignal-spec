# Contract: Runtime Mode and Protected Readiness

## Purpose

Define how workspace creation chooses Core and how readiness distinguishes a
compatible command from a proven protected operation. This contract extends
current Spec JSON/YAML shapes additively.

## Workspace mode contract

| Workspace condition | Explicit command | Persisted mode | Local candidate behavior |
|---|---|---|---|
| Workspace file does not exist before init | none | `managed-only` | Ignore workspace, environment, PATH, and ancestor-sibling candidates |
| Workspace file already exists and mode is absent | none | field remains absent | Effective `legacy-auto`; preserve current legacy resolution |
| Any workspace | successful `init --core-cmd <cmd>` | `development-override` | Persist the validated explicit command |
| Any workspace | successful `core setup --core-cmd <cmd>` | `development-override` | Persist the validated explicit command |
| Any workspace | failed explicit setup | unchanged | Do not persist an invalid command or new override |
| Any workspace | successful reset/update | `managed-only` | Remove/ignore local override per existing feature 026 contract |

Creation is determined before `init_workspace()` creates files. Repeated init,
including forceful regeneration of integration files, does not make an existing
field-absent workspace "new" and does not silently migrate it.

The current runtime result continues to expose its selected `source` and gains
or preserves an `effectiveResolutionMode` projection. No output includes receipt,
key, environment value, or sensitive command content beyond the already public
explicit executable string selected by the user.

For every protected source-runtime invocation, the command resolves one
effective entitlement API base URL. Receipt lookup and cached public-key lookup
both use that exact endpoint namespace. A custom CLI/workspace endpoint cannot
silently read keys cached for the default service.

## Readiness v1 additive shape

The fields below are added to both the persisted
`verifysignal-spec-readiness-snapshot/v1` and the `runtimeReadiness` object
returned by protected validation:

```json
{
  "commandCompatibilityStatus": "passed",
  "trustMaterialStatus": "ready",
  "protectedOperationStatus": "not-checked",
  "readinessScope": "command-and-trust-inputs"
}
```

Allowed values:

| Field | Allowed values |
|---|---|
| `commandCompatibilityStatus` | `not-checked`, `passed`, `blocked` |
| `trustMaterialStatus` | `not-checked`, `ready`, `blocked` |
| `protectedOperationStatus` | `not-checked`, `passed`, `blocked` |
| `readinessScope` | `command-and-trust-inputs`, `protected-operation` |

### Meaning

- `commandCompatibilityStatus` reports the public version/required-operation
  contract only.
- `trustMaterialStatus` reports availability and local validation of receipt/key
  inputs only. It does not claim the selected Core accepted or armed them.
- `protectedOperationStatus` reports the normalized result only when the
  entitlement-protected authoring check was invoked with
  `--runtime-readiness`. An authoring check without that flag remains
  `not-checked` for this component even though its authoring result is returned.
- `readinessScope` states the strongest proof represented by the object.

### Invariants

1. `readinessScope: protected-operation` requires
   `commandCompatibilityStatus: passed` and an `authoring-check` invocation with
   `--runtime-readiness`.
2. `protectedOperationStatus: passed` requires that flag, the exact expected
   public success schema, and `status: passed`.
3. Any attempted component that blocks makes the aggregate readiness `blocked`.
4. Aggregate `ready` requires protected scope, command compatibility and
   protected operation `passed`, and trust material `ready`.
5. `command-and-trust-inputs` may be useful onboarding information but never
   satisfies run preflight.
6. `fullBrowserFlowExecuted` remains false during readiness validation.
7. The receipt and source-runtime public-key handoff use the same effective API
   endpoint for authoring-check, run, probe, crystallize, and report inspection.

## Legacy decoding

When any additive field is absent:

```json
{
  "commandCompatibilityStatus": "not-checked",
  "trustMaterialStatus": "not-checked",
  "protectedOperationStatus": "not-checked",
  "readinessScope": "command-and-trust-inputs"
}
```

Existing aggregate fields remain readable, but a legacy `status: ready` alone
does not satisfy run preflight. The user is directed to run protected runtime
validation to upgrade the snapshot.

## Protected validation projections

| Invocation | Normalized authoring-check outcome | Component result | Aggregate result | Next action |
|---|---|---|---|---|
| Without `--runtime-readiness` | Any authoring result | protected `not-checked` | `blocked` for run readiness | `verifysignal validate <alias> --runtime-readiness --json` |
| With `--runtime-readiness` | Expected schema, `passed` | protected `passed` | `passed` when all earlier layers passed | `verifysignal run <alias> --json` |
| With `--runtime-readiness` | Expected schema, non-passing authoring result | protected `blocked` | `blocked` | Repair authored artifacts, then validate |
| With `--runtime-readiness` | `verifysignal.error/v1` | protected `blocked` | `blocked` | Follow normalized Core blocker recovery |
| With `--runtime-readiness` | Unknown/malformed schema | protected `blocked` | `blocked` | Upgrade compatible Core/Spec contract |

No row may be presented as browser evidence or create a RunHistory entry.

## Compatibility assertions

- Existing schema identifiers stay unchanged.
- Existing readers may ignore the additive fields.
- New readers load legacy records conservatively.
- Source and managed runtime selection continue through existing public CLI
  contracts; no private Core identity or package import is introduced.
