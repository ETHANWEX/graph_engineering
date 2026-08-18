# ADR-010: Session persistence, Context Packages, Repository Map, and Handoffs

- Status: Accepted
- Date: 2026-08-16

## Context

Model context is temporary. Runtime must recover after process or Session loss and rotate contexts
without losing requirements, state, or evidence.

## Decision

SQLite migration 3 stores provider-neutral Sessions, supervised process handles, review attempts,
and verifier executions. Session IDs, process start, completion/cancellation, and critical results
checkpoint transactionally with append-only events. Default policy is fresh per node, bounded resume
within the same node, rotation after configured continuations/failures, and always-fresh review.

Context Builder emits deterministically ordered, byte-bounded packages containing node duty,
relevant immutable Contract content, global policy, Git status, upstream Handoff, current failure
evidence, file/Artifact references, and output Schema. Immutable Contract/policy/schema sections are
never summarized; overflow removes lower-priority references or fails explicitly. Repository Map is
a sorted, Git-aware, rebuildable inventory. Handoff fields are status, summary, changed files,
decisions, remaining risks, next actions, and evidence references.

## Consequences

Runtime, Git, Contract, Verifier, and Artifact storage remain facts; Session text is only a cache.
Fresh Sessions can continue from structured Handoff plus evidence references.
