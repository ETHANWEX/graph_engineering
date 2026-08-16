# ADR-011: Read-only Reviewer/Observer and declarative Command Verifier

- Status: Accepted
- Date: 2026-08-16

## Context

Review and Human observation must not share or mutate implementation context. Deterministic command
verification must not become an arbitrary shell-code escape hatch.

## Decision

Reviewer and Observer calls always create fresh read-only Sessions with role-specific Context
Packages. Reviewer emits structured verdict/findings and cannot write the implementation worktree.
`changes_requested` routes to an Implementer fix, reruns declared affected verifiers, then creates a
new Reviewer attempt and Session. Observer results and costs are recorded separately; failure cannot
change the main Run state, route, budget, or Session.

Command Verifier accepts a non-empty argv list, cwd, environment-name allowlist, timeout, and output
byte cap. It never accepts a shell string and launches with `shell=False`. Exit zero is passed,
nonzero is verification failed, and spawn/timeout/oversize failures are classified infrastructure
errors. stdout/stderr are immutable Artifacts.

Pause/interrupt barriers are checked immediately before any Session, verifier, write, or side
effect. Interrupt requests termination of the supervised process; a process surviving the grace
period leaves the Run explicitly quiescing with residual-effect evidence.

## Consequences

Reviewer independence and Observer non-interference are enforceable boundaries rather than prompt
conventions. Command verification stays deterministic and auditable.
