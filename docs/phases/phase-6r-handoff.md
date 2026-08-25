# Recovery Gate R0 Handoff

- Status: Human-reviewed and approved on 2026-08-24 for one local delivery commit; push pending
  separate authorization.
- Branch: `phase/6-enhancements`.
- Predecessor: `f9ee0b330a5a22a99d48cb787356445d044fb2ae`.
- Delivery identity: the single child commit of the predecessor that contains this handoff. Its SHA
  is intentionally verified after creation rather than embedded in content that determines it.
- Remote Phase 6 ref: `origin/phase/6-enhancements` resolves to the same SHA.
- `origin/main`: `eedc46d1a607c6169cb43eca79ef56bdd137efac`.

## Authorization and history reconciliation

The original Phase 6B handoff was a pre-delivery snapshot and said the implementation was
uncommitted. A later audit found `f9ee0b3` locally and remotely without a versioned authorization
record. On 2026-08-24 the Human explicitly approved the exact full SHA as the Phase 6B delivery.
R0 records that decision and preserves history: no amend, reset, rebase, force-push, cherry-pick, or
main mutation occurred.

README, CURRENT, Phase 6B's handoff addendum, the Phase 6 roadmap, R0 scope, and the R0/6C prompts now
state the same current facts. Phase 6B's handoff also corrects an evidence typo: invalid Graph CLI
has always been contractually locked to exit 2, not exit 1.

## Reproducible tooling baseline

- Packaging support is explicit: Python `>=3.12,<3.14`, with Python 3.12 and 3.13 classifiers.
  Python 3.12 remains the mypy/Ruff minimum-language target.
- Pytest no longer forces the shared repository-local `.pytest-tmp` basetemp. On the normal host,
  the documented default `python -m pytest` works without a custom basetemp.
- Ruff root discovery excludes `.local` and `.pytest-*`, so inaccessible historical evidence does
  not crash lint discovery. Contributor commands continue to target `src tests` for formatting.
- Three R0 tests lock the Python support window, absence of a global repository basetemp, and Ruff
  ACL-evidence exclusions.
- Historical inaccessible temp/evidence directories were neither deleted nor tracked. The single
  `.pytest-r0-probe-20260824-a` directory created by this R0 diagnostic was path-validated and
  removed after the probe; it contained no delivery source and is not recoverable.

The managed filesystem sandbox changes ACLs on pytest-created temporary directories and therefore
produces setup/cleanup `PermissionError` failures independent of assertions. R0 does not disguise
those failures as product results. Final pytest evidence was run at the normal host boundary, where
the default command passed under both supported Python versions.

## Reconciled design locks

- ADR-003 and schema/migration drift evidence close the protocol-version and migration-strategy
  decision.
- ADR-007/008 and Phase 2 evidence close the Codex Session termination and external Memory prototype
  decision, while irreversible issued effects remain explicitly residual.
- ADR-019–023 and Phase 4 evidence close dynamic Verifier registry, generation, permission, and
  freeze lifecycle decisions.
- Container isolation is explicitly in the first formal-version route through Phase 6C, but remains
  unimplemented until that phase passes.
- The only remaining release-support lock is the Windows/Linux/macOS matrix, assigned to Phase 6E;
  current Windows evidence is not represented as cross-platform evidence.

## Final verification evidence

- Python 3.13.14 default host full regression: 190 collected / 186 passed / 4 skipped in 34.58s,
  exit 0.
- Python 3.12.10 default host full regression on the same final snapshot: 190 collected / 186 passed
  / 4 skipped in 33.95s, exit 0.
- R0, Schema/CLI, migration, Phase 6A Service/MCP, and Phase 6B Parallel focused suite: 45 passed in
  12.98s, exit 0.
- mypy strict: no issues in 124 source files, exit 0.
- Ruff root lint: all checks passed; Ruff format: 124 `src`/`tests` files check clean, exit 0.
- Schema export produced 36 files with zero committed drift. Migration 1–8 repeatability passed in
  focused and full coverage.
- Historical and Phase 6B valid Graph CLI exited 0. Phase 6B invalid Graph exited 2 with expected
  field paths. Verifier manifest validation exited 0.

The four skipped collected instances are the existing opt-in real-Codex acceptance cases. No skip
was added or weakened by R0.

## Changed areas

- Governance/status: DESIGN, README, CURRENT, Phase 6 roadmap, Phase 6B handoff addendum, R0 scope
  and handoff, and R0/6C startup prompts.
- Tooling: explicit Python support metadata, platform-managed pytest temporary root, Ruff historical
  evidence exclusions, and contributor verification guidance.
- Tests: `tests/test_recovery_gate_r0.py` with three tooling-contract tests.

No Runtime, protocol model, SQLite schema, public JSON Schema, MCP/IPC behavior, Plugin code,
parallel scheduler, or delivery provider implementation changed.

## Unverified evidence and next step

Real Codex tests remain opt-in. Real Codex Plugin load + MCP, real GitHub PR/Checks, Linux/macOS
Runtime/IPC/worktree/parallel, Container Verifiers, autonomous-delivery closure, telemetry, and UI
remain unverified or unimplemented and are assigned to later phases. Claude Code remains
unscheduled.

Human approved the R0 result and authorized the single local delivery commit containing this
handoff. No push, PR, main mutation, Plugin installation, external provider write, or Phase 6C
implementation is authorized by that decision.

Next step: verify the created local commit has predecessor `f9ee0b3`, contains only the reviewed R0
candidate, and leaves the worktree clean. Push requires separate Human authorization. Only after the
same R0 SHA is observed locally and remotely may a separately authorized Phase 6C start use
`docs/prompts/phase-6c-start.md`.
