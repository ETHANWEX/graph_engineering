# Phase 6B: Parallel Graphs

- Status: Implementation complete; uncommitted and awaiting Human Review
- Branch: `phase/6-enhancements`
- Baseline: `55750075c7af208ebc508299752566a3f67eaeb5`
- Predecessor: Phase 6A delivery commit

## Objective

Extend the authoritative local Graph Runtime with explicit, bounded parallel execution while
preserving serial Graph behavior, historical SQLite data, frozen inputs, typed failure semantics,
and the Phase 6A Runtime Service/IPC/MCP/Plugin boundary.

## In scope

- Strongly typed `parallel`, `subgraph`, and `join` graph nodes with explicit branch subgraphs.
- Deterministic validation, branch identity, result aggregation, and join output independent of
  worker completion order.
- Runtime-configured bounded concurrency with no distributed worker or remote scheduler.
- Atomic shared Run and node budget reservation before each branch attempt.
- Durable branch/node/attempt state, checkpoints, and restart recovery. A completed branch is never
  rerun, and checkpoint inheritance preserves completed branch state without modifying its source.
- Stable external-effect identity per Run, parallel node, branch, and nested node; recovery polls a
  checkpointed handle and never blindly retriggers an uncertain effect.
- Pause, interrupt, and cancel barriers covering both active and pending branches before any new
  Executor, Verifier, subprocess, HTTP, GitHub, worktree, or other effect starts.
- Deterministic Windows stress and recovery tests plus full Phase 0–6B regression evidence.

## Result and failure contract

Branch results are ordered by declared branch ID, never completion time. Aggregation is fail closed:
`error` outranks `blocked`, which outranks `failed`, then `cancelled`, and only unanimous success is
`succeeded`. A successful branch cannot offset a non-success branch. Join consumes the persisted
parallel result and emits the same canonical aggregate on every recovery.

## Compatibility and persistence

Existing serial Graph documents and public fields remain valid and follow the existing scheduling
path. New Graph node kinds and their typed definitions are additive and require ADR, exported Schema,
valid/invalid fixtures, and drift tests. SQLite migration 8 is monotonic and repeatable; migrations
1–7 and all compatibility properties remain readable. Provider-specific, IPC, MCP, and Plugin wire
formats do not enter Core.

## Acceptance

- A deterministic stress test proves active branch count never exceeds the configured bound.
- Concurrent attempts cannot reserve more shared calls or cost than the Run budget allows.
- Different completion orders produce byte-identical aggregate/join results.
- Failed, blocked, errored, or cancelled branches remain visible and prevent successful join status.
- Restart executes only incomplete branches/nodes and never repeats a completed side effect.
- Persisted external handles are polled, not triggered again; an uncertain trigger stops fail closed.
- Pause/interrupt/cancel persist a barrier before preventing pending starts and settling active work.
- Serial fixtures, historical migration tests, Runtime Service/IPC/MCP/Plugin tests, mypy strict,
  Ruff, Schema export/drift, and full pytest remain green.

## Explicit non-scope

Phase 6C or later work, container Verifiers, OpenTelemetry, UI, Claude Code Adapter, distributed
workers, OS services/startup, Plugin installation/publication, automatic merge, branch-protection
bypass, and history rewriting are prohibited.
