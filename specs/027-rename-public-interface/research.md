# Research: Canonical VerifySignal Distribution

## Decision 1: Treat distribution, import, executable, and schema names separately

- **Decision**: Rename only the PyPI distribution and public product/repository wording. Preserve the Python module, both console scripts, versioned schemas, workspace, environment variables, role, slash command, and legacy skill aliases.
- **Rationale**: PyPI distribution metadata is independent of import/entry-point identity. Persisted/versioned identifiers are compatibility contracts rather than marketing labels.
- **Alternatives considered**: Global `spec` replacement. Rejected because it would break workspaces, integrations, imports, automation, and schema consumers.

## Decision 2: Use three releases and two trusted-publisher identities

- **Decision**: Publish final old-name patch, first canonical release under the old GitHub slug, then post-rename canonical patch under the new slug.
- **Rationale**: PyPI projects cannot be renamed; pending publishers use exact repository identity and do not reserve a name until first publish; repository redirects do not update OIDC identity automatically.
- **Alternatives considered**: Rename GitHub first or publish both projects indefinitely. The former risks first canonical publish; the latter splits acquisition and maintenance indefinitely.

## Decision 3: Keep release versions automated

- **Decision**: Use PR titles to produce patch/minor/patch releases and never hand-edit version files in feature branches.
- **Rationale**: Existing workflow updates `pyproject.toml`, `__init__.py`, changelog, tag, and release together.
- **Alternatives considered**: Manual version changes. Rejected because they compete with existing automation and can drift artifacts.

## Decision 4: Publish 0.23.0 with pre-rename repository metadata, then patch URLs

- **Decision**: The canonical distribution switch can merge while source URLs still identify the live `verifysignal-spec` repository; the post-rename patch changes URLs to `RigelRise/verifysignal`.
- **Rationale**: Metadata must not advertise a repository that does not yet exist, while the canonical package must be proven before the repository rename.
- **Alternatives considered**: Point 0.23.0 at a future URL. Rejected as another broken onboarding window.

## Decision 5: Freeze, do not delete, the old PyPI project

- **Decision**: Leave final `verifysignal-spec` release installable and not yanked, with a migration notice.
- **Rationale**: Existing lockfiles, tool installs, and recovery workflows need immutable historical artifacts.
- **Alternatives considered**: Delete/yank or continue dual feature releases. Rejected because deletion breaks users and dual releases obscure the canonical path.
