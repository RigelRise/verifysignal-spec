"""RATCHET (sibling-dispatch emitter wiring). Core's product-truth gate consumes
``repository_dispatch`` with the ``sibling-push`` event type, but sibling-only changes
never push to the Core repo — without an emitter the composed cross-repo verdict waits
for the daily cron. This workflow makes every push to main POST that dispatch. The
anti-waste/anti-injection design lives in workflow TEXT, so it is pinned as text:

- the trigger is push-to-main ONLY: a ``pull_request`` or ``schedule`` trigger would burn
  the Core repo's private Actions minutes on states that are not main. The gate composes
  the siblings' MAIN heads and ignores ``client_payload`` — repository/sha ride along for
  run-log observability only.
- the secret reaches curl via env indirection (``Bearer ${PAT}``), never ``${{ }}``
  inside ``run:``; exactly three expression expansions may exist (the PAT and the two
  trusted-context payload fields).
- ``--fail-with-body`` keeps auth failures loud: a revoked or under-scoped token must
  fail the run visibly, not pass silently while the gate quietly stops firing.
- the existing per-file ratchets (version-bump.yml, pr-title.yml, release.yml) read only
  their own files, so this new workflow cannot disturb them — and must never absorb
  their responsibilities.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DISPATCH_WORKFLOW = ROOT / ".github/workflows/sibling-dispatch.yml"


def _text():
    return DISPATCH_WORKFLOW.read_text(encoding="utf-8")


def test_triggers_only_on_pushes_to_main():
    workflow = _text()
    assert "push:" in workflow
    assert "branches: [main]" in workflow
    assert "pull_request" not in workflow
    assert "schedule" not in workflow


def test_targets_the_core_gate_with_the_exact_event_type():
    workflow = _text()
    assert workflow.count("https://api.github.com/repos/RigelRise/verifysignal-core/dispatches") == 1
    assert workflow.count("sibling-push") == 1


def test_authenticates_via_env_indirection_and_fails_loudly():
    workflow = _text()
    assert workflow.count("VERIFYSIGNAL_CROSSREPO_TOKEN") == 1
    assert "Authorization: Bearer ${PAT}" in workflow
    assert workflow.count("${{") == 3
    assert "--fail-with-body" in workflow
    assert "[skip ci]" not in workflow
