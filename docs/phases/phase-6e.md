# Phase 6E: Integration Qualification

- Status: Implementation and authorized local qualification complete; uncommitted pending Human Review
- Branch: `phase/6-enhancements`
- Baseline / Phase 6D delivery: `651352c056c5402c6a4a4057946822948a23ea66`
- Phase 6D parent / Phase 6C delivery: `50f1d0a47d6c210c407af79b5c00e73b43ea984e`
- `origin/main`: `eedc46d1a607c6169cb43eca79ef56bdd137efac`
- Authority: `docs/phases/phase-6.md`, ADR-040 onward, and this scope

## Objective

Qualify the already implemented Graph Engineering boundaries with versioned, secret-safe evidence.
Every release claim must map to an exact operation, environment identity, evidence classification,
result, limitation, cleanup outcome, residual effect, and supported/unsupported/unverified
conclusion. Deterministic fixtures never substitute for real local, external, or platform evidence.

## In scope

- A standalone qualification evidence model and release-readiness claim matrix that never becomes
  authoritative Runtime state.
- Read-only evidence query/report behavior and an explicit local collection command.
- Reproducible wheel/sdist build, metadata, entry-point, isolated Python 3.12/3.13 install,
  reinstall/upgrade, migration/history, CLI/Service/IPC/MCP smoke, and package hash evidence.
- Static Plugin compatibility plus explicitly authorized local Windows integration evidence.
- Explicit blocked/unverified records for unavailable or unauthorized real Codex Plugin load,
  GitHub writes, container execution, Linux, and macOS.
- Recovery/failure classification and release-readiness documentation.

## Evidence and safety contract

Qualification evidence is append-only by run identity and is stored separately from Runtime Run,
Session, Contract, Verifier, acceptance-lock, and delivery evidence. Querying an evidence file is
byte-preserving and does not initialize or migrate Runtime SQLite. Evidence records only
authentication state, never credentials. Missing environment or authority maps to `blocked` or
`unverified`, never `passed`.

The default local collection path is read-only except for its explicit evidence output. Packaging
qualification uses disposable local directories, local build artifacts, and isolated virtual
environments. It never changes global Python, PATH, system services, personal Codex configuration,
marketplaces, registries, GitHub, or container daemons.

## Acceptance

- Model invariants prevent blocked, unverified, unavailable, unauthorized, or undisclosed skipped
  evidence from becoming passed evidence; explicit opt-in skips require a separate limitation.
- Evidence records exact product/protocol/Git/environment/tool identities, command/operation,
  timing/counts, Artifacts, cleanup, residual effects, limitations, and recovery guidance.
- Secret raw, URL-encoded, base64, overlap, and cross-chunk forms do not enter evidence.
- Python 3.12 and 3.13 isolated package install/upgrade and local Windows product smoke pass.
- Release-readiness claims distinguish implementation, fixture, real local, real external,
  supported-platform, blocked, failed, and unverified conclusions.
- Full Phase 0–6D regression, mypy, Ruff, Schema drift, migration, Graph, Verifier, and deterministic
  Phase 6D E2E remain green with exactly the four historical opt-in real-Codex skips.

## Explicit non-scope and authorization boundary

Phase 6F OpenTelemetry, Phase 6G UI, Claude Code, distributed workers, publishing, auto-merge,
branch-protection bypass, and system service work are prohibited. Real Plugin installation/load,
real Codex autonomous execution, GitHub writes, Docker/Podman execution or installation, image
pulls, Linux/macOS runners, cloud/CI/VM resources, and paid resources require separate precise Human
authorization. Without it they remain blocked/unverified. No Phase 6E commit, push, PR, main
mutation, merge, package/Plugin publication, or later phase is authorized.
