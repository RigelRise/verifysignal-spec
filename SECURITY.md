# Security Policy

We take the security of VerifySignal, and above all the safety of your
credentials and evidence, seriously.

## Reporting a vulnerability

Please do not open a public issue for a security problem. Report it privately:

- <https://github.com/RigelRise/verifysignal/security/advisories/new>

Include the affected version (`verifysignal --version`), a description, steps to
reproduce, and impact. Never include real credentials, tokens, or captured
evidence. Redacted excerpts are enough.

## What to expect

We aim to acknowledge a report within a few business days, keep you updated, and
credit you in the release notes unless you prefer to stay anonymous. Once a fix
ships, we publish an advisory.

## Supported versions

VerifySignal is pre-1.0. Security fixes land on the latest release. Please upgrade
before reporting to confirm the issue still reproduces.

## Design notes

A vulnerability in the open CLI should not be able to leak your secrets:

- Credential values resolve from the environment at run time and are never
  written to `.verifysignal/`, reports, logs, or cache metadata.
- Tokens, receipts, and signed URLs are redacted from all output.
- The runtime is a signed package whose signature is verified before execution.

Reports about credential persistence, redaction gaps, signature verification, or
the entitlement flow are especially welcome.
