# ADR-033: Durable bounded parallel runtime, atomic budgets, and barriers

- Status: Accepted
- Date: 2026-08-19

## Context

Concurrent branch workers race for shared budgets and may be interrupted between a side effect and
its checkpoint. A process restart must not repeat completed work, and a durable barrier must cover
workers already active as well as branches not yet admitted.

## Decision

SQLite migration 8 adds parent-node/branch/node state and attempt records. Branch admission and each
nested attempt reservation use `BEGIN IMMEDIATE`: the transaction rechecks Run status/barrier,
reserves the shared call and optional declared cost budget, records the running attempt, and creates
any external-trigger intent before returning. No worker starts an Executor, Verifier, subprocess,
HTTP request, GitHub write, worktree mutation, or other effect without that committed reservation.

The local scheduler executes one durable branch step per wave through a finite worker pool. It
checkpoints each nested result and route before admitting later work. Checkpoints include branch and
nested-node state; recovery schedules only incomplete state. External idempotency keys include Run,
container node, branch, and nested node. A checkpointed handle is polled; a triggering row without a
handle is uncertain and blocks the branch without retriggering.

Pause, interrupt, and cancel first persist a Run barrier. Pending branches are not admitted after
that point. Active workers may finish only their already-started atomic call, then checkpoint and
settle. Pause preserves incomplete branch state for resume; interrupt/cancel durably cancel pending
branches, request cancellation for checkpointed external handles, and report residual effects.
Event JSONL flushing is serialized, while SQLite remains authoritative.

## Consequences

Bounded parallelism remains single-machine and in-process; distributed scheduling is out of scope.
SQLite writer serialization is intentional and keeps shared reservations race-free. An already
issued irreversible call cannot be rolled back and remains disclosed. Existing top-level serial
scheduling, migrations 1–7, Runtime Service, IPC, MCP, and Plugin behavior are unchanged.
