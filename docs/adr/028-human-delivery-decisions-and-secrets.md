# ADR-028: Human delivery decisions, side-effect barriers, and secret safety

- Status: Accepted
- Date: 2026-08-18

## Decision

Accept/reject/revise begins as append-only `HumanMessage`, passes the existing fail-closed Intent
Compiler and confirmation policy, then reaches a typed Runtime delivery API. Records bind actor,
message, time, Run, Contract revision, and report revision and are idempotent by message/intent.
Accept never merges. Reject requires a reason and appends a Contract revision; revise also creates
new Run lineage. Pause/interrupt barriers are checked transactionally before every GitHub write.

GitHub credentials are resolved only at the adapter call, redacted from all errors, events,
Artifacts, PR bodies, and reports, and represented elsewhere only by reference name.

## Consequences

Ambiguous or targetless decisions fail closed. Historical Contracts, Runs, diffs, reports, and
evidence remain immutable, and uncertain external effects are disclosed rather than retried.
