# Contract: Automatic Loop Stateful Grounding Decisions

## Write or External Notification

| Core capability | Authentication | Decision |
|---|---|---|
| probe v1 | any supported reference | Invoke probe |
| no probe v1 | credentialRefs/sessionRef present | Stop and recommend Core upgrade |
| no probe v1 | no authentication | Stop unless the author explicitly chooses source-only risk |

After probe:

- reached=true, executed=false, fullFlowExecuted=false, all required targets
  grounded: present explicit normal-run confirmation for a
  developer-controlled target;
- confident target correction: persist through workflow API, then probe again,
  maximum two repair attempts;
- unresolved target: stop and ask for target intent;
- boundary not reached or any safety invariant differs: stop and report blocker.

## Read-Only

| Core capability | Decision |
|---|---|
| probe v1 | Probe may be unnecessary; retain discover/source-only path |
| discover v1 only | Continue with entry-page limitation notice |
| neither | Recommend upgrade or explicit source-only authoring |

## Prohibited Guidance

- Do not suggest `discover --storage-state`.
- Do not read `.env` or storage-state files to work around Core.
- Do not treat source-derived selectors as statefully grounded.
- Do not invoke `run` for write/external-notification without explicit user
  confirmation, even after successful probe.

## Isolated Structural Dogfood

Invoking the identity-neutral dogfood command explicitly authorizes one normal
run against its loopback target. The runner checks public run readiness first,
passes a returned `--confirm-risk` id when required, invokes normal run exactly
once, and proves one process-local resource. This authorization never applies to
another URL and requires no knowledge of Spec inside Core.
