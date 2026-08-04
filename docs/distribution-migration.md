# Distribution Name Migration

VerifySignal 0.22.x is the final release line under the `verifysignal-spec` distribution name.
The open-source project is moving to the simpler PyPI name
`verifysignal`; after the canonical release is published and verified, new
installations should use:

```sh
uv tool install verifysignal
```

Existing installations do not need an emergency migration. The
`verifysignal-spec` project on PyPI will remain installable and will not be deleted or yanked.
It will be frozen after its final migration release rather
than receiving future feature releases.

## Moving an existing installation

The old and canonical distributions contain the same Python import package and
console scripts, so they must not be installed side by side in the same tool or
Python environment. After `verifysignal` 0.23.0 or newer is visible on PyPI,
replace an existing `uv` tool installation in this order:

```sh
uv tool uninstall verifysignal-spec
uv tool install verifysignal
```

Uninstalling the global tool does not remove `.verifysignal/` from any project.
Those workspaces and their persisted schemas remain compatible with the
canonical distribution.

For an installation owned by `pip`, use the same interpreter or virtual
environment for both commands and uninstall the old distribution first:

```sh
python -m pip uninstall verifysignal-spec
python -m pip install verifysignal
```

Do not install the canonical distribution and then uninstall the old one: their
files overlap, so that reverse order can remove files belonging to the new
installation. If you are not ready to switch, keep using the final 0.22.x
release instead of installing both distributions together.

The distribution rename does not rename VerifySignal's technical and persisted
compatibility contracts. The canonical package continues to preserve:

- the `verifysignal_spec` Python import package;
- the `verifysignal` command and the `verifysignal-spec` executable alias;
- every existing `verifysignal-spec-*/v1` schema identifier;
- the `.verifysignal/` project workspace;
- existing `VERIFYSIGNAL_SPEC_*` environment variables;
- the `spec` workflow role;
- `/verifysignal-specify` and existing legacy skill aliases.

PyPI distributions are immutable identities, so the old and canonical names are
separate projects rather than a registry rename. Release notes will identify
the first verified canonical version. Until that version is available, the
installation commands elsewhere in this 0.22.x documentation intentionally
continue to install `verifysignal-spec`.
