# Phase 6C: Container Verifiers

- Status: Human-reviewed; one delivery commit and push explicitly authorized
- Branch: `phase/6-enhancements`
- Baseline: `b7da3c4c7712db0f8fb01f14cd2d141008c5186a`
- Authority: `docs/phases/phase-6.md`, ADR-034 onward, and this scope

## Objective

Add a provider-neutral container Verifier boundary with immutable image identity, fail-closed
runtime preflight, bounded resources and output, validated mounts, default-deny networking,
reference-only secrets, durable handle recovery, bounded cancellation/cleanup, and accurate
residual-effect reporting.

## In scope

- Docker-compatible adapter protocol and a deterministic fake adapter used only as fixture evidence.
- Digest-pinned image/platform/provenance policy and exact registry/repository/digest allowlists.
- CPU, memory, PID, wall-clock, output, Artifact, and provider concurrency limits.
- Windows/POSIX-aware mount validation under explicitly authorized roots; frozen control and
  evidence inputs are read-only and Docker sockets/system paths are rejected.
- `network=none` by default. Exact host/port/protocol access requires frozen authorization and an
  adapter capable of reliably enforcing it; otherwise execution fails closed.
- Secret resolution at execution time, streaming-safe redaction, ephemeral injection, and cleanup.
- SQLite migration 9 for container execution identity, attempt, owner, handle, digest, fingerprint,
  result, cleanup, and residual state.
- Restart polling without duplicate start, uncertain-start fail closure, durable barriers,
  cancellation, cleanup ownership, and parallel-compatible idempotency identities.

## Acceptance

- Mutable tags, image/config drift, unauthorized mounts/network, and unavailable/incompatible
  runtimes fail before a container side effect.
- Verifier failure, container infrastructure error, cancellation, cleanup failure, and unknown or
  residual effect remain distinct.
- Completed executions are reused; checkpointed handles are inspected; a start intent without a
  handle is never blindly retried.
- Output and Artifact limits are enforced while consuming bounded chunks, and all secret variants
  are redacted before persistence.
- Migration 1–9 is repeatable while Phase 0–6B compatibility views and public Schema remain stable.
- Deterministic focused tests and the complete Phase 0–R0 regression pass on supported Python.

## Evidence boundary

Deterministic fake-adapter evidence validates Graph Engineering policy, persistence, and state
machines. It is not evidence of real container isolation. Real Docker/compatible-runtime E2E may be
recorded only after separate authorization and only when an existing compatible runtime and pinned
local image are available; this phase never installs a runtime, changes a service, or pulls an
external image silently.

## Explicit non-scope

Phase 6D or later work, autonomous delivery closure, real integration qualification, OpenTelemetry,
UI, Claude Code, distributed workers, OS startup services, Plugin installation/publication,
automatic merge, branch-protection bypass, and history rewriting are prohibited.
