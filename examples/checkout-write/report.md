# Run report — checkout-write

> Illustrative sample. See [../README.md](../README.md).

**Result:** ✅ `passed`  ·  **Run:** `request_checkout-write_1780305512001`
**Target:** `https://staging.example.com/checkout/review`  ·  **Profile:** `normal`
**Credentials:** `shopper` group (from environment, never persisted)

An authenticated shopper places an order. Because this **mutates product state**,
the run is governed by a declared side-effect policy, and the commit is observed
at runtime.

## Side effects

| Property | Value |
| --- | --- |
| Class | `write` · mode `enforce` |
| Commit step | `submit-order` — reached, `passed` |
| Observed write | `POST /api/orders` → `201` — **allowed** by policy |
| Policy violations | none |
| Side-effect status | `committed-confirmed` |
| Captured output | `createdResourceUrl = /orders/VS-2026-4F19` |
| Rerun | `requires-confirmation` — a rerun refreshes `orderRef` to avoid a duplicate |

## Gate coverage

| Gate | What was proven | Evidence |
| --- | --- | --- |
| `order-commit` | The order was created (`POST /api/orders` → 201). | network |
| `order-confirmed` | The confirmation heading "Order confirmed" is visible. | assertion · [screenshot](browser/screenshots/02-order-confirmed.svg) |
| `order-reference` | The created order reference is shown to the shopper. | assertion |

Required gates missing: **none**. Coverage: **complete**.

## Why this is safe to run

The write was **declared**, **allowed** by policy, **observed** at runtime, and
**classified** for rerun. Nothing mutated data outside the policy, and a second
run will not silently create a duplicate order — it stops for confirmation and
generates a fresh `orderRef`.

## Evidence

- Screenshots: [`browser/screenshots/`](browser/screenshots/)
- Network log: [`browser/network.ndjson`](browser/network.ndjson)
- Machine-readable: [`report.json`](report.json) (`qa-report/v1`)
