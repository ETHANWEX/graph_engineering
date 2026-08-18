# Phase 5: Review, GitHub, and Delivery

## Baseline

Phase 5 starts from `origin/main` at
`8adf9e2760cc525a613c3eb27fd0835d77525a9c`, after the approved Phase 2, 3, and 4
commits were merged in order. Development is confined to
`phase/5-review-github-delivery`.

## Scope

Phase 5 adds four independent, fresh, read-only review dimensions; deterministic review
aggregation and bounded fix/reverify/fresh-review attempts; append-only requirement matrices;
read-only GitHub Checks/Actions polling; checkpointed and idempotent Pull Request creation/update;
versioned delivery reports for every terminal state; and confirmed Human accept/reject/revise
records. GitHub and Codex wire formats stay in adapters. Runtime persistence remains authoritative.

SQLite migration 6 stores review attempts/results, requirement-matrix revisions, GitHub query and
PR handles/intents, report revisions/artifacts, Human acceptance records, and external effects.

## Non-scope

No merge or auto-merge, branch-protection bypass, production repository write, Phase 6 plugin/MCP/UI,
Claude adapter, parallel graph, container, telemetry, daemon, arbitrary shell/Python evaluation, or
secret persistence is included. Real GitHub PR E2E requires separate Human authorization for an
isolated repository; deterministic provider fixtures are not represented as real GitHub evidence.

## Acceptance criteria

- Contract, correctness, security, and test-adequacy reviews use distinct fresh read-only Sessions
  and structured results. Errors remain distinct from changes requested; aggregation cannot cancel
  a blocking result.
- A fix reruns affected Verifiers and creates a new review attempt; approval from an older attempt
  is never reused, and the persisted review/fix budget is bounded.
- Every frozen acceptance criterion has one matrix row. Missing or mutable evidence is unverified,
  queries are read-only, and a Contract revision creates a new immutable matrix revision.
- GitHub status is bound to an exact repository and commit, preserves all pending/completed
  conclusions, classifies provider/auth/rate-limit/network errors separately, and resumes polling
  without a write side effect.
- PR intent is checkpointed before creation and its handle immediately after success. Recovery does
  not duplicate creation; ambiguous creation stops and is disclosed; updates validate Run,
  repository, head, and base; barriers block every write. Merge is never performed.
- `succeeded`, `failed`, `interrupted`, `cancelled`, and `rejected` compile versioned immutable
  delivery bundles from persisted state/evidence without an Agent Session.
- Human accept/reject/revise enters as `HumanMessage`, compiles to typed confirmed intent, is
  idempotent, preserves history, and never merges. Reject/revise append Contract/Run lineage.
- Phase 0–4 schemas, migrations, tests, CLI behavior, and safety invariants remain compatible.
