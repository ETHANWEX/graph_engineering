# Phase 6F Handoff: Observability

- Date: 2026-08-25
- Status: authorized local implementation and verification complete; uncommitted pending Human Review
- Branch: `phase/6-enhancements`
- Phase 6E delivery baseline/current committed HEAD: `e1aa9c61f568b7dda6c77248bc87a000f539a0ca`
- Phase 6E parent / Phase 6D delivery: `651352c056c5402c6a4a4057946822948a23ea66`
- `origin/phase/6-enhancements`: `e1aa9c61f568b7dda6c77248bc87a000f539a0ca`
- `origin/main`: `eedc46d1a607c6169cb43eca79ef56bdd137efac`
- Local/remote Phase 6 ahead/behind at startup: `0/0`

## Startup gate and baseline

`git fetch origin` exited 0. The required branch, local and remote Phase 6 SHA, Phase 6E parent,
and `origin/main` matched the Human gate. Tracked and nonignored untracked state was clean. Existing
ignored pytest caches/evidence were preserved. Phase 6E's pre-delivery handoff wording remains an
unaltered historical snapshot; this handoff records that Phase 6E was delivered and pushed.

The managed-sandbox baseline collected 235 tests and ended with 76 passed, 3 skipped and 156 setup
errors, all caused by the historical pytest temporary-root `WinError 5` ACL boundary. It was not
classified as passed. Fresh short host basetemps passed the exact baseline on Python 3.13.14 and
3.12.10: 231 passed / 4 skipped on each. The four skips were exactly the historical opt-in real
Codex cases. Baseline mypy, Ruff, 36-schema drift, serial/parallel Graph validation and Verifier
list/Manifest validation passed.

## Decision, contract and authority

ADR-042 and `docs/contracts/observability-1.0.md` define a dependency-free, OpenTelemetry-compatible
provider boundary. Telemetry is advisory and lossy. Runtime SQLite, frozen inputs, checkpoints,
provider handles and content-addressed evidence remain authoritative; no exporter, SDK, collector,
backend, span or metric may route work, recover work, decide a terminal state or prove cleanup.

The disabled default is `NoOpTelemetryProvider`. `TelemetryProvider` supplies deterministic
sampling and trace identity, context-local parentage, explicit links, bounded records and isolated
export. `InMemoryExporter` is deterministic local test evidence, not a collector substitute.
Optional adapters have typed missing-dependency/version behavior and a fail-safe disabled factory.

## Spans, metrics and identity

Stable spans cover Runtime Run/node/parallel/recovery/cleanup, Executor invocation, Verifier,
Review/review-fix, Service/IPC/MCP, GitHub, Final Report and Human decisions. Synchronous operations
use parent/child causality; thread/parallel and restart recovery use explicit persisted-identity
links. Deterministic trace identity correlates restart without relying on collector data.

Stable metrics cover operation duration/result/retry, budget usage, queue size, active operations,
dropped records and exporter failure/duration. Metric labels use a finite allowlist and never carry
persisted IDs. Span attributes may carry only explicit opaque repository/project, Run, node,
attempt, branch, Session, verifier/review, external-effect, provider-handle, report/artifact and
request identities plus bounded operational fields.

Paths, repository URLs, endpoints, usernames, branch names, commands, prompts, messages, logs,
exception bodies, file contents and provider responses are rejected. Secret-bearing keys and
configured raw, URL-encoded, base64, overlap and cross-value/cross-chunk secret forms are rejected
before buffering. Exporter exceptions are reduced to bounded local health counters; exception text
is never exported or copied into Runtime evidence.

## Sampling, buffering, flush and failure behavior

Sampling is deterministic by trace identity and configured numerator/denominator. Queue capacity,
batch size, export/flush/shutdown calls and attribute lengths are bounded. Overflow drops newest
records and increments local health. Slow, unavailable, partial and throwing exporters are isolated
behind daemon timeout workers. Telemetry is intentionally at-least-once: timeout can make exporter
acknowledgement uncertain, so duplicates and out-of-order delivery are permitted; record sequence,
trace/span identity and timestamps support backend deduplication but are never business authority.

Disabled telemetry leaves product behavior unchanged. Export failure does not become verifier
failure, consume business budget, weaken a durable barrier, alter terminal state or repeat a Run,
Session, subprocess, container, GitHub or report effect. Late records after a terminal Run are
marked `ge.late`; telemetry cleanup failure is observational only.

