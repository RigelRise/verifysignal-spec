# VerifySignal Agent Guidance

Use `verifysignal-spec` from the target repository root. Keep generated project
artifacts and guidance in English, write run requests under
`.verifysignal/run-requests/`, write reusable skills under `.verifysignal/skills/`,
and never persist credential values.

For write and external-notification VerifySignal use cases, keep rerun recovery
inside the public workflow/CLI contract. Do not hand-edit `.verifysignal/`
`lastRun`, registry, readiness, or run-history state to bypass a write-safety
guard. Repair the authored `resourceIdentity`, generated runtime input,
collision policy, side-effect policy, or rerun policy through
`verifysignal workflow persist implement`, then validate and rerun.

Author write policies with canonical `sideEffectPolicy.allowed[]` and
`sideEffectPolicy.forbidden[]`; do not author
`sideEffectPolicy.rules[].effect/match`. Use only runtime-supported
confirmation signals, route normal owner-approved reruns after committed writes
through `verifysignal workflow approve-rerun`, route reviewed false-positive
write outcomes through `verifysignal workflow supersede-write-outcome`, and treat
generated identity bindings as `prepared/committed/discarded`.
