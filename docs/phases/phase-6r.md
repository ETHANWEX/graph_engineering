# Recovery Gate R0: Delivery and Baseline Reconciliation

- Status: implementation reviewed and approved on 2026-08-24; single local delivery commit
  authorized, push not yet authorized.
- Branch: `phase/6-enhancements`.
- Observed HEAD: `f9ee0b330a5a22a99d48cb787356445d044fb2ae`.
- Observed remote: `origin/phase/6-enhancements` resolves to the same commit.
- Authority: `docs/phases/phase-6.md` and this scope document.

## Objective

Restore a trustworthy cross-conversation state and a reproducible developer baseline before any
Phase 6C feature work. R0 records observable facts and requires Human decisions where provenance is
missing; it never manufactures retroactive approval.

## In scope

- Reconcile README, CURRENT, Phase 6B handoff, Git refs, delivery SHA, remote state, and review/
  authorization evidence.
- Record the Human's 2026-08-24 explicit approval of `f9ee0b3` as the Phase 6B delivery. No amend,
  force-push, reset, or rebase is allowed.
- Reconcile the supported Python baseline with the active environment. Verify Python 3.12 as the
  declared target and decide whether Python 3.13 is supported or merely incidental.
- Make the documented default verification path robust against repository-local pytest basetemp
  ACL residue. Root-level Ruff/search commands must avoid inaccessible generated directories.
- Audit the still-open `DESIGN.md` review items against ADR-003 and Phase 2/4 evidence; close them
  only with citations, otherwise carry them forward as explicit work.
- Re-run full tests, mypy strict, Ruff, schema drift/export, Graph/Verifier CLI, migration 1–8
  repeatability, and the relevant service/IPC/MCP/parallel focused suites.
- Produce `docs/phases/phase-6r-handoff.md` and a refreshed Phase 6C startup prompt.

## Acceptance

- README, CURRENT, handoffs, prompts, local refs, and remote refs contain no contradictory current
  state claims.
- The Phase 6B authorization decision is explicit, attributable to Human direction, and does not
  rely on commit subject text as proof.
- A fresh checkout can run the documented default verification commands without depending on
  inaccessible historical temp directories.
- Python and OS versions in evidence match the process that actually ran each command.
- Every previously unchecked design/release item is either closed with durable evidence or mapped
  to a named later phase.
- The reviewed uncommitted candidate contains only attributed R0 changes; after an authorized
  delivery commit, the worktree must be clean. All verification exits successfully.
- Human reviews R0 before its single reconciliation delivery commit; Phase 6C remains blocked until
  that commit is explicitly authorized.

## Explicit non-scope

R0 does not implement Container Verifiers, autonomous-delivery wiring, real external E2E,
OpenTelemetry, UI, Claude Code, distributed workers, automatic merge, Plugin installation, or a
real GitHub write. It does not rewrite or delete historical evidence directories without separate
targeted authorization.

## Required execution order

1. Record exact local and remote facts without fetching or mutating unless separately authorized.
2. Record the Human's 2026-08-24 Phase 6B authorization decision.
3. Repair status/handoff drift and verification configuration.
4. Reconcile old design locks and run the complete baseline.
5. Create the R0 handoff, report the uncommitted result, and wait for review.
6. Commit/push only after explicit approval; only then may Phase 6C start.
