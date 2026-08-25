# ADR-032: Explicit parallel, subgraph, and deterministic join protocol

- Status: Accepted
- Date: 2026-08-19

## Context

Phase 6B must represent parallel work without executable expressions, implicit fan-out, provider
payloads, or completion-order-dependent results. Existing serial Graph 1.0 documents and frozen
hashes must remain valid.

## Decision

Execution Graph adds the node kinds `parallel`, `subgraph`, and `join`. A `subgraph` embeds an
explicit, strongly validated serial `Subgraph`; a `parallel` embeds two or more stable-ID branches,
each containing such a Subgraph and a finite `max_concurrency`; a `join` names exactly one parallel
node. Parallel and join relationships are explicit Graph data and route conditions remain the
existing allowlisted comparisons. Nested parallel/join nodes inside branch Subgraphs are rejected
in Phase 6B.

Branch and aggregate results are provider-neutral immutable models. Branches are always serialized
by branch ID. Aggregate precedence is `error`, `blocked`, `failed`, `cancelled`, then `succeeded`;
only unanimous branch success produces aggregate success. Changed files, Artifacts, completed-node
IDs, failures, and errors are sorted or deduplicated deterministically. Join returns the canonical
persisted aggregate for its named parallel node and never recomputes from worker arrival order.

The Graph Schema 1.0 change is additive for existing documents: all old node kinds and fields retain
their validation and bytes, while new node kinds require new typed fields. New readers accept old
Graph 1.0 data unchanged; old readers fail closed on the new enum values. The exported public
schemas and valid/invalid fixtures record that compatibility boundary.

## Consequences

No Python, shell, template, or expression source is introduced. Provider, IPC, MCP, and Plugin wire
formats remain unchanged. Supporting nested parallelism or alternative join policies requires a
later ADR and is not silently enabled by arbitrary `config` values.
