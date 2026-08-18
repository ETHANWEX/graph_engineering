# Phase 5 Handoff

## Baseline and branch evidence

- Latest fetched `origin/main`: `8adf9e2760cc525a613c3eb27fd0835d77525a9c`.
- Approved Phase 2: `53df64ceea904bdad1f39f04a5d3168f5ae40d25`.
- Approved Phase 3: `b746b3f6b9f70838a6fe063e8a90104be7bca8a8`.
- Approved Phase 4: `7410a66310f36799704e58cf743875d9383f5c87`.
- All three `git merge-base --is-ancestor <sha> origin/main` commands exited 0. The commit graph
  records PR #3, #4, and #5 in Phase 2 → 3 → 4 order, and Phase 2 is ancestor of Phase 3 while
  Phase 3 is ancestor of Phase 4.
- `phase/5-review-github-delivery` was created directly from `origin/main`; initial branch SHA,
  merge-base, and origin/main all returned the exact baseline above. Local main was not rewritten.
- Current HEAD is still the baseline SHA. All Phase 5 work is uncommitted and unpushed for review.

## Decisions and storage

- ADR-024: four-dimensional review, deterministic aggregation, and fresh attempts.
- ADR-025: requirement matrix and immutable evidence trust.
- ADR-026: GitHub identity, Checks, PR checkpoints, and uncertain effects.
- ADR-027: versioned delivery reports for all terminal states.
- ADR-028: Human decisions, barriers, and secret safety.
- SQLite migration 6 adds Phase 5 review attempts/dimensions, matrix revisions, GitHub queries,
  PR intents/handles, report revisions, terminal fixtures, and acceptance records. Compatibility
  properties remain 2/3/4/5; `delivery_migration_version == 6` is the actual head.
- Public Schema 1.0 remains unchanged: 30 committed schemas, zero drift. Phase 5 models are internal
  provider-neutral Pydantic models, so no public fixture or wire migration was required.

## Review protocol and routing

Each attempt creates four distinct Session slots for Contract, Correctness, Security, and Test
Adequacy. `CodexReviewDimensionAdapter` always constructs `ExecutorRole.REVIEWER` with read-only
sandbox and structured output. Context includes frozen Contract identity/criteria/hash, exact
baseline/target commits, diff Artifact, Verifier evidence, Repository Map, permissions, and risks;
it has no Implementer conversation or free reasoning.

Aggregation orders dimensions deterministically. Reviewer error or any blocked/blocking result wins;
otherwise changes requested wins; only unanimous clean results approve. Error never becomes changes
requested. A fix invalidates the whole attempt, records affected Verifiers, increments the durable
budget, and requires a new attempt/fresh Sessions after reverify. Old approvals remain evidence but
are not reusable.

## Requirement matrix

Every supplied frozen criterion ID creates one row with implementation, test, Verifier, CI, review,
and Human evidence columns. Only `sha256:<digest>` or explicitly frozen evidence is trusted.
Explicit negative evidence is failed; absent/mutable evidence is unverified with a reason. Contract
and matrix revisions append; `get` and fingerprint queries are read-only.

## GitHub provider boundary

- Exact owner/name/API host and commit SHA checks; HTTPS required except isolated loopback fixtures.
- Check states preserve queued/in-progress/completed/waiting/requested/pending and every documented
  conclusion. Unknown never maps to success. Auth, rate-limit, network, API, identity, and unknown
  status are separate provider failures. Query descriptors persist and resume after restart.
- PR identity key includes repository, Run, base, and head. Intent is committed before POST and
  number/URL/node ID immediately after 201. Recovery uses handle or exact discovery; an ambiguous
  prior POST stops without a second POST. Updates revalidate ownership; barrier is checked before
  discovery/create/update. Query/report has no PR write path.
- PR body renderer includes Contract/Run, matrix, Verifier/CI, review/verdict, unverified, effects,
  risks, Final Report/Artifact refs, and reproduction commands.
- No merge or branch-protection bypass operation exists.

## Final report and Human decisions

`DeliveryReportCompiler` reads persisted Runtime, matrix, review, Artifact, budget, event, control,
PR, handle, lineage, and secret-reference names. It freezes versioned content-addressed bundles with
the ten required filenames for succeeded/failed/interrupted/cancelled/rejected (and existing error)
semantics. Non-success summary text explicitly says delivery did not succeed. `ge report` only reads
the latest frozen revision and is tested not to change report/event counts.

Accept/reject/revise starts with append-only HumanMessage, passes the existing Intent Compiler and
explicit confirmation, and creates an idempotent acceptance record bound to actor/message/time,
Run/Contract/report revisions. Accept has `merge_performed=false`. Reject/revise calculate a new
Contract revision; where a real frozen Contract exists they call the append-only ContractRepository,
and revise creates Run lineage through RunPlanner. Historical data is never updated.

## Verification evidence

- Default: 156 collected / 152 passed / 4 skipped in 19.76s.
- Phase 0–4: 135 / 132 / 3 in 16.13s.
- Phase 0–3: 108 / 106 / 2 in 13.40s.
- Phase 0–2: 91 / 90 / 1 in 10.75s.
- Phase 0–1: 62 passed in 8.99s.
- mypy strict: 112 source files, no issues. Ruff lint and format check: pass.
- Schema export: 30; drift: none. Valid Graph/Manifest exit 0; invalid samples exit nonzero with
  expected field/policy errors.
- Real Codex: three independent structured read-only dimensions in an isolated Git fixture,
  1 passed in 302.10s. A preceding sandbox run failed only on basetemp ACL and is not counted.
- Isolated GitHub HTTP provider E2E: 1 passed in 0.85s; exact SHA success, checkpoint, restart, and
  one PR POST. Deterministic fixture evidence is labelled as such.

## Risks, authorization, and next step

- GitHub CLI 2.97.0 is installed and its `pr`, `run`, and `api` command surfaces were verified.
  `gh auth status` exits 1 because no GitHub host is authenticated, and no isolated real GitHub
  repository was authorized. Real GitHub E2E is unverified; no real PR was created or updated.
- Historical pytest basetemp ACL directories and ignored `.local` evidence were preserved.
- No commit, push, Graph Engineering PR, main mutation, merge, auto-merge, or Phase 6 work occurred.

Next step: Human reviews the uncommitted Phase 5 branch. Only explicit follow-up approval may
authorize commit/push. Integration and any real GitHub test remain separate decisions.
