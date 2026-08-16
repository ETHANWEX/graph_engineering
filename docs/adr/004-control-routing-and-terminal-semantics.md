# ADR-004: Typed control, safe routing, and terminal semantics

- Status: Accepted
- Date: 2026-08-16

## Context

Natural language must not be executable runtime control. Read-only queries must be distinguishable
from mutations. Graph conditions must not run arbitrary source. Results and reports must distinguish
acceptance failure from operational error and preserve incomplete or irreversible outcomes.

## Decision

`HumanMessage` is the only protocol input carrying Human natural-language text. `ControlIntent` is a
discriminated union of query actions and state-changing actions. Query variants cannot carry pause,
interrupt, revise, restart, accept, or reject. Revision and restart actions require typed details.

Graph edges use `RouteCondition`: an allowlisted result field, comparison operator, and scalar or
list value. Expression strings, Python, and shell are not accepted.

`failed` means task or acceptance failure and requires failure details. `error` means an executor,
verifier, or infrastructure exception and requires a classified `Error`. `FinalReport` covers
success, failure, error, interruption, cancellation, and rejection, and includes unverified items
and external effects including irreversible ones.

## Consequences

Phase 0 validates representation only; it does not compile natural language, mutate runtime state,
evaluate routes, execute nodes, or compile reports. Those behaviors remain in later phases.
