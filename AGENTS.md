# Repository Working Agreement

## Branch Workflow

- Repository initialization, foundational documentation, and initial scaffolding may be committed directly to `main`.
- After initialization is complete, do not develop features or fixes directly on `main`.
- Create a dedicated branch for each subsequent implementation phase, feature, or fix.
- Keep each branch scoped to one reviewable objective.
- Run the verification required by the current phase before requesting integration.
- Merge a development branch into `main` only after its changes and verification evidence have been reviewed.
- Do not automatically merge Graph Engineering delivery branches unless the user has explicitly approved the result.

## Phased Implementation

- Treat `DESIGN.md` as the current architecture and implementation plan until an accepted ADR supersedes a decision.
- Implement only the active phase described in `DESIGN.md` and `docs/status/CURRENT.md`.
- Do not begin a later phase while the active phase has unmet acceptance criteria.
- At the end of each phase, update the cross-conversation handoff files required by `DESIGN.md`.

## Change Safety

- Preserve user changes and unrelated work already present in the workspace.
- Inspect the current branch, worktree status, and relevant handoff documents before editing.
- Keep frozen contracts, verifiers, acceptance locks, and execution evidence separate from writable implementation worktrees.
