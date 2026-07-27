# Research: Hermetic Update and Test Readiness

## Decision 1: Separate managed selection from development override

**Decision**: Store resolution mode and managed metadata separately; do not
overload the existing workspace `coreCommand`.

**Rationale**: A source checkout command can report the same version as a
release. Version alone cannot prove what artifact was exercised.

**Rejected**: Delete caches on every update. This removes valid verified
fallbacks and makes offline recovery worse without solving source selection.

## Decision 2: Resolve latest before accepting cache

**Decision**: Update asks the managed backend for latest, then looks for that
exact verified cache version.

**Rationale**: The current "any compatible cache first" behavior is correct for
ordinary readiness but cannot implement update semantics.

**Rejected**: Use `VERIFYSIGNAL_CORE_VERSION` during update. A local pin would
make update non-hermetic and reproduce the observed bias.

## Decision 3: Suggestions are not decisions

**Decision**: A URL learned from repository files, previous workflow state, or
generated artifacts is presented as a recommendation and stays pending.

**Rationale**: Local and staging URLs are product intent, not facts derivable
from source. Requiring per-workflow confirmation prevents accidental execution
against the wrong environment.

**Rejected**: Treat plan persistence as confirmation. The plan is AI-authored
and therefore cannot prove user intent.

## Decision 4: Explicit, strict environment files

**Decision**: Read environment files only through `--env-file`, accept a strict
non-executable subset, and allow only keys declared by the use case.

**Rationale**: This provides low-friction credential input without implicitly
opening broad local secret files or evaluating shell syntax.

**Rejected**: Automatically source `.env.local`. It may contain unrelated
secrets, shell expressions, or credentials for a different target.

## Decision 5: Prepare Git exclusion before the secret file

**Decision**: Resolve the repository's real Git directory, add an exact exclude
entry, verify it, then create/update the 0600 file.

**Rationale**: A partial failure must not leave a newly created secret file
eligible for commit.

**Rejected**: Add to project `.gitignore`. That creates an unrelated tracked
repository change and may conflict with project policy.
