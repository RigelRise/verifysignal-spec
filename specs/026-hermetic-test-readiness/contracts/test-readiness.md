# Test Readiness Contract

## Target gate

An inferred target produces a pending `browser-target-environment` question:

```json
{
  "status": "pending",
  "requiresConfirmation": true,
  "suggestedAnswer": {"baseUrl": "http://127.0.0.1:4100"},
  "suggestionSource": "repository-start-instructions"
}
```

Browser operations block with:

```json
{
  "code": "clarification.target-environment-confirmation-required",
  "questionId": "...",
  "recommendedTarget": "http://127.0.0.1:4100"
}
```

Only clarification provenance `direct-user` or `explicit-command` confirms the
target on the current workflow run.

## Credential preparation

```text
verifysignal credentials prepare ALIAS \
  --env-file .env.verifysignal.test.local \
  --json
```

The command never prints assignments. It writes only declarations derived from
the use case and only after exact Git exclusion is active.

## Explicit environment loading

The following commands accept the same `--env-file`:

```text
verifysignal validate ALIAS --runtime-readiness --env-file FILE --json
verifysignal probe --run REQUEST --skill SKILL --env-file FILE --json
verifysignal run ALIAS --env-file FILE --json
```

Accepted lines are blank, comments, `KEY=value`, and `export KEY=value`.
Single or double quotes may delimit one-line literal values. Interpolation,
substitution, backticks, multiline constructs, duplicate keys, invalid names,
and undeclared keys are blockers. No default dotenv path is consulted.
