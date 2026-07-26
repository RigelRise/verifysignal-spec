# Run report — home-page-unauth

> Illustrative sample. See [../README.md](../README.md).

**Result:** ✅ `passed`  ·  **Run:** `request_home-page-unauth_1780303629096`
**Target:** `https://staging.example.com/`  ·  **Profile:** `normal`  ·  **Credentials:** none

A signed-out visitor loads the landing page. Every required gate rendered and
was proven with a specific, rendered result — not just an HTTP 200.

## Gate coverage

| Gate | What was proven | Evidence |
| --- | --- | --- |
| `hero-heading` | The hero headline "Ship with proof" is visible. | assertion · [screenshot](browser/screenshots/01-hero.svg) |
| `home-activity-slider` | The live activity slider rendered at least one slide. | assertion |
| `leaderboard-table` | The ranked table rendered with a "Rank" column, backed by the `LeaderboardQuery` GraphQL response (HTTP 200). | network · [screenshot](browser/screenshots/02-activity-and-ranking.svg) |

Required gates missing: **none**. Coverage: **complete**.

## Steps

1. `open-home` — navigate to `{{baseUrl}}/` → **passed**
2. `wait-hero` — wait for the hero heading text → **passed**
3. `scroll-to-activity` — scroll the activity slider into view → **passed**
4. `await-leaderboard` — await `POST …/graphql` `LeaderboardQuery` (200) → **passed**

## Evidence

- Screenshots: [`browser/screenshots/`](browser/screenshots/)
- Network log: [`browser/network.ndjson`](browser/network.ndjson)
- Machine-readable: [`report.json`](report.json) (`qa-report/v1`)

A green result here means the same thing every time it is run: these gates, this
evidence. That is the point.
