# Security Policy

We take the security of VerifySignal and, above all, the safety of your
credentials and evidence seriously.

## Reporting a vulnerability

**Please do not open a public issue for a security problem.**

Report it privately through GitHub's private vulnerability reporting:

- <https://github.com/RigelRise/verifysignal-spec/security/advisories/new>

Include as much as you can — affected version (`verifysignal --version`), a
description, reproduction steps, and impact. **Never include real credentials,
tokens, or captured evidence** in a report; redacted excerpts are enough.

## What to expect

- We aim to acknowledge a report within a few business days.
- We will confirm the issue, keep you updated on remediation, and credit you in
  the release notes unless you prefer to remain anonymous.
- Once a fix ships, we will publish an advisory.

## Supported versions

VerifySignal is pre-1.0 and evolving quickly. Security fixes land on the latest
released version; please upgrade before reporting to confirm the issue still
reproduces.

## Scope and design notes

VerifySignal is built so that a vulnerability in the open CLI cannot leak your
secrets:

- Credential values are resolved from the environment at run time and are never
  written to `.verifysignal/`, reports, logs, guides, or cache metadata.
- Tokens, receipts, and signed URLs are redacted from all output.
- The managed runtime is a signed package whose signature is verified against an
  embedded release key before execution.

Reports about credential persistence, redaction gaps, signature verification, or
the entitlement flow are especially welcome.
