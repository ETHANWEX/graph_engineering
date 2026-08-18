# ADR-029: Project-owned foreground Runtime Service lifecycle

- Status: Accepted
- Date: 2026-08-18

## Decision

Each resolved project root may own one foreground Runtime Service. A private `.ge/service`
directory holds an atomically replaceable endpoint descriptor and PID metadata; authoritative Run,
checkpoint, external-handle, conversation, and report data stays in the existing SQLite stores.
The service binds an ephemeral IPv4 loopback port, publishes health and independently versioned
Runtime/IPC/package compatibility, and supports an authenticated controlled shutdown. Startup
refuses a live owner, removes only a stale descriptor after identity checks, and never creates an OS
service or startup entry. Windows subprocesses use argv, resolved paths, explicit timeouts, and
best-effort descriptor cleanup in `finally`.

## Consequences

Codex and MCP lifetimes do not own Runs. Restart reopens persisted stores and recovery remains the
Runtime's responsibility. Project isolation is explicit and multi-project multiplexing is deferred.
