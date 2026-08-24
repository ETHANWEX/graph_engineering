# ADR-037: Confirmed preparation and explicit durable Run start

- Status: Accepted for Phase 6D implementation
- Date: 2026-08-25

## Decision

Contract confirmation atomically freezes the Contract, Verifier references and acceptance lock and
creates exactly one `prepared` Run. It never starts a Session, worktree, container, subprocess,
HTTP request or provider effect. A separate typed `run` request uses stable request and idempotency
identities. Runtime persists a start claim before materialization; completed claims replay their
result, while an executing claim with no authoritative outcome fails closed as uncertain.

## Consequences

Confirmation replay cannot duplicate Runs and Run replay cannot duplicate effects. Frozen hash
drift is rejected before start. SQLite remains authoritative across frontend disconnects.
