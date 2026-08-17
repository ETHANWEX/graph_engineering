# ADR-023: Codex-generated Verifier trust boundary

- Status: Accepted
- Date: 2026-08-17

## Decision

Discovery first tests whether the HTTP declaration can express the requested verifier. Only an
insufficient declaration invokes Codex in non-interactive JSONL mode with an output schema and
workspace-write limited to an isolated generation directory. Prompts include secret reference
names but never secret values. The structured response must contain Manifest, implementation,
fixtures, and tests and pass independent validation, policy scan, tests, and dry-run. Raw JSONL and
stderr are redacted Artifacts. Generation never freezes or executes a Verifier.

## Consequences

Codex output is untrusted input until the complete lifecycle and Human confirmation succeed.
