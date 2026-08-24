# ADR-042: Non-authoritative, secret-safe observability provider boundary

- Status: Accepted for Phase 6F implementation
- Date: 2026-08-25

## Context

Runtime and provider operations need correlated traces and metrics, but exporter availability,
delivery order and collector retention cannot participate in authoritative scheduling or recovery.
Unbounded attributes and raw exception/log bodies would also leak secrets or create unsafe metric
cardinality.

## Decision

Add an internal OpenTelemetry-compatible provider protocol with contract version 1.0. It accepts
only stable span/metric names, an explicit identity object and allowlisted bounded attributes.
Trace identity is deterministically derived from persisted repository/Run identity; child spans
inherit context and concurrent/recovered work may add identity-derived links. Metric labels contain
only bounded enums and never Run, node, attempt, Session, handle, path, URL, branch or user values.

The default provider is disabled/no-op. The enabled implementation uses deterministic sampling, a
finite queue, finite batches and explicit flush/shutdown deadlines. Exporter initialization,
unavailability, timeout, partial failure and exceptions are contained as telemetry health facts;
exception text and provider responses are never re-exported. Queue overflow drops telemetry rather
than blocking or mutating product work.

Instrumentation is dependency-free at the product boundary. Optional SDK/exporter adapters must
declare compatible contract/version capabilities. Missing imports and mismatches have typed
fail-safe outcomes and never cause a product Run, Session, verifier, review, GitHub/report effect or
barrier action to be repeated or reclassified.

## Consequences

SQLite remains the only Run authority and no migration or public Core Schema is added. Recovery
reconstructs correlation from persisted identities, never collector data. Disabled or failing
telemetry preserves business return values/exceptions and read-only behavior. Real external export
requires separate target-specific Human authorization.
