# Graph Engineering Project UI/API Contract 1.0

## Authority

All payloads are presentation snapshots of existing persisted facts. Runtime SQLite remains the
only Run authority. UI state, HTML, polling, connection order, cache and telemetry never route,
recover, verify, accept, reject, revise or prove a side effect.

## Routes

- `GET /`, `GET /runs/{run_id}`: escaped server-rendered Project and Run pages.
- `GET /assets/ui.css`, `GET /assets/ui.js`: immutable package-owned CSS/JavaScript with fixed MIME
  types. The script provides same-origin JSON form submission and one-at-a-time conditional polling;
  it uses no browser storage and contains no authoritative state.
- `GET /api/v1/project`, `GET /api/v1/runs/{run_id}`: full read-only snapshots.
- `POST /api/v1/messages`: one bounded Human message routed through `HumanMessage` and the Intent
  Compiler.
- `POST /api/v1/confirmations/{pending_action_id}`: one persisted confirmation-card request.
- `POST /api/v1/runs/{run_id}/actions/{action}`: typed pause/resume/interrupt/cancel/accept/reject/
  revise entry point; actions still obey Gateway policy and durable barriers.

## Snapshot and polling rules

Each response identifies contract version, project, generated time, source instance, snapshot
revision/digest and stale/terminal status. Clients accept only matching project/Run identities and a
strictly newer revision or matching digest. Duplicate/out-of-order responses are discarded. A gap,
instance change, endpoint rotation, disconnect or stale timeout requires a full snapshot. Terminal
late updates may add persisted report/decision facts but may never change the terminal Runtime Run.
Polling is conditional, one request at a time, and subject to finite rate/concurrency/output bounds.

## Confirmation cards

A card binds project, actor/session context, conversation, source HumanMessage, pending action,
typed intent and action, Run, Contract ID/revision/hash, creation/expiry, snapshot, request and
idempotency identities. Expired, stale, wrong-project, wrong-Run, wrong-revision, mismatched actor or
session, or consumed-by-another-request cards fail closed. Exact replay of a completed request may
return its prior response and never repeats an effect. Confirmation and execution remain separate.

## Security and rendering

Only loopback Host values and the exact same Origin are accepted. Mutations require the HttpOnly
session cookie, exact Origin, `Sec-Fetch-Site: same-origin`, and JSON MIME. Header/body/output/
concurrency/rate limits are finite. Responses use
default-deny CSP, `frame-ancestors 'none'`, nosniff, no-referrer and no-store. Untrusted text is HTML
escaped; Markdown is inert plain text; paths, repository/provider URLs, endpoints and commands are
not executable links. Raw errors, filesystem paths, credentials and configured secret variants are
rejected before response creation. Browser local/session storage is not used.
