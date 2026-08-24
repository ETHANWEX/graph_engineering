# Phase 6F: Observability

- Status: Active local implementation; all results remain uncommitted pending Human Review
- Branch: `phase/6-enhancements`
- Baseline / Phase 6E delivery: `e1aa9c61f568b7dda6c77248bc87a000f539a0ca`
- Phase 6E parent / Phase 6D delivery: `651352c056c5402c6a4a4057946822948a23ea66`
- `origin/main`: `eedc46d1a607c6169cb43eca79ef56bdd137efac`
- Authority: `docs/phases/phase-6.md`, ADR-042 onward, and this scope

## Objective

Add a secret-safe, bounded, optional OpenTelemetry provider boundary correlated with existing
persisted identities. Telemetry observes Runtime, IPC, MCP, Agent, Verifier, Review, GitHub,
delivery/report, Human control, recovery and cleanup without becoming a routing, recovery, budget,
barrier or terminal-state authority.

## Contract and compatibility

The versioned contract is `docs/contracts/observability-1.0.md`; compatibility analysis is
`docs/compatibility/phase-6f-observability.md`. Instrumentation uses a provider-neutral internal
protocol with deterministic in-memory evidence. No SDK/exporter package is required by default.
The disabled provider is a no-op. Optional SDK/exporter integration must fail safely and may never
change product behavior.

Package remains 0.8.0, Plugin 0.1.0, Runtime API/IPC/MCP 1.0, SQLite migration head 10, and public
Schema count 36. No public Core protocol or persisted Runtime format changes in this phase.

## Acceptance

- Stable span/metric names, persisted identity correlation, parent/link rules, deterministic
  sampling, metric-label cardinality bounds, attribute allowlists and streaming secret rejection.
- Runtime/parallel, IPC/MCP, Agent, Verifier, Review/review-fix, GitHub, Final Report, Human control,
  recovery, cancel and cleanup instrumentation.
- Bounded queue/batch/flush/shutdown with unavailable, slow, partial, exception and overflow
  isolation; disabled behavior remains equivalent.
- Restart correlation uses persisted identities and never collector state. Late telemetry cannot
  mutate a terminal Run or repeat an effect.
- Read-only status/query/report remain Runtime-state byte/fingerprint preserving when instrumented.
- Dual Python regression, mypy, Ruff, Schema drift, historical migration/read, Phase 6D E2E and
  package build/install smoke pass with exactly the four historical opt-in real-Codex skips.

## Authorization boundary

No real collector/backend traffic, OTLP endpoint, SaaS, cloud resource, external GitHub write,
Plugin publication, container runtime action, package publication, commit, push, PR, main mutation,
merge, or Phase 6G work is authorized. Real OTLP/collector E2E remains blocked/unverified until the
Human separately approves an exact target, fields, network/auth scope, retention, write effects and
cleanup.
