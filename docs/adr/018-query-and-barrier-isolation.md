# ADR-018: Read-only queries and persisted pause/interrupt barriers

- Status: Accepted
- Date: 2026-08-17

## Context

Natural-language control must preserve Phase 1-2 non-interference and barrier guarantees.

## Decision

Natural-language query/status/report compiles to query intent and uses a fresh Phase 2 read-only
Observer or deterministic persisted report. Main execution fingerprints are checked before/after;
query audit and Observer cost are separately scoped. Pause/interrupt calls the existing Runtime
transaction that persists the barrier before returning. Conversation orchestration rechecks that
barrier immediately before Executor, Verifier, Session, worktree write, or external-effect starts.

## Consequences

Observer failure cannot mutate the Run. A barrier cannot undo an already-issued effect, so any
uncertain residual effect remains disclosed rather than reported as rollback.

