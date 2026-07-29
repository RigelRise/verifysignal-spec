# Data Model: Hermetic Update and Test Readiness

## Workspace Core Configuration

| Field | Type | Semantics |
|---|---|---|
| `coreResolutionMode` | enum | `legacy-auto`, `managed-only`, or `development-override`; missing maps to `legacy-auto`. |
| `coreCommand` | string? | Persisted command only for explicit development override compatibility. |
| `coreSource` | string? | Source of the development override. |
| `coreVersion` | string? | Version reported by the development override. |
| `managedCoreVersion` | string? | Active verified managed version. |
| `managedCoreUpdatedAt` | datetime? | Last successful managed update. |
| `managedCoreCheckedAt` | datetime? | Last managed latest check, including failed checks. |

Invariant: `managed-only` resolution never consults `coreCommand`, environment,
PATH, or ancestor-sibling candidates.

## AuthoringQuestion Extension

| Field | Type | Semantics |
|---|---|---|
| `suggestedAnswer` | object? | Non-authoritative candidate presented to the user. |
| `suggestionSource` | string? | Repository, previous workflow, or explicit discovery provenance. |
| `requiresConfirmation` | boolean | True for browser target environment questions. |

Invariant: suggestion fields never change the question status to answered.

## WorkflowRun Target Confirmation

| Field | Type | Semantics |
|---|---|---|
| `targetEnvironmentConfirmation` | object? | Confirmation scoped to this workflow run. |
| `.url` | string | User-confirmed browser target. |
| `.source` | enum | `direct-user` or `explicit-command`. |
| `.confirmedAt` | datetime | Confirmation time. |
| `.questionId` | string | Authoring question that captured the decision. |

Invariant: another workflow run cannot reuse this object as confirmation.

## CredentialPreparationResult

Schema: `verifysignal-spec-credential-preparation/v1`

| Field | Type | Secret-safe contents |
|---|---|---|
| `status` | enum | `prepared`, `blocked`, or `unchanged`. |
| `alias` | string | Registered use-case alias. |
| `envFile` | string | Project-relative explicit file path. |
| `declaredKeys` | string[] | Exact public environment key names. |
| `appendedKeys` | string[] | Missing declarations appended. |
| `preservedKeys` | string[] | Existing declared assignments preserved. |
| `gitExcluded` | boolean | Whether exact exclusion is verified. |
| `permissions` | string | Expected `0600`, never file contents. |
| `blockers` | object[] | Safe codes and remediation. |

## ParsedEnvironment

Ephemeral in-memory mapping from declared key name to value. It is never
serialized and is discarded after constructing the Core child environment.
