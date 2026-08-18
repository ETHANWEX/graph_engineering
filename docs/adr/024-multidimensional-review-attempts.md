# ADR-024: Multidimensional review and fresh attempts

- Status: Accepted
- Date: 2026-08-18

## Decision

Contract, correctness, security, and test-adequacy reviews are independent structured results from
fresh read-only Sessions. Input is limited to frozen Contract, exact Git baseline/target/diff,
Verifier evidence, Repository Map, and permission/risk facts. Review errors have their own status.
Aggregation is deterministic: any error or `blocked`/blocking finding blocks; otherwise any
`changes_requested` requests changes; only unanimous clean results approve. Fixes invalidate the
attempt, rerun affected Verifiers, and require a wholly fresh attempt. Attempts and fix budget are
persisted and append-only.

## Consequences

Implementer conversation and persuasive summaries are not review evidence. One approval cannot
offset another dimension's blocker, and pre-fix approval cannot be reused.
