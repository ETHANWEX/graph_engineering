# ADR-001: Provider-neutral independent core

- Status: Accepted
- Date: 2026-08-16

## Context

Graph Engineering must retain authoritative contracts, graph state, evidence, and reports across
executor changes and executor-session loss. Embedding provider-specific session formats in the core
would couple persisted runs to a particular Coding CLI.

## Decision

The core is an independent control layer. Phase 0 public models contain no Codex, Claude Code, or
other provider-specific session payload. Future adapters translate provider data at the boundary;
provider session identifiers, if needed, remain adapter metadata rather than protocol structure.

## Consequences

The public schemas are language- and provider-neutral. Adapter capability discovery and actual
executor invocation remain deferred to Phase 2.
