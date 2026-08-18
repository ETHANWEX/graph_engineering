# Phase 6B Handoff

- Status: implementation complete, uncommitted, and awaiting Human Review.
- Branch: `phase/6-enhancements`.
- Baseline/current committed HEAD: `55750075c7af208ebc508299752566a3f67eaeb5`.
- Baseline parent: `51fad9e05c4b4d68f25d9c8bd1d269dcb0cd129f`.
- `origin/main`: `eedc46d1a607c6169cb43eca79ef56bdd137efac`.

## Startup evidence

`git fetch origin` exited 0. Branch and HEAD matched the required Phase 6A delivery commit, whose
parent and handoff facts were consistent. No remote Phase 6 branch existed. Initial tracked and
nonignored untracked counts were zero; 9734 ignored historical environment, pytest, cache, and
evidence entries were preserved. The Phase 0–6A baseline collected 171 tests: 167 passed and four
opt-in real-Codex tests skipped. No partial Phase 6B implementation or unattributed modification was
present.

## Decisions and public compatibility

- ADR-032 adds explicit typed `parallel`, `subgraph`, and `join` nodes, stable branch IDs,
  serial-only branch Subgraphs, deterministic aggregate ordering, and fail-closed precedence.
- ADR-033 defines the durable bounded local scheduler, SQLite-serialized shared reservations,
  branch checkpoints/recovery, qualified external-effect identity, and active/pending barriers.
- Public Schema 1.0 grows additively from 30 to 36 files. Old node kinds and fields remain valid;
  old readers reject unknown parallel enum values fail closed. The historical serial Graph SHA is
  still `77b93993133ef786a481bb954db31c8ed4aca26fe54195cafbdaff36e7b3f267`.
- SQLite migration 8 adds `parallel_branches`, `parallel_branch_nodes`,
  `parallel_branch_attempts`, `parallel_branch_edge_traversals`, and
  `shared_budget_reservations`. Migrations 1–8 apply once. Phase 6A
  `service_migration_version` remains compatibility-capped at 7; `parallel_migration_version`
  reports actual head 8.
- Runtime Service, IPC 1.0, MCP tools, Plugin manifest/config, Executor/Verifier protocols, and
  existing serial Runtime behavior are unchanged at their boundaries.

## Implemented scope

- `ParallelSpec` admits two or more explicit branch Subgraphs through a finite
  `max_concurrency`; explicit `Subgraph` runs through the same durable branch machinery.
- A bounded `ThreadPoolExecutor` advances one durable branch step per wave. Nested identity is
  qualified as container/branch/node, and SQLite `BEGIN IMMEDIATE` atomically rechecks Run barrier
  and shared call budget before each attempt.
- `reserve_cost` provides idempotent, atomic shared cost reservations. Concurrent accepted
  reservations cannot exceed the configured Run or node cap.
- Branch/node/attempt/result/route state is checkpointed. Completed branches and checkpointed
  results are reused after same-Run recovery, pause/resume, or child checkpoint inheritance instead
  of repeating completed side effects. Checkpointed external handles are polled; an uncertain
  trigger fails closed without retriggering.
- Join reads the persisted canonical parallel result. Branch results are sorted by branch ID;
  changed files and Artifacts are deterministically deduplicated. Aggregate precedence is
  `error > blocked > failed > cancelled > succeeded`, so success never hides non-success.
- Pause preserves incomplete state. Interrupt durably cancels pending branches while active work
  settles. Cancel durably marks both active and pending incomplete branches cancelled before Run
  finalization; late worker results cannot mutate the terminal Run.

## Final verification evidence

- Phase 6B focused, host boundary: 16 passed in 7.32s, exit 0.
- Full Phase 0–6B regression, host boundary: 187 collected / 183 passed / 4 skipped in 34.95s,
  exit 0. The skips
  are the existing opt-in real-Codex tests.
- mypy strict: no issues in 123 source files, exit 0.
- Ruff lint: all checks passed; Ruff format: 123 files check clean, exit 0.
- Schema export: 36 files; expected-output drift tests passed, exit 0.
- Schema and migration focused suite: 10 passed in 2.70s, exit 0; migrations 1–8 remain repeatable.
- Historical valid Graph CLI and Phase 6B valid Graph CLI exited 0. Historical invalid and Phase 6B
  invalid Graph fixtures exited 1 with expected field-level validation errors.
- Deterministic Windows tests cover bounded concurrency, opposite completion orders, shared call and
  cost races, failed/blocked aggregation, completed-node restart, checkpointed external handles,
  checkpoint inheritance, pause/resume unresolved-result routing, and active/pending interrupt and
  cancel barriers.

Pytest's repository-local default basetemp encountered the known Windows ACL `PermissionError`
during cleanup/setup, without an assertion failure. Final focused and full evidence used fresh
isolated directories under the system temp directory and exited 0. The newly generated ignored
repository basetemp artifacts contain no delivery source and are not tracked.

## Security, invariants, and unverified evidence

SQLite remains authoritative. No branch starts a call after a persisted barrier, shared budget
updates are writer-serialized, external idempotency keys include qualified branch identity, and late
workers cannot mutate terminal results. Existing frozen input hashes, serial scheduling, read-only
queries, Runtime Service authentication, IPC replay, MCP validation, Plugin boundary, accept-never-
merge behavior, and historical data readability remain covered by the full regression.

All parallel evidence is deterministic local Windows evidence. Real Codex Plugin load + MCP E2E
remains unverified because Plugin installation and personal configuration were not authorized.
Cross-platform parallel scheduling is unverified. No GitHub/provider write, Plugin installation,
container execution, or other external side effect was performed.

## Changed areas

- Scope/status/decisions: README, CURRENT, Phase 6B scope/handoff, ADR-032–033, and Phase 6C startup
  prompt.
- Protocol/Schema: Graph container models, branch/parallel result models, six additive Schema files,
  and updated ExecutionGraph/Node schemas.
- Runtime/storage: parallel coordinator, engine integration, event flush serialization, thread-safe
  fakes, migration 8, branch snapshots, atomic cost reservation, checkpoints, recovery, and barriers.
- Tests/fixtures: Phase 6B valid/invalid Graph fixtures, model/Schema compatibility tests, durable
  parallel runtime tests, and migration 8 compatibility coverage.

## Explicit non-scope and next step

Phase 6C and later work, Container Verifier implementation, Claude Code Adapter, OpenTelemetry, UI,
distributed workers, OS services, Plugin installation/publication, automatic merge, and branch-
protection bypass were not started. No commit, push, PR, main mutation, rebase, cherry-pick, or
history rewrite was performed.

The exact next subphase is Phase 6C: Container Verifiers. Its ready-to-use startup prompt is
`docs/prompts/phase-6c-start.md`. It must not be used until Human Review approves Phase 6B and an
explicitly authorized single Phase 6B delivery commit exists.
