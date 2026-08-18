# Phase 3 Handoff

## Delivery summary and stacked baseline

- Design: `DESIGN.md` v0.2; scope: `docs/phases/phase-3.md`.
- Branch: `phase/3-discovery-contract`.
- Phase 2 approved/base commit:
  `53df64ceea904bdad1f39f04a5d3168f5ae40d25`.
- `origin/phase/2-codex-memory` and local Phase 2 were fetched and verified at that exact SHA before
  branch creation.
- Start-time `origin/main=a069b36fc0169dc51400265ea72a64c7b0b2839f`; Phase 2 was not merged.
- Final handoff recheck found the same remote SHAs: `origin/main=a069b36` and
  `origin/phase/2-codex-memory=53df64c`; Phase 2 was still not merged and Phase 3 history was not
  rewritten.
- Human explicitly authorized stacked development. No pseudo-merge, reset, force, rebase, main
  mutation, PR, or automatic integration occurred.
- Integration order is mandatory: Phase 2 before Phase 3.
- Delivery state: Phase 3 is intentionally uncommitted and unpushed pending Human review.

## ADRs

- ADR-012: HumanMessage, Conversation, and typed ControlIntent boundary.
- ADR-013: intent ambiguity, confidence, target, state, and confirmation policy.
- ADR-014: bounded pre-scan, unknowns, multi-turn Discovery, and draft recovery.
- ADR-015: explicit acceptance lock, immutable freeze, delta, and append-only revision.
- ADR-016: deterministic frozen Contract to standard Execution Graph compilation.
- ADR-017: revise/restart Contract and immutable parent/supersedes Run lineage.
- ADR-018: read-only query/Observer isolation and persisted pause/interrupt barriers.

ADR-001–011 and all Phase 0–2 invariants remain in force.

## SQLite migration 4

Migration 4 adds:

- `conversations`, `human_messages`, `intent_compilations`, `pending_confirmations`;
- `discovery_sessions`;
- `contract_drafts`, `contract_revisions`, `acceptance_locks`, `contract_deltas`;
- `planned_runs`.

State changes and audit outbox records share `BEGIN IMMEDIATE` transactions. Human message,
compiled intent, Discovery checkpoint, draft, confirmation, frozen revision, lock, delta, and
prepared Run are durable. Raw Codex JSONL/stderr remains in Artifact Store, not SQLite.

Phase 2 compatibility properties remain `schema_version == 2` and
`latest_migration_version == 3`; `storage_migration_version == 4` reports the real head.

## HumanMessage and ControlIntent boundary

- ConversationRepository appends the immutable public Schema 1.0 HumanMessage before compiling or
  applying any action; duplicate IDs are idempotent only for identical bytes.
- IntentCompiler returns existing `QueryControlIntent` or `StateChangeControlIntent`, never free
  text. status maps to progress query and report maps to evidence query.
- Multiple actions, unrecognized/low-confidence text, and missing Run targets return structured
  clarification with no Runtime call.
- pause/interrupt can apply only when explicit and targeted. revise/restart/accept/reject persist a
  pending confirmation first and recover it after process restart. Duplicate confirmation replays
  the stored result.

## Conversation and Discovery state machine

`ge start` creates/reloads the project Conversation from `.ge/control/phase3.db`. ProjectScanner
uses sorted Git-visible or filesystem entries with file-count/byte caps and a truncation flag.

Discovery persists `awaiting_answers` and `awaiting_confirmation` states. It asks for exact test or
acceptance method first and offers a concrete existing-test recommendation rather than inventing a
pass. It then captures acceptance, upstream/downstream interfaces, conventions, permissions,
delivery, and budget. Every answer checkpoints before the next question. Process restart restores
the same unknown list, answers, repository summary, draft, and pending confirmation.

## Contract draft, confirmation, and freeze

- Drafts use public TaskContract Schema 1.0 with `status=draft`.
- `ge start` displays canonical draft plus permission/risk summary. No acceptance lock, planned Run,
  Executor Session, verifier, or worktree is created before confirmation.
- Explicit confirmation atomically appends `status=frozen`, its digest, verifier digests,
  confirmation message ID, and AcceptanceLock.
- Reconfirming the same draft is idempotent. A different document claiming an existing revision is
  rejected. Frozen revisions have no update/replace operation.
- Immutable Contract, Graph, and lock JSON files are written below `.ge/control`; an existing file
  with different bytes is refused.

## Contract delta and revision

ContractDelta names its stable ID, Contract ID, exact source revision, Human-readable change, and
replacement description. It can only apply to the current latest frozen revision after explicit
confirmation. The result is revision N+1 with the public `supersedes` ContractRef. Source bytes and
lock remain unchanged.

## Contract to Execution Graph

ExecutionGraphCompiler accepts only a frozen Contract with a matching AcceptanceLock. It emits
stable inspect, implement, sorted verifier, repair, fresh-review, and deliver nodes. Only existing
enum/operator RouteCondition values route verifier passed/failed outcomes. Infrastructure error has
no failed-repair edge. The same Contract canonical bytes produce the same Graph canonical bytes and
SHA-256; no Python, shell, template, or model text is evaluated.

## RunRelationship and restart

RunPlanner writes a `prepared` Run only after freeze and lock validation. A revised/restarted Run
stores both `parent_run_id` and `supersedes_run_id` pointing to the source plus an optional typed
RestartFrom. The source row, Graph, Contract, and evidence are read but never updated. Missing
source Runs and mismatched locks are rejected.

