# ADR-008: Codex capability, version, and JSONL compatibility

- Status: Accepted
- Date: 2026-08-16

## Context

Codex CLI flags and JSONL events evolve. Documentation describes non-interactive JSONL and resume,
but the installed executable is the runtime authority for a particular machine.

## Decision

Preflight records `codex --version`, login status, and exact help-derived support for exec JSON,
output schema, last-message output, resume, structured review, sandbox, approval policy, and cancel
by process termination. Required capabilities are checked before launch. The Adapter uses argv with
`--json`, `--output-schema`, `--output-last-message`, `--sandbox workspace-write|read-only`, and
`--ask-for-approval never` only when the installed help confirms them. Dangerous bypass is rejected.

JSONL parsing requires only a JSON object and optional string `type`. Known lifecycle/thread/final
events are projected; unknown objects are retained as neutral `unknown` events and raw evidence.
Fixtures are version-labelled. Final structured output is validated independently of event names.

Codex CLI 0.147.0 advertises `--output-schema` for `exec review` but, in a real invocation, writes a
plain-text final message. Until preflight can prove native structured review behavior, the Adapter
implements provider-neutral review as a fresh `codex exec` in read-only sandbox with the Review
Schema. Native review capability is recorded but is not allowed to bypass structured validation.

## Consequences

An unsupported installation fails preflight explicitly instead of starting partially. New unknown
events do not break a Run. Help snapshots and raw output provide compatibility evidence.
