# Phase 6A: Runtime Service, Local IPC, MCP, and Codex Plugin

- Status: Active implementation
- Branch: `phase/6-enhancements`
- Baseline: `51fad9e05c4b4d68f25d9c8bd1d269dcb0cd129f`
- Package target: `0.7.0`

## Objective

Provide a persistent local product entry point whose state survives Codex and MCP sessions. The
independent Runtime and its SQLite stores remain authoritative; CLI, MCP, and the repository-owned
Codex Plugin are thin clients of one Human Gateway.

## In scope

- Foreground Runtime Service lifecycle, health/version discovery, controlled shutdown, restart,
  single-project ownership, and Windows-safe endpoint cleanup.
- Versioned authenticated loopback IPC with project/workspace identity, request and idempotency
  identities, typed envelopes and errors, bounded frames, timeout, reconnect, and bounded retry.
- `ge service start|status|stop` and `ge mcp-server`.
- MCP tools `start`, `message`, `confirm`, `status`, and `report`, all routed through the Human
  Gateway. Natural language is represented only as a persisted `HumanMessage`; mutations reach
  Runtime only as typed `ControlIntent`.
- A reviewable repository-owned Codex Plugin containing a valid manifest, Skill, MCP configuration,
  compatibility declarations, and usage documentation.
- SQLite migration 7, deterministic transport fixtures, Windows subprocess tests, and handoff
  evidence.

## Compatibility contract

Package/CLI `0.7.x`, Runtime API `1.0`, IPC `1.0`, MCP tool contract `1.0`, and Plugin `0.1.x` are
declared independently. Major-version disagreement fails closed. Schema 1.0 Core models and the 30
committed public schemas are unchanged. Databases migrate monotonically from versions 1 through 6
to 7 and historical Runs remain readable.

## Security and side-effect contract

The endpoint descriptor is private project-local metadata and contains a random bearer capability;
the service accepts loopback clients only and compares the capability in constant time. Requests
bind the resolved project root and workspace identity. Frame, string, retry, and timeout limits are
finite. Protocol responses, errors, and diagnostics never echo authorization values. Query/status/
report are read-only. Mutation replay returns the persisted prior response. Pause/interrupt barriers
are enforced by the existing Runtime immediately before effects.

## Acceptance

- Start/status/stop, health/version, restart recovery, reconnect, idempotent replay, and cleanup work
  in isolated Windows subprocess tests.
- Missing, ambiguous, expired, unauthorized, incompatible, oversized, or identity-mismatched
  requests fail closed with typed transport errors.
- The five MCP schemas validate and route through the same Gateway; disconnect never stops a Run.
- Read-only operations do not change authoritative execution state.
- Plugin validation passes without installing the Plugin or modifying personal Codex configuration.
- Phase 0-5 regression, mypy strict, Ruff, schema drift, migrations, and CLI fixtures pass.

## Explicit non-scope

Phase 6B or later work, Claude Code, parallel graphs, container Verifiers, OpenTelemetry, UI,
distributed workers, system services/startup entries, Plugin publication/installation, personal
marketplace/config changes, and automatic merge are prohibited.
