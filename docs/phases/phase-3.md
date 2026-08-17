# Phase 3: Natural-language Discovery and Contract Freeze

## Scope

Phase 3 adds the persistent Human control plane that precedes and remains isolated from autonomous
execution:

- `ge start` project conversations and append-only `HumanMessage` persistence;
- schema-validated natural-language intent compilation for query, status, report, pause, resume,
  interrupt, revise, restart, accept, and reject;
- deterministic bounded repository pre-scan, unknown detection, multi-turn Discovery, and recovery;
- structured Contract drafts covering acceptance, tests, dependencies, conventions, permissions,
  budgets, and delivery;
- explicit confirmation, acceptance locks, append-only frozen Contract revisions and deltas;
- deterministic Contract-to-Execution-Graph compilation;
- new Run lineage for revise/restart without modifying the source Run;
- query isolation through the Phase 2 read-only Observer and durable pause/interrupt barriers;
- SQLite migration, checkpoints, audit events, artifacts, CLI entry points, and reports needed by
  these behaviors.

## Non-scope

Phase 3 does not add Claude Code, dynamic verifier code, HTTP/remote CI, GitHub PR management,
auto-merge, plugins, MCP/UI product entry points, a daemon, parallel graphs, containers,
OpenTelemetry, or Phase 4-6 delivery features. Model free text is never Runtime control and Codex is
never invoked with dangerous approval/sandbox bypass.

## Acceptance criteria

- Human text is persisted as `HumanMessage` before compilation and survives process restart.
- Query and mutation intents remain different protocol types. Ambiguous, low-confidence, or
  targetless destructive requests produce a pending clarification/confirmation, not a mutation.
- Repository pre-scan is sorted, deterministic, bounded, and reports truncation.
- Discovery persists unknowns and answers across turns and asks for missing verification or offers
  an explicit recommendation.
- A Contract draft cannot create an acceptance lock or autonomous Run before explicit Human
  confirmation. Duplicate confirmation is idempotent.
- Frozen Contract revisions are immutable and append-only; deltas identify source revision and
  Human confirmation.
- A frozen Contract deterministically compiles the same standard serial Execution Graph without
  evaluating source expressions.
- Revise/restart creates a new Contract revision and new Run relationship; the source Run remains
  unchanged.
- Natural-language status/report queries use a fresh read-only Observer and do not change node,
  route, budget, Session, or worktree state.
- Pause/interrupt persists a barrier before any new Executor, Verifier, Session, worktree write, or
  external effect can start.
- Conversation, Discovery draft, pending confirmation, acceptance lock, and control state recover
  from SQLite after Runtime restart, including Windows paths.
- Phase 0-2 tests, public Schema 1.0, mypy strict, Ruff, Graph CLI, and explicit real-Codex evidence
  remain valid.

