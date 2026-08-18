# ADR-027: Versioned final delivery reports for every terminal state

- Status: Accepted
- Date: 2026-08-18

## Decision

Runtime compiles each delivery bundle solely from persisted State/Event/Artifact/Git/external-handle
facts. Every terminal state produces the ten named delivery files. Bundle and file Artifacts are
content-addressed; report revisions append and cannot overwrite. The actual terminal reason is
rendered without success-shaped wording for failure, interruption, cancellation, or rejection.

## Consequences

Agent Session loss cannot prevent delivery. Later Human decisions add acceptance records and a new
report revision rather than changing an earlier report.