## Compatibility and persistence

Product/package remains 0.8.0, Plugin 0.1.0, Python `>=3.12,<3.14`, Runtime API/IPC/MCP 1.0,
migration head 10 and public Schema count 36. There is no new dependency, public protocol, JSON
Schema, SQLite table/view/column or migration. Migration 1–10 and historical reads remain covered
by the full and Phase 6D/6E regression. Default constructor behavior remains no-op compatible.
Read-only status/query/report instrumentation preserves Runtime fingerprints/outbox state.

## Verification evidence

Tests were written before their integration points. The first focused implementation run produced
4 passed / 3 failed, with the failures precisely identifying missing Runtime and Human Gateway
provider boundaries. The completed focused Phase 6F suite has 13 tests, including a concurrent
equal-identity span uniqueness lock. Affected Phase 2/5/6A–6D regression passed 93 tests. Explicit
Phase 6D autonomous-delivery plus Phase 6E qualification regression passed 20 tests on a fresh host
basetemp; the sandbox attempt retained 7 passes and 13 ACL setup errors, with no product assertion
failure.

Final full host regression collected 248 tests:

- Python 3.13.14: 244 passed / 4 skipped in 50.38s, exit 0.
- Python 3.12.10: 244 passed / 4 skipped in 50.78s, exit 0.
- mypy: 136 source files clean.
- Ruff: lint passed; 136 files format-clean.
- Schema export: 36, zero drift.
- Serial/parallel Graph and Verifier list/validate: passed.
- `git diff --check`: passed (only normal Windows LF-to-CRLF notices).

No skip, xfail, renamed historical case or weakened assertion was added.

## Packaging and external classification

No dependency or package version changed. The supported local venvs initially lacked `build` and
`setuptools`. After separate Human approval, the exact Phase 6E-qualified toolchain was installed
in a disposable host venv from the local pip cache (`build` 1.3.0, setuptools 80.9.0, wheel 0.45.1,
packaging 26.3, pyproject-hooks 1.2.0 and colorama 0.4.6; the command retained the approved PyPI
index as source). The current uncommitted snapshot then built successfully without isolation:

- wheel SHA-256: `3db8d070a61ae265856e1bd90ac0b5fd69d21ca86f3c96dfa808c3efecd698c0`
- sdist SHA-256: `9957876e15b27163c53c20e2e3f8b83107c8bbf3cece119d0ab0e0a6b5bcae88`

The wheel contains all three `graph_engineering.observability` modules. Fresh Python 3.12 and 3.13
venvs installed it offline with `--no-index --no-deps`; both reported distribution 0.8.0,
observability contract 1.0 and a working disabled provider. The first import assertion incorrectly
assumed `CONTRACT_VERSION` was a package-level public export; the corrected smoke used the declared
`ObservabilityConfig.contract_version` boundary and passed. No API was changed to fit the invalid
assertion. Phase 6E's frozen package evidence was not rewritten.

Real OTLP/collector/SaaS E2E is **blocked by authorization**. No endpoint, credentials, retention
policy or cleanup plan was approved, and no telemetry left the process. Linux/macOS remain
unverified; no runner/VM was created. Existing real Plugin, GitHub and container limitations remain
as recorded by the frozen Phase 6E release-readiness report.

## Cleanup, residuals and external writes

No Runtime Service, container runtime, image, collector, cloud resource, GitHub operation, Plugin
installation or external telemetry connection was started. The separately approved build-tool pip
operation used cached wheels while retaining `https://pypi.org/simple` as its configured index; it
wrote only the disposable host smoke root and normal shared pip cache state. No product dependency
or package was published. The exact package-smoke root was removed after results and hashes were
recorded. Fresh pytest host basetemps are local verification residue; historical workspace
`.pytest-*` evidence was not deleted. There was no commit, push, PR, main mutation or merge.

## Worktree and next gate

All Phase 6F source, tests and documentation remain uncommitted and attributed on
`phase/6-enhancements`; committed HEAD and both tracked remote refs remain at the authorized SHAs.
Human Review is the next gate. A delivery commit/push or any resolution of blocked package/collector
evidence requires new explicit authorization. Phase 6G must not begin before Phase 6F review and
delivery disposition are complete.
