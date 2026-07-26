# Skill: home-page-unauth

Grounds the public landing page of the target app. Selectors were grounded
against the live DOM with `verifysignal discover`, so every step references a
**named target** rather than an inline selector.

```yaml
schemaVersion: qa-skill/v1
id: skill.home-page-unauth
browser:
  targets:
    heroHeading:
      testId: hero-heading
      domainSemantics: Landing hero headline
    activitySlider:
      css: ".chakra-container .swiper-slide"
      domainSemantics: Live activity slider
    rankedTable:
      testId: leaderboard-table
      domainSemantics: Ranked leaderboard table
  steps:
    - id: open-home
      action: navigate
      value: "{{parameters.baseUrl}}/"
    - id: wait-hero
      action: checkText
      target: heroHeading
      value: "Ship with proof"
      timeoutMs: 30000
    - id: scroll-to-activity
      action: scrollIntoView
      target: activitySlider
    - id: await-leaderboard
      action: awaitNetwork
      match:
        method: POST
        urlContains: graphql
        operationName: LeaderboardQuery
        expectedStatus: 200
  assertions:
    - id: hero-visible
      kind: text
      target: heroHeading
      expected: "Ship with proof"
      gateId: hero-heading
    - id: activity-visible
      kind: visible
      target: activitySlider
      gateId: home-activity-slider
    - id: ranking-rendered
      kind: text
      target: rankedTable
      expected: "Rank"
      gateId: leaderboard-table
```
