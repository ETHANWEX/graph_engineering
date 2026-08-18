# ADR-013: Intent confidence, ambiguity, targets, and confirmation

- Status: Accepted
- Date: 2026-08-17

## Context

Misclassifying a query as a destructive action could stop work or freeze an incorrect decision.

## Decision

Intent compilation returns either a validated typed intent or a structured pending action. Query,
status, and report are read-only. Pause and interrupt may apply only when explicit and targeted.
Resume requires a paused target. Revise, restart, accept, and reject require an explicit Run target
and Human confirmation. Confidence below the configured threshold, conflicting actions, or missing
targets produces clarification and no Runtime call. Duplicate confirmed action IDs are idempotent.

## Consequences

The compiler may fail closed. Confirmation and rejection are auditable records. No model-generated
free text can bypass permission or Run-state checks.

