# Examples

Two end-to-end VerifySignal use cases, committed **with their evidence** so you
can see exactly what a run produces before you install anything.

> **These are illustrative samples.** The `report.json` files match the real
> `qa-report/v1` schema and the artifacts mirror a real `.verifysignal/`
> workspace, but the runs were not executed against a live target. The
> screenshots are stand-in mockups (`.svg`), not real captures. Your own runs
> write real PNG screenshots and a real network log under
> `.verifysignal/runs/<alias>/<run-id>/`.

| Example | Flow | Side effects | What it shows |
| --- | --- | --- | --- |
| [`home-page-unauth/`](home-page-unauth/) | Public landing page, signed out | `none` (read-only) | The golden-path first run — hero, live activity, and a ranked table proven with rendered-result evidence. |
| [`checkout-write/`](checkout-write/) | Place an order | `write` (enforced) | Write-flow safety — a declared side-effect policy, a commit step, a captured `createdResourceUrl`, and a rerun classification. |

## What's in each example

```
<alias>/
├── use-case.yaml        # the registered use case          (verifysignal-spec-use-case/v1)
├── run-request.yaml     # the executable request the runtime runs (qa-run-request/v1)
├── <alias>.browser.md   # the grounded browser skill: named targets, steps, assertions
├── report.md            # human-readable result — step by step, gate by gate
├── report.json          # machine-readable result           (qa-report/v1)
└── browser/
    ├── screenshots/      # captured evidence per gate
    └── network.ndjson    # redacted network log
```

New here? Open [`home-page-unauth/report.md`](home-page-unauth/report.md) first —
it is the shortest path to understanding what "evidence over green checkmarks"
actually means.
