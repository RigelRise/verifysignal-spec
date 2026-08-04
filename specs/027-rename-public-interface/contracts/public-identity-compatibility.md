# Public Identity Compatibility Contract

| Identity | Migration action | Canonical value | Compatibility guarantee |
|---|---|---|---|
| PyPI distribution | rename by new project | `verifysignal` | old `verifysignal-spec` final release remains installable |
| Product name | simplify | VerifySignal | no “Spec” suffix in new-user product prose |
| Private executable public label | simplify | VerifySignal Runtime | “Core” allowed in narrowly technical material |
| Python import | preserve | `verifysignal_spec` | byte-for-byte import path compatibility |
| Primary CLI | preserve | `verifysignal` | unchanged |
| Legacy CLI | preserve alias | `verifysignal-spec` | continues to invoke the same CLI |
| Workspace | preserve | `.verifysignal/` | no migration or rewrite |
| Versioned schemas | preserve | `verifysignal-spec-*/v1` | all existing identifiers unchanged |
| Environment variables | preserve | `VERIFYSIGNAL_SPEC_*` | existing automation remains valid |
| Workflow role | preserve | `spec` | no role migration |
| Slash command | preserve | `/verifysignal-specify` | existing integrations remain valid |
| Legacy skills | preserve aliases | `verifysignal-spec-*` | old installed workflows remain executable |
| GitHub repository | rename | `RigelRise/verifysignal` | old URL redirect retained and slug never reused |

New canonical names are acquisition identity. Preserved names are technical or persisted compatibility identity and must not be rewritten by broad search/replace.
