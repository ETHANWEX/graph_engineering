# Phase 6 Roadmap

- Status: Recovery Gate R0 reviewed and approved on 2026-08-24; its single local delivery commit is
  authorized. Push and Phase 6C start remain separately gated.
- Baseline: `origin/main=eedc46d1a607c6169cb43eca79ef56bdd137efac`.
- Branch: `phase/6-enhancements`.
- Predecessor: Phase 5 implementation `db7dd54` and handoff
  `4ebeb2da969e3cce9210fc3ed8dc23dbf3986662`, both merged through PR #6.

## Authority and delivery model

This file is the authoritative cross-conversation roadmap for Phase 6. New conversations must read
it together with `DESIGN.md`, `docs/status/CURRENT.md`, and the latest Phase 6 handoff. Chat history
and model-generated summaries are not authoritative phase definitions.

By explicit Human decision, all Phase 6 subphases use the single long-lived
`phase/6-enhancements` branch. This is a Phase 6-specific exception to the usual branch-per-phase
workflow. Each completed subphase is prepared, verified, reviewed, and then recorded as its own
distinct delivery commit on that branch. A later subphase must not begin until the active subphase
meets its acceptance criteria and Human authorizes its delivery commit.

No Phase 6 commit, push, PR, main mutation, merge, history rewrite, or later-subphase start is
authorized merely by this roadmap. Each delivery action still requires explicit Human approval.

## Purpose

Phase 0–5 form the component-level Graph Engineering MVP. Phase 6 first reconciles delivery truth
and reproducibility, then adds isolation, closes the user-facing autonomous-delivery path, qualifies
real integrations, and finally adds observability and an optional presentation layer without
weakening the MVP contracts.

## Subphase roadmap

| Subphase | Delivery commit objective | Scope |
|---|---|---|
| Phase 6A | Runtime/MCP/Plugin | Independent Runtime Service, versioned local IPC, MCP Server, and thin Codex Plugin |
| Phase 6B | Parallel Graphs | Parallel nodes, subgraphs, deterministic join, bounded concurrency, recovery, budgets, and barriers |
| Recovery Gate R0 | Delivery and baseline reconciliation | Resolve Phase 6B authorization provenance, repair status drift, restore reproducible verification, and reconcile old completion locks |
| Phase 6C | Container Verifiers | Container provider, image policy, resource limits, mounts, networking, cancellation, and secret policy |
| Phase 6D | Autonomous Delivery Closure | Connect confirmed Discovery to explicit Run execution, control, verification, review, PR/report delivery, and terminal Human decisions |
| Phase 6E | Integration Qualification | Real Codex Plugin/MCP and GitHub E2E, supported-OS matrix, packaging/install/upgrade, and failure/recovery evidence |
| Phase 6F | Observability | OpenTelemetry traces and metrics correlated with persisted Runtime identities and safely redacted |
| Phase 6G | Optional Project UI | Project/Run pages, live progress, evidence and reports, Human messages, and confirmation cards |

This reordered roadmap is the explicit Human-requested response to the 2026-08-23 progress audit.
Additional Phase 6H–6N work may only be appended by an explicit Human decision that first updates
this roadmap. Claude Code Adapter remains intentionally unscheduled and is not part of Phase 6A–6G.

## Phase 6 invariants

Every subphase must preserve these Phase 0–5 invariants:

- Runtime persistence remains authoritative for Run state, routing, checkpoints, external handles,
  Review, Requirement Matrix, delivery, reports, and Human acceptance.
- `HumanMessage` remains the only natural-language input and Runtime accepts only strongly typed
  `ControlIntent`.
- Contract, Verifier, Review, evidence, Requirement Matrix, Final Report, and acceptance records
  remain append-only, frozen, versioned, or content-addressed as appropriate.
- Query, status, and report operations remain read-only.
- Pause and interrupt establish a durable barrier before stopping work; no new Agent, Verifier,
  subprocess, HTTP call, GitHub write, or other side effect may start after the barrier.
- Codex, MCP, Plugin, container, telemetry, and UI wire formats remain outside Core.
- Provider errors, infrastructure errors, business failures, verifier failures, and Review verdicts
  remain distinct.
- Secret values never enter prompts, protocol logs, events, exceptions, Artifacts, telemetry,
  reports, or UI output.
- Phase 0–5 SQLite data and historical Runs remain readable.
- Public protocol changes require an ADR, compatibility analysis, fixtures, migration, schema
  export, and drift tests.
- Default behavior never merges code automatically or bypasses branch protection.
- Arbitrary Python, shell strings, and expression source are never evaluated.
- Existing Phase 0–5 tests must not be weakened.

## Phase 6A: Runtime Service, MCP, and Codex Plugin

### Objective

