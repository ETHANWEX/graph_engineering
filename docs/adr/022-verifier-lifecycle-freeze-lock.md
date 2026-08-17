# ADR-022: Verifier lifecycle, append-only freeze, and acceptance lock

- Status: Accepted
- Date: 2026-08-17

## Decision

Verifier revisions progress through draft, validated, tested, dry-run, and frozen. Freeze requires
explicit Human confirmation and records canonical Manifest, source, tests, and optional fixtures
SHA-256 values. Frozen revisions cannot be updated. Runtime verifies all hashes before trigger or
process spawn. Revision N+1 may only bind to a later Contract revision; an existing Contract
revision cannot silently acquire a new Verifier revision.

## Consequences

Acceptance evidence is append-only and drift fails before external side effects.
