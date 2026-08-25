# ADR-036: Durable container recovery, cancellation, and owned cleanup

- Status: Accepted
- Date: 2026-08-24

## Decision

SQLite migration 9 records stable execution and owner identities, qualified parallel-compatible
idempotency key, attempt, state, runtime handle, immutable image digest, config fingerprint,
result, byte accounting, cleanup outcome, and residual effect. Start intent is committed before the
adapter call and the handle immediately afterward. Recovery inspects a saved handle and never starts
again; a committed start without a handle is an uncertain effect and stops fail closed. Completed
checkpointed results are reused.

Pause starts nothing after its durable barrier and preserves recovery state. Interrupt/cancel asks
the adapter to stop an active handle, waits only for a bounded settlement, and records any surviving
or unknown effect. Cleanup uses the stable owner identity, is idempotent, and may remove only
resources belonging to that execution attempt. Cleanup failure is recorded separately from the
Verifier result and is surfaced as event/evidence/report data.

## Consequences

The provider is never the authoritative Run state source. Late results cannot change a terminal
Run, and Graph Engineering never claims cleanup when termination or owned-resource removal is
unknown.
