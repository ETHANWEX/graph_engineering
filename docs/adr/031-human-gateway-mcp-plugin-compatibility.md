# ADR-031: One Human Gateway for MCP and the Codex Plugin

- Status: Accepted
- Date: 2026-08-18

## Decision

CLI, MCP, and Plugin use one Human Gateway. `message` first persists `HumanMessage`, then uses the
existing fail-closed Intent Compiler and typed Runtime control. `confirm` binds the same actor,
project, conversation, pending action, protocol major, and finite expiry; stale, resolved,
unauthorized, targetless, or incompatible confirmation fails closed. `status` and `report` use
read-only Runtime/report APIs. The MCP stdio adapter exposes only `start`, `message`, `confirm`,
`status`, and `report`, validates bounded JSON schemas, and never opens SQLite or worktrees itself.

The repository Plugin contains `.codex-plugin/plugin.json`, a Graph Engineering Skill, and
`.mcp.json`. It stores no authoritative state or endpoint capability. It invokes the local
`ge mcp-server`, requires compatible `ge`/Runtime/IPC/MCP/host versions, and reports an explicit
compatibility error when unavailable. Codex Session replacement or compaction therefore has no Run
semantics.

Deterministic fixtures and isolated fake-host tests are labeled as such. A real Codex Plugin/MCP
test may be reported only when the repository Plugin is actually loaded by Codex; lack of authority
to install or alter personal configuration is recorded as unverified, never replaced by a fixture.

## Consequences

MCP errors remain protocol errors rather than fabricated business failures. Secrets are rejected
from free-form transport metadata and redacted from all protocol errors and diagnostics. Claude Code
and all later Phase 6 capabilities remain outside this decision.
