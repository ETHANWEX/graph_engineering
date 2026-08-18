# ADR-015: Acceptance lock, immutable freeze, delta, and revision

- Status: Accepted
- Date: 2026-08-17

## Context

Implementation must not start against an unconfirmed or mutable Contract.

## Decision

Drafts are mutable snapshots, but explicit Human confirmation atomically appends a frozen
`TaskContract`, its digest, confirmation record, and acceptance lock. Frozen rows cannot be updated.
A change is a structured `ContractDelta` referencing the source revision and confirming message;
applying it appends revision N+1 with the public `supersedes` reference. Repeated confirmation of
the same draft digest returns the existing lock.

## Consequences

Acceptance locks are Runtime gates. Revision never overwrites Contract history and all hashes are
recoverable and auditable.

