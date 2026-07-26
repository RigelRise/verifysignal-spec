# Run report: home-page-unauth

> Illustrative sample. See [../README.md](../README.md).

Result: **passed**. Run `request_home-page-unauth_1780303629096`.
Target `https://staging.example.com/`, profile `normal`, no credentials.

A signed-out visitor loads the landing page. Every required gate rendered and was
proven with a specific result, not just an HTTP 200.

## Gates

| Gate | Proven by | Evidence |
| --- | --- | --- |
| `hero-heading` | the hero headline "Ship with proof" is visible | assertion |
| `home-activity-slider` | the live activity slider rendered a slide | assertion |
| `leaderboard-table` | the ranked table rendered, backed by the `LeaderboardQuery` response (HTTP 200) | network |

Missing required gates: none. Coverage: complete.

## Files

- [`report.json`](report.json), schema `qa-report/v1`
- [`browser/network.ndjson`](browser/network.ndjson)

A real run also saves a screenshot per gate under `browser/screenshots/`. This
text sample omits them.
