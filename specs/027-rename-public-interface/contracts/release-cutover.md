# Release Cutover Contract

## Stage A: Final old-name patch

- Branch: `fix/announce-verifysignal-distribution`
- PR title: `fix: announce the verifysignal distribution migration`
- Expected automated version: 0.22.1
- Required evidence: migration-notice contract, full pytest, artifact build/check, isolated old-name CLI smoke.
- Exit condition: release visible on old PyPI project and migration notice rendered.

## Stage B: First canonical release

- Manual prerequisite: pending trusted publisher for PyPI `verifysignal`, repository `verifysignal-spec`, workflow `release.yml`, environment `pypi`.
- Branch: `027-rename-public-interface`
- PR title: `feat: publish the canonical verifysignal distribution`
- Expected automated version: 0.23.0
- Required evidence: canonical wheel metadata; both console scripts; stable import/schema/workspace/env/role/skill inventory; full pytest/Docker; isolated canonical CLI and managed-Runtime smoke.
- Exit condition: canonical release is installable and verified before any GitHub rename.

## Stage C: Repository rename

- Rename `RigelRise/verifysignal-spec` to `RigelRise/verifysignal`.
- Do not recreate the old slug.
- Verify old web and Git remote redirects and new canonical source URL.
- Create the new exact PyPI trusted publisher for repository `verifysignal` before publishing.

## Stage D: First post-rename patch

- Branch: `fix/canonical-verifysignal-repository`
- PR title: `fix: canonicalize renamed repository publishing`
- Expected automated version: 0.23.1
- Required evidence: canonical repository metadata, release workflow environment URL, full regression, build/check, isolated install, successful OIDC publish under new binding.
- Exit condition: only after success may the old repository trusted-publisher binding be removed.

## Recovery Rules

- Never delete or yank the old PyPI project as part of this migration.
- Never reuse the old GitHub slug.
- Do not merge downstream Core or backend PRs until Stage D is green.
- If a stage fails, repair that stage without advancing external identities.

