# Phase 1: Persistent Graph Runtime

## Scope

Phase 1 implements the provider-neutral, single-machine, single-run, serial execution runtime:

- SQLite state and migration management.
- JSONL audit events backed by a transactional SQLite outbox.
- Content-addressed artifact persistence.
- Deterministic run, node, attempt, edge, budget, and terminal state transitions.
- Restricted conditional routing, retry limits, budget enforcement, and cancellation.
- Checkpoints, hash-validated recovery, and completed-node deduplication.
- Fake Executor and Fake Verifier, including checkpointed external handles.
- Read-only snapshots, `LiveReport`, typed Control API, pause/resume/interrupt barriers.
- Run relationships, restart roots, and basic reports for every Phase 1 terminal state.

## Non-scope

Phase 1 does not call Codex, Claude Code, language models, HTTP pipelines, dynamic verifiers,
GitHub, a Human Gateway, plugins, MCP/UI entry points, background daemons, parallel graphs, remote
workers, or Phase 2 context/session abstractions.

## Acceptance criteria

- Migrations are repeatable and state mutations roll back atomically on failure.
- Every committed state mutation records an outbox event that can be idempotently flushed to JSONL.
- Valid run/node/attempt transitions succeed and invalid transitions are rejected.
- A Fake Executor completes a serial graph and a failed implementation can traverse a repair loop.
- Verifier `failed` follows acceptance/repair routing while verifier `error` follows error routing.
- Retry and executor-call/repair budgets stop deterministically and produce a terminal report.
- Run and node call/duration/repair budgets plus explicit cost charges stop deterministically.
- Recovery rejects Contract or Graph hash drift, does not rerun completed nodes, and resumes from a
  committed checkpoint.
- A checkpointed external handle is queried after recovery instead of being triggered again; an
  unconfirmed trigger is reported as uncertain and is never guessed or retriggered.
- Repeated read-only queries do not change nodes, routes, executor context, main budget, or workspace.
- Once a pause/interrupt barrier commits, no new node, attempt, or external side effect starts.
- Pause reaches `paused`, resume continues the same Run, and interrupt reaches `interrupted`.
- Run inheritance preserves parent/supersedes and an explicit `RestartFrom` value.
- Checkpoint restart validates lineage and hashes, inherits committed node/route/Artifact state,
  resets the new Run budget, and leaves the source Run unchanged.
- Artifact metadata and role-scoped Run links are durable; basic FinalReport aggregates changed
  files and verifier evidence from persisted results.
- `succeeded`, `failed`, `error`, `interrupted`, and `cancelled` produce basic `FinalReport` objects
  that retain unverified items and irreversible external effects.
- Phase 0 tests, schema drift checks, mypy strict, Ruff lint, and Ruff format remain green.

## Verification

All acceptance criteria above are covered by the Phase 1 test suite. On 2026-08-16, the combined
Phase 0–1 suite completed with 62 passing tests on both CPython 3.12.10 and 3.13.14. Mypy strict,
Ruff lint/format, and export of the 30 unchanged public Schema 1.0 documents also passed. Exact
commands are recorded in `phase-1-handoff.md`.
