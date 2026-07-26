# Run report: checkout-write

> Illustrative sample. See [../README.md](../README.md).

Result: **passed**. Run `request_checkout-write_1780305512001`.
Target `https://staging.example.com/checkout/review`, profile `normal`.
Credentials: `shopper` group, from the environment, never persisted.

An authenticated shopper places an order. Because this mutates product state, the
run is governed by a declared side-effect policy, and the commit is watched at run
time.

## Side effects

| Property | Value |
| --- | --- |
| Class | `write`, mode `enforce` |
| Commit step | `submit-order`, reached, `passed` |
| Observed write | `POST /api/orders` returned `201`, allowed by policy |
| Policy violations | none |
| Side-effect status | `committed-confirmed` |
| Captured output | `createdResourceUrl = /orders/VS-2026-4F19` |
| Rerun | `requires-confirmation`; a rerun refreshes `orderRef` to avoid a duplicate |

## Gates

| Gate | Proven by | Evidence |
| --- | --- | --- |
| `order-commit` | the order was created (`POST /api/orders` returned 201) | network |
| `order-confirmed` | the confirmation heading "Order confirmed" is visible | assertion |
| `order-reference` | the created order reference is shown to the shopper | assertion |

Missing required gates: none. Coverage: complete.

The write was declared, allowed, watched, and classified for rerun. Nothing
mutated data outside the policy, and a second run will not silently create a
duplicate: it stops for confirmation and generates a fresh `orderRef`.

## Files

- [`report.json`](report.json), schema `qa-report/v1`
- [`browser/network.ndjson`](browser/network.ndjson)
