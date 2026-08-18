---
name: graph-engineering
description: Use a persistent local Graph Engineering Runtime through its five MCP Human Gateway tools.
---

# Graph Engineering

Use this Skill when the Human asks to start, control, inspect, or report a Graph Engineering Run.

## Compatibility and safety

Require Codex CLI 0.147.0 or newer, `graph-engineering`/`ge` 0.7.x, Runtime API 1.x, IPC 1.x, and
MCP tools 1.x. The project
Runtime Service must already be running (`ge service start --project-root <project>` in a managed
foreground process). If it is absent or reports an incompatible major version, stop and explain the
compatibility error. Never edit `.ge` SQLite databases, Runtime endpoint files, worktrees, or
external handles. Never copy the endpoint authorization capability into chat, logs, or prompts.

The Plugin and Codex Session hold no authoritative Run state. Session replacement, compaction, or
MCP reconnect must resume by conversation or Run identity through the tools.

## Workflow

1. Call `start` with stable `project_id` and `actor_id`; retain the returned `conversation_id` only
   as a routing handle.
2. Call `message` for every natural-language Human request. Do not manufacture a `ControlIntent` or
   bypass the Human Gateway.
3. If a pending confirmation is returned, show the exact proposed action. Call `confirm` only after
   a new explicit Human confirmation and pass its `confirmation_id`.
4. Use `status` for current persisted Run state and `report` for the latest immutable delivery
   bundle. These tools are read-only.
5. Treat MCP/IPC/service errors as infrastructure errors, not as Verifier failures, Review verdicts,
   or business outcomes. Missing/ambiguous targets and stale confirmations fail closed.

Pause and interrupt establish durable Runtime barriers. Never start another side effect after the
Runtime reports a barrier. Acceptance never means merge, and no workflow here authorizes automatic
merge or branch-protection bypass.
