# Phase 6G: Optional Project UI

- Status: Active implementation
- Branch: `phase/6-enhancements`
- Baseline / Phase 6F delivery: `ba30339922f9412cc369063efa2c136e0a3aef1f`
- Phase 6F parent / Phase 6E delivery: `e1aa9c61f568b7dda6c77248bc87a000f539a0ca`
- `origin/main`: `eedc46d1a607c6169cb43eca79ef56bdd137efac`
- Authority: `docs/phases/phase-6.md`, ADR-043 onward, and this scope

## Objective

Provide an optional local Project/Run UI over the existing Runtime Service and Human Gateway. It
renders authoritative snapshots, live progress, risk/budget/Contract/evidence/review/report facts,
Human Control Conversation messages, and persisted confirmation cards without creating a second
Run, pending-action, budget, decision, or recovery authority.

## Architecture and compatibility

Use Python standard-library HTTP with server-rendered HTML, package-owned dependency-free CSS/
JavaScript assets, versioned JSON snapshots, same-origin JSON form submission, and bounded polling.
The default bind is IPv4 loopback only. There is no Node.js,
npm, React, browser driver, external CDN, analytics, font, runtime dependency, SQLite migration, or
public Core Schema change. Product/package remains 0.8.0; Python remains `>=3.12,<3.14`; Runtime API,
IPC and MCP remain compatible at 1.0; migration head remains 10 and public Schema count remains 36.

## Authority and mutation boundary

- UI code never opens SQLite or writes worktrees, Artifacts, checkpoints, provider handles, frozen
  inputs, acceptance evidence, or qualification files.
- Snapshot reads and mutations traverse a provider backed by the existing Runtime Service/Human
  Gateway. Natural language is persisted as `HumanMessage` before compilation. Controls remain
  typed intents guarded by existing confirmation, replay and durable-barrier semantics.
- Confirmation cards bind project, actor/session context, source HumanMessage, pending action,
  intent action, Run/Contract/revision, creation/expiry, request/idempotency and snapshot identity.
- Accept records a Human decision and never merges. Query/status/report have no mutation path.
- Polling is observational and disposable. A gap, stale response, refresh, disconnect or Runtime
  restart recovers from a fresh authoritative snapshot; no event stream or browser state is a fact.

## Pages and safety acceptance

- Project overview, Run list/detail, node/attempt/parallel/Session state, risks and budgets.
- Frozen Contract and revision, Requirement Matrix classification, Verifier/repair, Review/fix,
  read-only GitHub handles, Final Report and Artifact metadata.
- Human messages plus pause/resume/interrupt/cancel/accept/reject/revise structured entry points and
  persisted confirmation cards.
- Honest blocked/unverified/partial/failed/error/stale/disconnected/late status text.
- Strict Host/Origin checks, same-origin CSRF, CSP, frame denial, nosniff, referrer policy, no-store,
  safe MIME, HTML escaping, inert untrusted Markdown/report/Artifact content and non-clickable
  untrusted paths/repository URLs/endpoints/commands.
- Bounded headers/body/frame/output/concurrency/poll cadence and slow-client behavior; generic
  secret-safe errors and no secret or authoritative state in browser storage.
- Semantic headings, labels, tables, focus visibility, keyboard operation, live status text and no
  color-only meaning.

## Evidence boundary and non-scope

Default tests use in-process HTTP and deterministic Runtime fixtures. They do not claim a real
browser matrix, external hosting, CDN, TLS/DNS, container, GitHub, collector, Codex Plugin load, or
cross-platform UI deployment. Missing authorized real browser infrastructure is reported
blocked/unverified, never skipped-success. Claude Code, distributed workers, OS startup services,
publishing, analytics, remote telemetry and auto-merge are out of scope.
