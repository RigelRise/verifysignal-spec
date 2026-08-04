# Managed Runtime Entitlement Handoff

## Problem

VerifySignal owns the public user experience, and its open interface is open
source. If that interface is the only place where token validation happens,
users can bypass or modify the checks and still try to acquire or run the
private Runtime.

The user experience must remain smooth: users should install the public
`verifysignal` CLI and run it without manually downloading Core. Spec should guide
the unlock flow, acquire Core when allowed, verify it, cache it, and pass only a
signed entitlement receipt to Core.

## Recommendation

Use the option B architecture: token exchange plus signed entitlement receipt.

Spec should implement the public orchestration layer:

- ask for the email token during onboarding or runtime readiness;
- exchange the raw token with the official backend;
- receive a signed entitlement receipt;
- store only the receipt and non-sensitive cache metadata in user-scoped
  storage outside the target project;
- download Core artifacts through backend-authorized short-lived URLs;
- verify Core release metadata, detached signature, archive `sha256`, package
  contents, manifest, and `verifysignal-core version --json`;
- cache the verified runtime atomically;
- invoke Core only through the documented public CLI JSON contract;
- pass the entitlement receipt path to Core for protected operations;
- redact raw tokens, receipt payloads, signed URLs, credentials, local env-file
  values, source code, screenshots, browser storage, and private runtime paths.

## Options

### Option A: Manual Core installation after Spec install

Rejected. It creates the poor user experience we are trying to avoid: users
would install the public CLI and then discover they must manually fetch Core.

### Option B: Managed runtime acquisition with signed receipt

Accepted. Spec gives the user one guided flow while the authoritative boundary
remains in the backend and Core.

### Option C: Bundle Core inside the public Spec package

Rejected. It exposes private IP, makes public package distribution harder, and
removes the backend entitlement boundary.

## Shared Architecture

```text
verifysignal CLI
  readiness detects missing Core
  prompts for email token when needed
  exchanges token with verifysignal-be
  receives signed entitlement receipt
  fetches runtime metadata and signed artifact URL
  verifies and caches verifysignal-core
  passes receipt path into verifysignal-core

verifysignal-core
  validates receipt for protected operations
  emits public JSON only

verifysignal-be
  validates raw tokens
  signs receipts
  authorizes downloads
```

## UX Flow

1. User installs or runs the public `verifysignal` CLI.
2. Spec checks manual/dev overrides first.
3. If no usable Core runtime exists, Spec checks the user-scoped runtime cache.
4. If no valid cached runtime exists, Spec asks for the email token.
5. Spec sends the raw token to `verifysignal-be` over HTTPS.
6. Spec receives a signed entitlement receipt.
7. Spec stores the receipt in user-scoped storage with restrictive permissions.
8. Spec requests runtime download metadata for the host platform and required
   Core version.
9. Spec downloads Core through the short-lived signed URL.
10. Spec verifies release metadata, signature, archive hash, content boundary,
    manifest, and Core compatibility.
11. Spec atomically promotes the verified runtime into cache.
12. Spec runs Core with `--entitlement-receipt <path>` or the agreed environment
    variable.

Raw token lifetime is process-local only. It must be discarded immediately after
exchange.

## Storage Rules

Target project `.verifysignal/` may store only portable, non-sensitive workflow
state and non-sensitive readiness summaries.

User-scoped storage may contain:

- signed entitlement receipt file;
- runtime cache entries;
- release metadata and detached signatures;
- cache manifest with package id, version, platform, `sha256`, and verification
  timestamp;
- metadata consent decision.

User-scoped storage must not contain:

- raw email token;
- signed download URLs after use;
- credentials;
- local env-file values;
- source code snapshots;
- screenshots or browser storage;
- private runtime file listings beyond non-sensitive package identity metadata.

Receipt and config files should be written with restrictive permissions, such as
`0600` on POSIX systems. Prefer OS keychain storage for raw credentials if a
future flow introduces refresh secrets.

## Backend API Client Contract

Spec should call backend endpoints owned by `verifysignal-be`.

Token exchange:

```http
POST /api/entitlements/exchange
Cache-Control: no-store
Content-Type: application/json

{
  "token": "vs_...",
  "client": {
    "cliVersion": "0.1.0",
    "platform": "darwin-arm64"
  }
}
```

Runtime metadata:

```http
GET /api/runtimes/{coreVersion}?platform=darwin-arm64
Authorization: Bearer <signed-entitlement-receipt>
Cache-Control: no-store
```

The response should include the signed Core release metadata, detached metadata
signature, package size, archive `sha256`, and a short-lived archive URL. Spec
must treat the signed URL as a secret and never persist or print it.

## Runtime Verification

Spec should reuse the Core-owned runtime package contract:

1. verify detached signature over the exact release metadata bytes using a
   trusted Core release public key;
2. parse signed release metadata;
3. select the package for the host platform and required version;
4. download the archive through the signed URL;
5. compute archive `sha256`;
6. extract into a staging directory;
7. inspect the content boundary;
8. verify `manifest.json` hash and fields;
9. run `verifysignal-core version --json`;
10. compare Core version, public contract version, and operation metadata.

Only after all checks pass may Spec promote the runtime into the user cache.

## Blockers

Spec should surface actionable blockers without leaking secrets.

Recommended blocker codes:

- `entitlement.unlock-required`
- `entitlement.invalid-token`
- `entitlement.expired-token`
- `entitlement.expired`
- `entitlement.revoked`
- `entitlement.rejected`
- `runtime.download-unauthorized`
- `runtime.download-unavailable`
- `runtime.signed-url-expired`
- `runtime.metadata-signature-invalid`
- `runtime.package-integrity-mismatch`
- `runtime.unsupported-platform`
- `runtime.compatibility-mismatch`
- `runtime.entitlement-required-by-core`

## Implementation Tasks

- Add a backend client for entitlement exchange and runtime metadata/download
  authorization.
- Add receipt storage in user-scoped config/cache outside `.verifysignal/`.
- Add raw token redaction and signed URL redaction fixtures.
- Add runtime cache staging, safe extraction, verification, and atomic promote
- Add managed runtime readiness integration to `init`, `check`, `run`,
  `validate`, `repair`, and integration guidance where Core is required.
- Pass the receipt path to Core protected operations.
- Preserve manual/dev Core override precedence for local development.
- Add tests for first-run unlock, declined unlock, invalid token, expired
  receipt, cached offline use, download failure, tampered package, unsupported
  platform, Core entitlement rejection, and redaction.

## Acceptance Criteria

- A user can install the public CLI and complete Core acquisition through one
  guided unlock flow.
- Raw tokens are never persisted and signed URLs are never printed or stored
  after use.
- A valid receipt plus valid artifact metadata produces a cached
  `verifysignal-core` executable.
- Offline cached use works while the receipt remains valid.
- Expired, revoked, malformed, or Core-rejected receipts block protected
  operations with stable JSON/readiness blockers.
- Spec never imports private Core packages and never reads undocumented Core
  report internals.
