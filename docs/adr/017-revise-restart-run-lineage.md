# ADR-017: Revision, restart, and immutable Run lineage

- Status: Accepted
- Date: 2026-08-17

## Context

Direction changes must preserve the source Run, evidence, and worktree.

## Decision

Revise first establishes the source Run interrupt barrier, then opens a delta against its frozen
Contract. After confirmation it appends a Contract revision and creates a new Run with both
`parent_run_id` and `supersedes_run_id` pointing to the source. Restart additionally requires a
typed `RestartFrom`. Creation is transactional and never updates source Run rows.

## Consequences

Run history is a durable lineage. Phase 3 uses existing clean-base/checkpoint/accepted-commit
semantics and does not rewrite Git history.

