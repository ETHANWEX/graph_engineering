# Phase 2 Handoff

## Delivery summary

- Design: `DESIGN.md` v0.2; scope: `docs/phases/phase-2.md`.
- Branch: `phase/2-codex-memory`; base: `a069b36` (`origin/main`, Phase 1 merge).
- Delivery state: implementation is intentionally uncommitted pending Human review; no push, PR,
  merge, or Phase 3 work.
- Existing ignored user note under `.local/` was preserved.

## ADRs

- ADR-007: provider-neutral Executor / Codex Adapter boundary.
- ADR-008: Codex capability/version/JSONL compatibility and native review limitation.
- ADR-009: per-Run Git worktree and external frozen control/evidence.
- ADR-010: Session, Context Builder, Repository Map, and Handoff.
- ADR-011: read-only Reviewer/Observer and declarative Command Verifier.

ADR-001–006 and all public Schema 1.0 invariants remain in force.

## SQLite migration

Migration 3 adds `executor_sessions`, `supervised_processes`, `review_attempts`, and
`verifier_executions`. Session rows store neutral provider/version/opaque handle, role, attempt,
continuation/failure counters, process ID, outcome, and raw Artifact references. Critical Session
start is paired with an outbox event. Completed attempt outcomes reload after a new Python Runtime
instance and are not invoked twice. The Phase 1 compatibility property remains 2; actual migration
head is exposed as `latest_migration_version == 3`.

## Executor and Adapter boundary

Core owns immutable requests, capabilities, Session handles, neutral events/results, policy, and
cancel semantics. `adapters/codex.py` alone owns help commands, argv ordering, CLI flags, JSONL event
names, strict output-Schema adaptation, and raw output. The Adapter never uses dangerous bypass.

Installed capability evidence:

- Codex CLI 0.147.0; authenticated via ChatGPT.
- exec JSONL/output-schema/output-last-message, resume, review, workspace-write/read-only, approval
  never, and process termination are available.
- Native `exec review` advertises output schema but returned a plain-text last message in a real
  run. Provider-neutral structured review therefore uses fresh read-only `codex exec` until a later
  preflight/fixture proves native behavior.

Official OpenAI Docs reference:
<https://learn.chatgpt.com/docs/developer-commands#codex-exec>.

## Session, recovery, Context, and Handoff

- Default fresh Session per node; bounded resume only for the same Implementer node; rotate after
  configured continuation/failure thresholds; Reviewer/Observer always fresh.
- Durable outcome replay prevents duplicate completed attempts after Runtime restart.
- Context sections are deterministic and byte-limited. Node duty, immutable Contract, global policy,
  and output Schema cannot be truncated; lower-priority evidence/references truncate deterministically.
- Repository Map is sorted and rebuildable from Git-visible files or a filesystem fixture.
- Handoff is strict status/summary/changed_files/decisions/remaining_risks/next_actions/evidence_refs.

## Worktree/control/evidence isolation

`GitWorkspaceManager` validates run IDs and resolved paths, creates `ge/run-<id>` branches and
separate worktrees with Git argv, refuses unexpected existing targets, and verifies commit objects.
Accepted-commit restart creates a new worktree at the selected commit without changing the source
worktree. Control and Artifact roots are outside Agent worktrees; frozen inputs are hash verified.

## Reviewer, Observer, and Command Verifier

- Reviewer and Observer requests enforce read-only sandbox and fresh attempt IDs.
- Observer compares the main execution fingerprint before/after and converts its own failure without
  changing the main Run.
- Review-fix coordinator enforces review → fix → affected verifier → incremented fresh review.
- Command Verifier accepts argv only, uses `shell=False`, and bounds timeout/output. Exit nonzero is
  acceptance `failed`; spawn/timeout/oversize are infrastructure `error`; output is Artifact evidence.

## Pause, interrupt, and process semantics

DurableExecutorRuntime checks the persisted Run barrier before starting a Session. ProcessSupervisor
exposes stable handles, query, terminate, grace timeout, and quiescing. The real acceptance resumed a
known Codex Session, observed its active process mapping, requested cancel, and verified settlement.

## Verification and real evidence

Target environment: CPython 3.12.10, Codex CLI 0.147.0, Windows.

Final deterministic verification:

| Command | Exit | Result |
|---|---:|---|
| `python -m pytest --basetemp <system-temp>/graph-engineering-phase2-final-suite-4` | 0 | 90 passed, 1 real test skipped; 91 collected |
| `python -m pytest --ignore-glob=tests/test_phase2_* --basetemp <system-temp>/graph-engineering-phase01-final` | 0 | 62 Phase 0–1 tests passed |
| `python -m mypy src tests` | 0 | success, 0 issues in 57 source files |
| `python -m ruff check src tests` | 0 | all checks passed |
| `python -m ruff format --check src tests` | 0 | 57 files formatted |
| `ge schema export --output schemas` + `git diff --exit-code -- schemas` | 0 | 30 Schema 1.0 files, no drift |
| `ge graph validate tests/fixtures/valid/graph.yaml` | 0 | valid |
| `ge graph validate tests/fixtures/invalid/graph.yaml` | 1 | rejected with field paths |
| real-Codex command below | 0 | 1 passed in 289.42s |

The 62 Phase 0–1 tests were not edited and all pass. Phase 2 adds 29 tests, for 91 distinct tests;
the default suite skips only the explicitly networked real-Codex test, which passed separately.

The final verification table is updated immediately before Human handoff. The completed real command
was:

```powershell
$env:GE_RUN_REAL_CODEX='1'
$env:GE_REAL_CODEX_FIXTURE_ROOT='E:\project\graph_engineering\.local\real-codex-fixture-persistence-2'
.local\venv312\Scripts\python.exe -m pytest tests\test_phase2_real_codex.py -vv -s
```

Result: exit 0, 1 passed in 289.42s. Raw JSONL, structured final messages, command evidence, and the
fixture Git state are under ignored `.local/real-codex-fixture-persistence-2`; they are not committed
public data. The test persists real Implementer, Reviewer, and Observer Session metadata plus a
structured Handoff, then constructs a new repository instance and recovers the completed Implementer
attempt from SQLite after a simulated Runtime restart. It also cancels a real in-flight known-Session
resume and confirms the worker settles.

Earlier attempts accurately failed for: Codex strict-Schema requirements, native review returning
plain text, and pytest-created Windows ACLs denying the Codex sandbox. Each was treated as an
infrastructure/capability fact and corrected at the Adapter or fixture boundary, never replaced by a
Fake pass.

## Known risks and unverified items

- Native structured review remains disabled for 0.147.0 as described above.
- Cancellation cannot guarantee an already-issued external effect was rolled back; a non-settling
  process is quiescing and must be disclosed.
- Linux/macOS real-Codex and worktree behavior were not exercised in this Windows phase run.
- Dynamic/HTTP/remote verifiers, Human Gateway, GitHub delivery, daemon, plugins/UI, and parallel
  execution are deliberately later-phase work.

## Next step

Human reviews the uncommitted Phase 2 diff and verification evidence. Only explicit Human approval
authorizes commit and push of `phase/2-codex-memory`; do not create a PR or merge, and do not begin
Phase 3 before integration.
