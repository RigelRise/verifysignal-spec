<!-- Thanks for contributing! Keep PRs focused and see CONTRIBUTING.md. -->

## What and why

<!-- What does this change and why? Link the issue it addresses. -->

Closes #

## Type of change

- [ ] Fix (patch)
- [ ] New backwards-compatible capability (minor)
- [ ] Breaking change (major)
- [ ] Docs / infra only

## Checklist

- [ ] `python -m pytest` is green
- [ ] Added/updated tests first (red → green) for behavior changes
- [ ] Existing behavior preserved, or intentionally migrated with coverage for old and new paths
- [ ] No private Core imports; interaction stays behind the public CLI JSON contract
- [ ] No secret-looking values added to code, tests, docs, or examples
- [ ] PR title follows Conventional Commits and carries the intended release class (`feat`/`fix`/`!`); the version itself is bumped by automation after merge — do not hand-bump
- [ ] Docs updated if user-facing behavior changed
