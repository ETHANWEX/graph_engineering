# ADR-003: Explicit protocol versioning and append-only contract revisions

- Status: Accepted
- Date: 2026-08-16

## Context

Later phases must persist and exchange contracts, graphs, results, controls, and reports without
silently accepting incompatible shapes. Frozen contracts and evidence must be hashable and must not
be overwritten when direction changes.

## Decision

Every public Phase 0 protocol includes a required `schema_version` field. Version 1 uses the literal
`"1.0"`. Protocol models reject unknown fields and are immutable after validation. Canonical JSON
uses UTF-8, sorted keys, compact separators, JSON-mode values, and omitted nulls; SHA-256 is computed
over those bytes.

A `TaskContract` has a stable `contract_id` and positive `revision`. Revision 1 has no predecessor.
Later revisions must reference a lower revision with the same contract ID. `RunRelationship`
separately represents `parent_run_id` and `supersedes_run_id`; `RestartFrom` restricts restart roots
to a clean base, accepted commit, or named checkpoint.

## Consequences

Breaking protocol changes require a new schema version and migration ADR. Contract changes append
history rather than modifying old documents. The committed schemas and fixtures detect accidental
wire-format changes.

