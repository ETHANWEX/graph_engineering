# ADR-016: Deterministic Contract-to-Graph compilation

- Status: Accepted
- Date: 2026-08-17

## Context

Confirmed requirements need a standard executable form without executing generated source.

## Decision

The compiler accepts only a frozen `TaskContract`. It emits a canonical serial graph with stable
IDs and allowlisted node/edge data: inspect, implement, declared verifier nodes, review, and deliver.
Verifier failures route through one bounded repair node; errors do not share that route. Ordering is
derived from sorted verifier IDs. Route conditions use the existing enum/operator model only.

## Consequences

The same Contract bytes always produce the same Graph bytes. Compilation never evaluates Python,
shell, templates, or model text.

