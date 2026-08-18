# Phase 2: Codex Executor and Memory

## Scope

Phase 2 connects the persistent serial Runtime to a real Codex CLI without making provider wire
formats part of Core. It implements:

- a provider-neutral Executor protocol for start, resume, review, cancel, and capabilities;
- Codex preflight/version/capability discovery, argv construction, JSONL parsing, structured final
  output, raw-event Artifacts, process supervision, and safe cancellation;
- durable Sessions and checkpoints, bounded same-node continuation, rotation, and restart recovery;
- deterministic bounded Context Packages, a rebuildable Repository Map, and structured Handoffs;
- one Git branch/worktree per Run, frozen control/evidence separation, and accepted-commit restart;
- fresh read-only Reviewer and Observer Sessions, review-fix routing, and non-interference rules;
- a declaration-only Command Verifier with timeout/output limits and failed/error separation;
- SQLite migrations, events, Artifacts, checkpoints, and foundational FinalReport evidence needed by
  these boundaries.

## Non-scope

Phase 2 does not implement Claude Code, natural-language intent recognition, Discovery/Human Gateway
product behavior, dynamic verifier generation, HTTP/remote CI, GitHub PRs, auto-merge, plugins,
MCP/UI product entry points, a daemon, semantic/vector search, parallel graphs, or later-phase
delivery/report enrichment. It never invokes Codex with
`--dangerously-bypass-approvals-and-sandbox`.

## Acceptance criteria

- Unsupported or unauthenticated Codex installations are rejected before a Session starts, and the
  detected version/capabilities are recorded.
- Recorded Codex JSONL fixtures parse into provider-neutral events/results; unknown events remain
  preservable and compatible. Raw stdout/stderr is immutable Artifact evidence.
- Start/resume/review/cancel use argv, structured output schemas, supported sandbox/approval flags,
  durable provider-neutral Session metadata, and checkpoint before subsequent routing.
- Completed attempts are not repeated after restart. Session loss does not lose Run state. Rotation
  follows explicit continuation/failure thresholds; every Reviewer uses a new Session.
- Context/Handoff output is deterministic and bounded, while Contract/global policy content is never
  summarized away. A new Session can continue using only the Handoff and referenced evidence.
- Repository Map rebuilds deterministically from Git-visible files.
- Every Run uses a distinct branch/worktree. Frozen control and historical evidence live outside the
  writable worktree and cannot be overwritten by an Agent. Accepted-commit restart materializes the
  requested commit without changing the source Run.
- Reviewer and Observer use fresh read-only Sessions and independent Context Packages. Review-fix
  runs affected verifiers before a fresh review. Observer success or failure cannot mutate main Run
  state, route, budget, implementation Session, or worktree.
- Command Verifier never evaluates shell source, enforces timeout/output limits, distinguishes
  acceptance failure from infrastructure error, and stores raw evidence.
- A committed pause/interrupt barrier prevents new Sessions, attempts, worktree writes, verifiers,
  and side effects. Interrupt requests process termination; inability to settle is reported as
  quiescing with an unverified residual effect.
- Contract/Graph/Verifier/acceptance-lock hash drift rejects recovery, including on Windows paths.
- The complete Phase 0–2 test suite, mypy strict, Ruff lint/format, public Schema 1.0 drift check,
  Graph CLI checks, and the explicitly enabled real-Codex fixture-repository acceptance pass, or any
  environmental blocker is reported accurately as unverified rather than replaced by a Fake.
