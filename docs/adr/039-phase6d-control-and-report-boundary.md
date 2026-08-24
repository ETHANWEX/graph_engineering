# ADR-039: Phase 6D typed control and terminal reporting boundary

- Status: Accepted for Phase 6D implementation
- Date: 2026-08-25

## Decision

CLI, MCP and Plugin routes are strict typed mappings to the Human Gateway and Runtime APIs. Every
mutation carries request/idempotency identity; natural language remains an append-only
`HumanMessage` before a typed intent. Status/report are read-only. Unknown fields, shell/source
fields, incompatible versions, ambiguous targets and stale authority fail closed.

Every terminal outcome freezes the compatible ten-file delivery bundle from persisted facts.
Human decisions append a new acceptance/report record, never overwrite evidence, and accept never
merges. Revise creates a new Contract revision and prepared Run lineage requiring confirmation and
a later explicit start.
