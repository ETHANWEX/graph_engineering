# ADR-005: Persistent runtime storage and transaction boundary

- Status: Accepted
- Date: 2026-08-16

## Context

Phase 1 must persist authoritative state in SQLite and append audit events to JSONL. A direct dual
write cannot atomically commit both files, while state changes must never exist without a durable
event record. Artifacts may be larger than SQLite rows and historical evidence must not be
overwritten.

## Decision

SQLite is authoritative for run state. Schema changes use monotonic migrations recorded in
`schema_migrations`. Every state-changing transaction inserts the corresponding immutable event in
an `event_outbox` row in the same transaction. After commit, the outbox is flushed to `events.jsonl`
using stable event IDs; recovery flushes any remaining rows. The JSONL sink deduplicates event IDs
already present, appends one canonical JSON object per line, flushes, and fsyncs before marking an
outbox row delivered.

SQLite uses foreign keys, WAL mode, explicit `BEGIN IMMEDIATE` writer transactions, and read-only
snapshot connections for reports. Runtime protocol payloads are canonical JSON, not Python pickle.

The Artifact Store is append-only and content-addressed by SHA-256. It writes a temporary file,
fsyncs it, atomically renames it, and refuses a digest collision. SQLite stores artifact metadata
and opaque relative references; large content does not live in state rows.

Migration 2 adds stable checkpoint references, per-node budget accounting, and `run_artifacts`.
Artifact content remains globally deduplicated while each Run records immutable role-scoped links
(`runtime`, `executor`, or `verifier`). Result persistence registers artifact metadata and its audit
event in the same state transaction as the result checkpoint.

## Consequences

State and its event intent are atomic, while JSONL delivery is eventually consistent and
idempotent. A crash can leave a pending outbox row but cannot leave an unaudited committed mutation.
Readers never take the Scheduler writer lock. Storage is internal Phase 1 data and does not revise
public Schema 1.0.