## Query and pause/interrupt isolation

- Phase2Observer requires `ExecutorRole.OBSERVER`, `SandboxMode.READ_ONLY`, a fresh attempt, and the
  existing Phase 2 ReadOnlyRoleRunner.
- NaturalLanguageControlService snapshots the execution fingerprint before/after Observer calls;
  Observer failure or mutation cannot alter main state.
- GraphRuntime remains the only authority applying typed controls. Its pause/interrupt transaction
  commits the barrier before returning.
- DurableExecutorRuntime retains its persisted barrier check. PersistedBarrierGuard supplies the
  same check to CommandVerifier and GitWorkspaceManager. Tests prove natural-language pause blocks
  verifier start and worktree creation.

## Codex Discovery evidence

CodexDiscoveryAdapter uses:

- `codex --ask-for-approval never exec`;
- `--sandbox read-only`;
- `--json`, `--output-schema`, and `--output-last-message`;
- strict schema adaptation and independent Pydantic validation;
- immutable raw stdout/stderr Artifacts.

It never starts implementation and never uses dangerous bypass. Official OpenAI documentation:
<https://learn.chatgpt.com/docs/non-interactive-mode>.

Runtime facts: Windows, CPython 3.12.10, Codex CLI 0.147.0, authenticated using ChatGPT.

Real Phase 3 command:

```powershell
$env:GE_RUN_REAL_CODEX='1'
$env:GE_PHASE3_REAL_CODEX_FIXTURE_ROOT='E:\project\graph_engineering\.local\real-codex-phase3-discovery-final2'
.local\venv312\Scripts\python.exe -m pytest tests\test_phase3_real_codex_discovery.py -vv -s --basetemp E:\project\graph_engineering\.local\phase3-real-basetemp
```

Result: exit 0, 1 passed in 25.81s. It returned structured Discovery, identified missing test or
verification information, saved raw JSONL, and left fixture Git status unchanged.

The first sandboxed run exited 1 because Codex could not initialize its app-server under the host's
denied `C:\Users\ADMIN\.codex` ACL. The stderr Artifact was retained. The identical test then ran
at the approved host boundary and passed; no Fake substituted for this evidence.

Real Phase 2 regression command used a new isolated fixture and returned exit 0, 1 passed in
289.32s. The full implement → failed verifier → fresh Reviewer → resume fix → passed verifier →
fresh Reviewer → fresh Observer → SQLite recovery → interrupt path remained valid.

## Deterministic verification

Final expected inventory is 108 tests: 62 Phase 0–1, 29 Phase 2, and 17 Phase 3. The two explicit
real-Codex tests are skipped by default and passed separately. Commands used for final handoff:

```powershell
.local\venv312\Scripts\python.exe -m pytest --basetemp .local\verify-phase3-final
.local\venv312\Scripts\python.exe -m pytest --ignore-glob=tests/test_phase3_* --basetemp .local\verify-phase02-final
.local\venv312\Scripts\python.exe -m pytest --ignore-glob=tests/test_phase2_* --ignore-glob=tests/test_phase3_* --basetemp .local\verify-phase01-final
.local\venv312\Scripts\python.exe -m mypy src tests
.local\venv312\Scripts\python.exe -m ruff check src tests
.local\venv312\Scripts\python.exe -m ruff format --check src tests
.local\venv312\Scripts\ge.exe schema export --output schemas
git diff --exit-code -- schemas
.local\venv312\Scripts\ge.exe graph validate tests\fixtures\valid\graph.yaml
.local\venv312\Scripts\ge.exe graph validate tests\fixtures\invalid\graph.yaml
```

Final results: default exit 0, 108 collected / 106 passed / 2 skipped; Phase 0–2 exit 0,
91 collected / 90 passed / 1 skipped; Phase 0–1 exit 0, 62 passed. Mypy, Ruff lint, Ruff format,
Schema export, and Schema drift each exited 0. Valid Graph exited 0; invalid Graph exited 2 with the
expected field paths.

## Changed areas

- `conversation/`, `discovery/`, `contracts/`, `compiler/`, `control/`;
- `adapters/discovery.py`, `runtime/barriers.py`, migration 4, workspace guard;
- `ge start`, package version 0.4.0;
- ADR-012–018, Phase 3 scope/tests/README/CURRENT/this handoff.

No Phase 0–2 tests or public schemas were weakened or edited.

## Risks and unverified items

- Windows/Linux/macOS cross-platform real Codex was not tested; real evidence is Windows only.
- CLI is foreground and recoverable, not a daemon.
- Prepared Run creation does not implicitly start autonomous execution.
- Natural-language classification is deliberately conservative and may ask for clarification more
  often than a model-only classifier.
- Dynamic/HTTP/remote verifiers, GitHub delivery, Plugin/UI, auto-merge, parallel graphs,
  containers, and telemetry remain later phases.

## Worktree, commit, and integration state

- Branch: `phase/3-discovery-contract`, stacked on approved `53df64c`.
- Phase 2 was not merged into `origin/main` at Phase 3 start.
- All Phase 3 changes are uncommitted and unpushed for Human review.
- No PR exists and no merge was attempted.
- Phase 2 must be integrated before Phase 3. If main changes now, record it; do not rewrite Phase 3
  history without Human instruction.

## Next phase first step

Human reviews this implementation and evidence. Only explicit approval authorizes commit and push
of `phase/3-discovery-contract`. Integrate Phase 2 first, then Phase 3. Do not begin Phase 4 before
Phase 3 is reviewed and integrated into main.
