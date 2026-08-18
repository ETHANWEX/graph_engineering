# ADR-021: Structured subprocess, capability, and secret boundary

- Status: Accepted
- Date: 2026-08-17

## Decision

Project Verifiers accept an argv entrypoint only and exchange one JSON request/result over
stdin/stdout with `shell=False`. Timeout, combined output, JSON Schema, and exit status are bounded.
Valid `failed` output is an acceptance failure; spawn, timeout, oversize, invalid JSON/schema, or
abnormal exit is `error`.

Manifest capabilities default-deny network, use exact hosts, constrain filesystem access to
declared roots, identify secrets only by reference, and disclose external side effects. Runtime
resolves only declared references at execution. Raw, URL-encoded, and base64 secret forms are
redacted using longest-match streaming-safe replacement before persistence or exception creation.

## Consequences

The first release does not claim generated subprocess code is fully isolated; Human sees the
permission summary and container isolation remains later work.
