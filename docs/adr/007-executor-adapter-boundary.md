# ADR-007: Provider-neutral Executor and Codex Adapter boundary

- Status: Accepted
- Date: 2026-08-16

## Context

Phase 2 must call Codex while preserving ADR-001 and public Schema 1.0. Codex CLI arguments, JSONL
events, and thread identifiers can change independently from persisted Runtime semantics.

## Decision

Core defines immutable internal request, capability, Session-handle, event, result, and cancellation
types plus an Executor protocol with `start`, `resume`, `review`, `cancel`, and `capabilities`.
Provider handles are opaque strings with provider/version metadata; provider payloads never become
Core state-machine input. The Codex Adapter alone owns CLI argv and JSONL decoding. It validates the
final message against the requested JSON Schema and maps it to existing provider-neutral result
models. Raw stdout/stderr and unknown events are stored as Artifacts.

## Consequences

Public Schema 1.0 remains unchanged. Runtime persists neutral Session metadata and Artifact
references. A future provider can implement the same protocol without Codex branches in Core.
