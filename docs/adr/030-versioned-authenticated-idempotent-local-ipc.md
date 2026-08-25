# ADR-030: Versioned authenticated and idempotent local IPC

- Status: Accepted
- Date: 2026-08-18

## Decision

IPC 1.0 is newline-delimited bounded UTF-8 JSON over IPv4 loopback. Every request carries protocol
version, request ID, idempotency key, operation, resolved project/workspace identity, and a random
endpoint capability. Responses are typed success/error envelopes. Major-version mismatch,
authorization failure, identity mismatch, invalid shape, oversized frame, timeout, or missing target
fails closed. Clients reconnect and retry only boundedly; mutations reuse one idempotency key.

Migration 7 records an immutable request fingerprint and completed response. A reused key with a
different fingerprint is rejected; the same mutation returns its prior response and cannot repeat a
Run or external effect. Read-only operations are never inserted in the replay ledger. Capabilities
are constant-time compared, omitted from persistence and response/error text, and the service does
not accept Python, shell, or expression source.

## Consequences

Provider, Codex, and MCP wire formats remain outside Core. Transport/infrastructure failures stay
distinct from business, Verifier, and Review results. Runtime barriers remain authoritative and are
checked at the typed Runtime boundary immediately before any IPC-triggered effect.
