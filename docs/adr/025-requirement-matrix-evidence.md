# ADR-025: Versioned requirement matrix and evidence trust

- Status: Accepted
- Date: 2026-08-18

## Decision

Each frozen Contract revision owns immutable matrix revisions containing exactly one row per
acceptance-criterion ID. Rows separately reference implementation, test, Verifier, CI, review, and
Human evidence. `verified` requires frozen or content-addressed evidence; absent or mutable evidence
is `unverified`, and explicit negative evidence is `failed`. Queries never project or mutate status.

## Consequences

Agent prose alone cannot verify a criterion. Contract revision changes append history instead of
overwriting a matrix.
