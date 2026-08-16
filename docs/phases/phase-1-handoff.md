# Phase 1 Handoff

## Delivery summary

- Design: `DESIGN.md` v0.2.
- Phase: Phase 1, persistent serial Graph Runtime.
- Branch: `phase/1-runtime`.
- Base: `ece58b0` (Phase 0 merge on `origin/main`).
- Phase 1 implementation commit: `5bad314`; final handoff metadata commit is branch `HEAD`.
- Review/delivery: Human approved; delivery branch is ready for Human-controlled integration.
- PR/merge: no PR created, not merged.

Phase 1 implements the SQLite/JSONL/Artifact persistence boundary, deterministic serial Fake
Runtime, typed control barriers, recovery, Run inheritance, and basic terminal reports. It does not
implement any real Coding CLI, language model, daemon, HTTP pipeline, GitHub integration, or UI.

## ADRs

Existing invariants remain governed by ADR-001 through ADR-004. Phase 1 adds:

1. `docs/adr/005-persistent-runtime-storage.md` — SQLite authority, transactional event outbox,
   idempotent JSONL projection, and content-addressed artifacts.
2. `docs/adr/006-runtime-control-and-recovery.md` — deterministic transitions, execution barriers,
   hash-validated recovery, and external-effect uncertainty.

No public Schema 1.0 protocol changed; all 30 committed schemas remain byte-current after export.

## Migration and persistence

SQLite migration version 1 creates:

- `runs`, `nodes`, `attempts`, `edge_traversals`, `budgets`;
- `checkpoints`, `external_handles`, `control_intents`, `reports`;
- `artifact_metadata`, `event_outbox`, and `schema_migrations`.

Migration 2 adds stable checkpoint references, per-node duration/cost/repair accounting, Artifact
kind metadata, and role-scoped `run_artifacts` links. Migration application is repeatable from an
empty database and upgrades an existing migration-1 database.

Writer mutations use `BEGIN IMMEDIATE`. State changes enqueue immutable events in the same
transaction. `EventStore.flush` appends canonical JSONL, fsyncs, and then marks outbox delivery.
Read snapshots use read-only SQLite connections. Artifact content uses SHA-256 paths and atomic
rename.

## State machine and recovery

- Starting an attempt atomically verifies `running`, verifies no barrier, reserves budget, assigns
  stable `<run>:<node>:<number>`, and checkpoints before the Fake boundary call.
- Results checkpoint before restricted routing; edge traversals and repair usage are persisted.
- `failed` can enter a bounded repair edge; `error` remains operational and follows a separate edge
  or terminal report.
- Pause/interrupt commits a barrier before returning. The Scheduler settles the current Fake call
  but cannot start another node, attempt, or external trigger.
- Resume clears only a paused Run's barrier; Contract/Graph identity is unchanged.
- Recovery requires exact Contract and Graph hashes and never reruns completed attempts.
- A checkpointed handle is queried. `triggering` without a handle becomes terminal `error` with an
  unverified item and irreversible/unknown external effect; it is never retriggered or guessed.
- Parent and supersedes identifiers plus `RestartFrom` are preserved on the new Run.
- Parent/supersedes references must exist. Checkpoint ownership and exact Contract/Graph hashes are
  validated before the child Run transaction is committed.
- A checkpoint restart inherits committed node/result/route and Artifact-link state, resets the new
  Run's budget, turns an in-flight node back to `ready`, and leaves the source Run unchanged.
- Run and Node call/duration/repair limits and explicit cost charges are enforced before new work.
- Result checkpointing registers Artifact metadata/roles/events; FinalReport aggregates changed
  files and Verifier artifacts from persisted evidence.

## Verification evidence

Environment: Windows, CPython 3.12.10 (target runtime) and CPython 3.13.14 (compatibility rerun),
2026-08-16.

```powershell
py -3.12 --version
py -3.12 -m venv .local\venv312
.local\venv312\Scripts\python -m pip install -e ".[dev]"
.local\venv312\Scripts\python -m pytest --basetemp C:\Users\ADMIN\AppData\Local\Temp\graph-engineering-phase1-review-py312-final2
.local\venv312\Scripts\python -m mypy src tests
.local\venv312\Scripts\python -m ruff check src tests
.local\venv312\Scripts\python -m ruff format --check src tests
.local\venv312\Scripts\ge schema export --output schemas
git diff --exit-code -- schemas
```

Results:

- CPython: 3.12.10 installed for the current user and used from the ignored `.local/venv312`.
- Editable install: `graph-engineering 0.2.0` installed successfully under CPython 3.12.
- pytest: 62 passed (36 Phase 0 plus 26 Phase 1) on CPython 3.12.10.
- CPython 3.13.14 compatibility rerun: 62 passed; mypy strict and Ruff also passed.
- mypy strict: success, 0 issues in 31 source files.
- Ruff lint: passed.
- Ruff format: 31 files already formatted.
- Schema export: 30 schemas; drift check passed.

The first sandboxed Phase 0 run produced four setup `PermissionError` values because managed pytest
temporary directories received unreadable ACLs. The identical test suite was rerun outside that
sandbox boundary and passed; no assertion failed. This environment artifact does not affect the
repository implementation.

## Changed areas and committed work

- Added ADR-005, ADR-006, Phase 1 scope, and this handoff.
- Added `src/graph_engineering/runtime/` (store, events, artifacts, fakes, engine, errors, read types).
- Added four Phase 1 test modules, helpers, and two runtime fixtures.
- Updated README, CURRENT status, and package version/description.
- All listed Phase 1 changes are committed. No unrelated user changes were present or modified.

## Known risks

- SQLite/outbox state is atomic, while JSONL projection is intentionally eventually consistent.
- Exactly-once cannot be guaranteed for an external system that returns no recoverable handle.
- `accepted_commit` is validated structurally but is not materialized until Phase 2 introduces the
  Git worktree boundary; Phase 1 fully materializes only same-Graph checkpoint restart.
- Fake boundaries are synchronous; real process cancellation, Session formats, worktree isolation,
  Context Builder, and adapters remain Phase 2.
- Phase 1 FinalReport is foundational; full evidence matrices and GitHub delivery remain Phase 5.

## Next phase first step

After Human-controlled integration of this branch, create a new Phase 2 branch from updated `main`.
Begin with an ADR and failing tests for Codex preflight,
capability negotiation, and a provider-neutral Executor Adapter. Do not introduce provider-specific
Session wire formats into Core and do not auto-merge delivery branches.
