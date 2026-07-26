# Examples

Two end-to-end use cases, committed with their evidence, so you can see what a
run produces before installing anything.

> Illustrative samples. The `report.json` files match the real `qa-report/v1`
> schema and mirror a real `.verifysignal/` workspace, but were not run against a
> live target. A real run also captures a screenshot per gate and a full network
> log under `.verifysignal/runs/<alias>/<run-id>/`.

| Example | Flow | Side effects | Shows |
| --- | --- | --- | --- |
| [`home-page-unauth/`](home-page-unauth/) | public landing page, signed out | none | the golden-path first run, proven gate by gate |
| [`checkout-write/`](checkout-write/) | place an order | write (enforced) | write safety: a declared policy, a commit step, a captured order URL, a rerun classification |

Each example holds the use case (`use-case.yaml`), the executable request
(`run-request.yaml`), the grounded skill (`<alias>.browser.md`), and the result
as `report.md` (human) and `report.json` (`qa-report/v1`), plus a sample
`browser/network.ndjson`.

Start with [`home-page-unauth/report.md`](home-page-unauth/report.md).
