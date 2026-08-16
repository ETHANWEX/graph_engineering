# ADR-009: Run worktrees and immutable control/evidence isolation

- Status: Accepted
- Date: 2026-08-16

## Context

Implementers need write access, while frozen Contract/Graph/Verifier/acceptance data and historical
evidence must not be writable from the implementation checkout.

## Decision

Each Run receives a deterministic, validated branch and a separate Git worktree. `.ge/control` and
Run state/artifacts stay under the control root outside that worktree. Agent Context Packages expose
them by content hash and read-only reference, never by writable copies. Worktree operations use Git
argv and resolved Windows-safe paths. Creation refuses an existing unexpected target.

`RestartFrom.accepted_commit` verifies the commit object and creates the new Run worktree at that
commit on a new branch. It never resets, cleans, or modifies the source Run/worktree.

## Consequences

Filesystem layout supplies the primary write boundary, while Codex sandbox is defense in depth.
Cleanup is explicit and never part of automatic phase delivery.