Provide a persistent product entry point through a thin Codex Plugin and MCP Server while keeping
the independent Runtime and persistent stores authoritative. Closing Codex, replacing a Session,
disconnecting MCP, or compacting conversation context must not lose or alter a Run.

### Scope

- Independently managed local Runtime Service lifecycle, health, version, controlled shutdown, and
  restart recovery.
- Versioned local IPC with project/Run/workspace identity, request IDs, idempotency, typed errors,
  limits, timeout, reconnect, and bounded retry.
- `ge mcp-server` exposing the minimum `start`, `message`, `confirm`, `status`, and `report` tools.
- MCP routing through persisted HumanMessage, Intent Compiler, confirmation policy, typed
  ControlIntent, Runtime, and Report APIs without a mutation bypass.
- Thin repository-owned Codex Plugin with a valid manifest, Graph Engineering Skill, MCP
  configuration template, compatibility checks, and usage documentation.
- Windows process, path, endpoint, shutdown, and cleanup behavior.
- Necessary ADR, migration, schema, fixture, CLI, test, and handoff work.

### Acceptance

- Runtime state survives Codex/MCP disconnect and Runtime restart.
- Replayed mutation requests do not duplicate Runs or external side effects.
- Missing, ambiguous, expired, incompatible, or unauthorized requests fail closed.
- `status`, `report`, and query messages do not mutate persisted state.
- Pause/interrupt barriers prevent later IPC/MCP-triggered side effects.
- Plugin and MCP Sessions contain no authoritative Run state and never write SQLite or worktrees
  directly.
- Plugin, MCP, IPC, Runtime, and `ge` versions are checked explicitly.
- Secret values do not appear in protocols, logs, events, exceptions, Artifacts, or reports.
- Deterministic fixtures are not represented as real Codex Plugin/MCP E2E evidence.
- Phase 0–5 regression, mypy strict, Ruff, schema drift, migration, and Windows tests pass.

### Non-scope

Phase 6A does not implement parallel graphs, containers, OpenTelemetry, UI, Claude Code, distributed
workers, system startup services, Plugin publication, personal marketplace mutation, or automatic
merge.

## Phase 6B: Parallel Graphs

### Objective and scope

Add bounded parallel nodes, explicit subgraphs, deterministic join semantics, parallel checkpoint
and restart recovery, resource/budget coordination, result aggregation, and durable cancellation,
pause, and interrupt barriers.

### Acceptance direction

- Restart never duplicates completed branch work.
- Join output is deterministic regardless of completion order.
- A failed, blocked, or errored branch cannot be cancelled out by successful branches.
- Shared budgets cannot be overspent by races.
- Barriers cover active and pending branches.
- Existing serial Graph behavior remains compatible.

## Recovery Gate R0: Delivery and Baseline Reconciliation

R0 is a mandatory recovery gate, not a feature phase. Its scope and acceptance criteria are defined
in `docs/phases/phase-6r.md`. Phase 6C must not start until R0 has an explicitly approved delivery
record.

R0 resolves the repository fact that `f9ee0b330a5a22a99d48cb787356445d044fb2ae` exists locally and
on `origin/phase/6-enhancements`, while the checked-in README, CURRENT, and Phase 6B handoff still
describe a pre-commit state. R0 must record, but must not infer, whether that commit was authorized.

## Phase 6C: Container Verifiers

### Objective and scope

Add a container Verifier provider with immutable image identity, provenance/allowlist policy,
CPU/memory/process/time/output limits, mount policy, default-deny networking, secret references,
checkpoint, cancellation, cleanup, and residual-effect reporting.

### Acceptance direction

- Container infrastructure errors remain distinct from verifier failures.
- Mounts cannot escape authorized workspace paths.
- Frozen image/config drift is rejected.
- Secret values never enter commands, logs, events, Artifacts, or reports.
- Network and redirect policy cannot be bypassed.
- Residual containers, volumes, and effects are accurately disclosed.

## Phase 6D: Autonomous Delivery Closure

### Objective and scope

Close the product-level path from a confirmed Contract to an explicitly started durable Run and
then through implementation, verifier/review loops, GitHub delivery, terminal report, and Human
accept/reject/revise. Provide typed CLI and MCP/Plugin control surfaces for run, status, pause,
resume, interrupt, and terminal decisions without bypassing HumanMessage, confirmation policy, or
Runtime barriers.

### Acceptance direction

- A real Git fixture can traverse `ge start` discovery and confirmation through Run execution and a
  terminal delivery bundle without direct Python composition by the user.
- Confirmation and execution remain separate explicit actions; confirmation never silently starts
  side effects.
- Restart, pause, resume, interrupt, and revision preserve lineage and do not duplicate external
  effects.
