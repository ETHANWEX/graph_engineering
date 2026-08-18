# ADR-012: Persistent Human conversation and typed control boundary

- Status: Accepted
- Date: 2026-08-17

## Context

Natural-language control must survive CLI/session restarts without becoming executable Runtime
input. Existing public Schema 1.0 already defines `HumanMessage` and a discriminated query/state
change `ControlIntent`.

## Decision

Every Human utterance is appended as an immutable `HumanMessage` before interpretation. SQLite
migration 4 stores conversations, messages, compiled intents, pending actions, and checkpoints.
Only a schema-validated `QueryControlIntent` or `StateChangeControlIntent` may reach Runtime.
Conversation provider output and confidence are advisory Adapter data, never state-machine input.

## Consequences

Public Schema 1.0 remains unchanged. Runtime never accepts free text. Restart reconstructs the
conversation from durable rows rather than a Codex Session.

