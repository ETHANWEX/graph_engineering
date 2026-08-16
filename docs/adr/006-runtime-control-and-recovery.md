# ADR-006: Deterministic runtime control, recovery, and external effects

- Status: Accepted
- Date: 2026-08-16

## Context

The serial Runtime must make retries and routing deterministic, stop new side effects immediately
after Human control barriers, and recover without guessing whether external work happened.

## Decision

Run, node, and attempt transitions are allowlisted internal state machines. Starting an attempt is a
single SQLite transaction that checks the Run is `running`, checks no barrier exists, reserves
budget, and persists the running attempt before calling an Executor or Verifier. Result persistence
and route selection are separate checkpoints; the Scheduler rechecks the barrier before either a
new route target or external trigger starts.

`pause` and `interrupt` are typed `StateChangeControlIntent` actions. Their transaction persists the
barrier before returning. Pause lets the current atomic call settle and reaches `paused`; resume
clears the barrier on the same unchanged Run. Interrupt settles current state, terminates the Run as
`interrupted`, and freezes a report. Queries use typed `QueryControlIntent`, read-only SQLite
connections, and never invoke routing or executors.

Recovery requires exact Contract and Graph hashes. Completed nodes and attempts remain immutable.
External triggers use a stable `run_id + node_id` idempotency key. A `triggering` intent is committed
before the side effect; the returned handle is checkpointed before polling. Recovery queries a
saved handle and never triggers it again. If a crash leaves `triggering` without a handle, the
effect is uncertain: Runtime stops with `error`, records an unverified item/external effect, and
does not infer success, failure, rollback, or retry.

New Runs store `RunRelationship` and `RestartFrom` independently; old Runs and evidence are never
modified by inheritance.

Run and node budgets enforce call, duration, repair-iteration, and cost limits. Duration uses an
injectable UTC clock so boundary behavior is deterministic in tests. Executor adapters charge
provider cost through an explicit Runtime accounting operation; Phase 1 Fakes do not invent cost.

Parent and superseded Run references must already exist. A checkpoint restart must reference a
checkpoint owned by one of those Runs and must match the exact Contract and Graph hashes. A
checkpoint contains node/result/route and Artifact-link state. A new Run materializes that state,
resets its own Run budget, converts an in-flight node to `ready`, and never modifies the source Run.
Actual accepted-commit/worktree materialization remains Phase 2 because Phase 1 has no Git
worktree boundary.

## Consequences

The Phase 1 Runtime is intentionally serial and synchronous around Fake boundaries. Real Executor
session cancellation, process supervision, Context Builder, worktrees, and adapters remain Phase 2.
The barrier prevents new work after persistence but cannot pretend an already-running irreversible
operation was rolled back; reports disclose that limitation.