- Verifier failure, infrastructure error, Review rejection, and delivery failure route distinctly.
- Every terminal outcome produces a report and no path merges automatically.

## Phase 6E: Integration Qualification

### Objective and scope

Qualify the implemented product boundaries in real, explicitly authorized environments. Cover
Codex Plugin installation/load plus MCP routing, real Codex execution, a disposable GitHub
repository with Checks and PR recovery, packaging/install/upgrade, and the declared Windows,
Linux, and macOS support matrix. Fixtures remain useful but cannot substitute for real E2E evidence.

### Acceptance direction

- Each claimed supported platform has repeatable install, service/IPC, worktree, subprocess,
  parallel-runtime, cancellation, and recovery evidence.
- Real Plugin/MCP and GitHub evidence is clearly separated from deterministic fixtures.
- Unsupported platforms and unavailable credentials are reported explicitly, not silently skipped
  in release evidence.
- Upgrade and migration tests cover existing Phase 0–6 data without rewriting historical records.
- A release-readiness report maps every product claim to evidence or an explicit limitation.

## Phase 6F: Observability

### Objective and scope

Add an OpenTelemetry provider boundary for Runtime, IPC, MCP, Agent, Verifier, Review, GitHub, and
Report traces/metrics correlated with persisted Run, node, attempt, Session, and external-handle
identities. Define sampling, bounded buffering, shutdown, exporter failure, attribute allowlists,
and redaction.

### Acceptance direction

- Telemetry is never authoritative or required for routing/recovery.
- Exporter failure cannot corrupt or change Runtime state.
- Secret values and unrestricted prompt/log bodies are never exported.
- Read-only operations remain read-only when instrumented.

## Phase 6G: Optional Project UI

### Objective and scope

Add an optional project/Run interface for live progress, risks, budgets, Contract, Requirement
Matrix, Verifier/CI, Review, Final Report, Human messages, and structured confirmation cards through
the existing Human Gateway and Runtime APIs.

### Acceptance direction

- UI never writes SQLite, worktrees, or provider adapters directly.
- Human messages still pass through HumanMessage and Intent Compiler.
- Confirmation cards bind to persisted, unexpired pending actions.
- Query pages do not mutate Runtime state.
- UI disconnect does not affect Runs.
- Untrusted report content is safely rendered and secrets remain redacted.

## Sequencing and commit discipline

Priority is intentionally asymmetric:

1. **P0 correctness of process:** R0 is immediate and blocks every later feature.
2. **P1 security and usable closure:** Phase 6C and 6D complete isolation and the main user path.
3. **P2 release claims:** Phase 6E proves real integrations and the supported-platform matrix.
4. **P3 enhancements:** Phase 6F and 6G add telemetry and presentation only after the product path
   is evidence-backed.

No UI or telemetry work may displace an unmet R0, isolation, autonomous-delivery, or qualification
acceptance criterion.

The default sequence on `phase/6-enhancements` is:

```text
roadmap commit
  -> Phase 6A delivery commit
  -> Phase 6B delivery commit
  -> Recovery Gate R0 reconciliation commit
  -> Phase 6C delivery commit
  -> Phase 6D delivery commit
  -> Phase 6E delivery commit
  -> Phase 6F delivery commit
  -> Phase 6G delivery commit
```

Before each subphase:

1. Verify the current branch, clean tracked worktree, current Phase 6 commit, and remote facts.
2. Read this roadmap, `CURRENT.md`, the previous handoff, all accepted ADRs, and relevant code/tests.
3. Create the phase scope document before implementation.
4. Implement only the active subphase.
5. Run full required verification and create `phase-6<letter>-handoff.md`.
6. Report uncommitted results and wait for Human Review.
7. Only explicit Human approval authorizes that subphase's delivery commit and push.

Review corrections must be completed before the single subphase delivery commit. A pushed commit is
never amended or history-rewritten; any post-delivery correction requires a separately authorized
fix decision and explicit audit record.

## Cross-conversation handoff

Each subphase handoff must record:

- Phase 6 branch and exact baseline/current commit.
- Predecessor commit and verification that the worktree contains it.
- ADRs, migrations, public protocol compatibility, and changed files.
- Implemented scope and explicit non-scope.
- Verification commands, exit codes, counts, and durations.
- Deterministic versus real E2E evidence.
- Risks, unverified items, and preserved invariants.
- Confirmation that later subphases and Claude Code were not started.
- The exact next subphase and a ready-to-use startup prompt.

Startup prompts currently exist at `docs/prompts/phase-6a-start.md`,
`docs/prompts/phase-6r-start.md`, and `docs/prompts/phase-6c-start.md`. Each later phase must create
the next prompt only after its scope and predecessor evidence are stable.
