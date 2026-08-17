# ADR-014: Discovery scan, unknowns, and draft state machine

- Status: Accepted
- Date: 2026-08-17

## Context

Discovery must ask only material questions, recover across restarts, and avoid unbounded repository
ingestion.

## Decision

Discovery states are `collecting`, `awaiting_answers`, `draft_ready`, `awaiting_confirmation`,
`frozen`, and `superseded`. Pre-scan uses Git-visible sorted paths with file/count/byte limits and
records truncation. Unknowns are typed for objective, acceptance, tests, dependencies, conventions,
permissions, delivery, and budget. Missing tests always remains blocking until answered or the
Human explicitly accepts a concrete recommendation. Answers, draft snapshots, and pending
confirmation checkpoint transactionally.

## Consequences

Large source content stays in Artifact Store; SQLite stores bounded summaries and references.
Restart resumes the same question set and draft.

