# Data Model: Public Identity Migration

## DistributionIdentity

- `projectName`: `verifysignal-spec` or `verifysignal`
- `releaseRole`: `legacy-final`, `canonical-first`, or `canonical-post-rename`
- `version`: automation-derived from PR title
- `repositoryUrl`: must identify the live slug at publication time
- `consoleScripts`: `verifysignal`, `verifysignal-spec`
- `importPackage`: `verifysignal_spec`

## CompatibilityIdentity

- `kind`: schema, workspace, environment variable, workflow role, slash command, integration alias, or skill alias
- `value`: existing exact identifier
- `policy`: preserved
- `validation`: inventory snapshot plus focused behavior tests

## TrustedPublisherBinding

- `pypiProject`: `verifysignal`
- `owner`: `RigelRise`
- `repository`: `verifysignal-spec` before rename or `verifysignal` after rename
- `workflow`: `release.yml`
- `environment`: `pypi`
- State: `pending` -> `proven` -> `retired`; old binding is retired only after the new binding publishes successfully.

## MigrationStage

1. `legacy_active`
2. `legacy_final_published`
3. `canonical_publisher_ready`
4. `canonical_first_published`
5. `repository_renamed`
6. `canonical_new_publisher_ready`
7. `canonical_post_rename_published`
8. `migration_complete`

Transitions require the artifact and smoke evidence defined in `contracts/release-cutover.md`; no stage is skipped.

