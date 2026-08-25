# ADR-043: Optional local Project UI over authoritative snapshots

- Status: Accepted for Phase 6G implementation
- Date: 2026-08-25

## Context

The final scheduled Phase 6 enhancement needs a usable Project/Run presentation without making a
browser, event connection, cache, frontend framework, or second database authoritative. It must run
offline on Python 3.12/3.13 and preserve the existing local Runtime Service/Human Gateway boundary.

## Decision

Implement an optional Python standard-library HTTP presentation process. It binds IPv4 loopback,
calls the existing versioned Runtime Service through a narrow provider, renders escaped HTML with
package-owned CSS and a small dependency-free JavaScript controller, and exposes UI/API contract
1.0 JSON snapshots. The controller submits same-origin JSON forms and performs bounded conditional
polling without browser storage. Every response carries a snapshot identity derived from persisted facts;
clients discard older snapshots and fetch a full snapshot after gaps, reconnect, Runtime restart,
endpoint rotation, or stale detection. Polling queues and browser state are disposable.

Mutation requests require exact Host and Origin, a same-origin CSRF/session binding, bounded JSON,
and a request/idempotency identity. Natural language goes to `message`; confirmation goes to
`confirm`; other structured controls use the existing typed Gateway routes. Confirmation cards bind
the persisted pending action and its HumanMessage/intent/Run/Contract/revision/creation/expiry facts.
Same-request replay is idempotent; stale, expired, consumed under another request, wrong identity,
or mismatched snapshot fails closed. Accept never merges.

Untrusted values are text, never executable HTML/Markdown, event handlers, URLs, script or CSS. Security
headers enforce default-deny CSP, frame denial, MIME safety, no referrer and no-store. Requests,
responses, active handlers and poll frequency are bounded. Browser storage is unused.

## Consequences

No new product/runtime dependency, Node toolchain, CDN, SQLite migration or public Core Schema is
required. IPC 1.0 receives only additive read-only snapshot operations; old clients are unchanged
and old servers fail unknown operations closed. A real-browser/accessibility/platform matrix and
external deployment remain blocked/unverified until exact infrastructure is separately exercised.
