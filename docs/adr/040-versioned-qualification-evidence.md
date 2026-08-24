# ADR-040: Versioned, non-authoritative qualification evidence

- Status: Accepted for Phase 6E implementation
- Date: 2026-08-25

## Context

Release claims span deterministic policy tests, real local integrations, real external providers,
and operating-system support. Treating unavailable or unauthorized environments as skipped success
would overstate readiness, while storing qualification state in Runtime tables would risk changing
product Runs during a read-only release audit.

## Decision

Phase 6E uses a separately versioned qualification document and claim matrix outside Runtime
SQLite. Each run binds product/package/Plugin/Runtime/IPC/MCP versions, exact Git repository/commit/
dirty identity, host/tool/authentication identity, typed operations, UTC timing, exit/result counts,
Artifact references, cleanup, residual effects, limitations, and recovery guidance.

Evidence classifications are exactly deterministic fixture, real local integration, real external
integration, supported-platform evidence, blocked, and unverified. Results distinguish passed,
failed, blocked, and unverified. Model validation forbids passed results for blocked or unverified
classification and forbids nonzero failed/blocked/unverified counts in a passed operation.

Authentication is recorded only as authenticated, unauthenticated, unavailable, not checked, or not
authorized. Secret-bearing keys and configured raw, URL-encoded, base64, overlapping, and
cross-chunk values are rejected before serialization. Evidence query loads an existing document
without touching Runtime state or rewriting the source file.

## Consequences

Qualification evidence can be audited, hashed, and compared without becoming a scheduler or Run
authority. Deterministic fixtures remain useful regressions but cannot qualify a provider or
platform. Missing authority or environment is a first-class blocked/unverified release conclusion.
Protocol and SQLite migration heads remain unchanged at Schema 1.0 / migration 10.
