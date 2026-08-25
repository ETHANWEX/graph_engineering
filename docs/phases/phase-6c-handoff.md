# Phase 6C Handoff

- Status: Human-reviewed and approved; one Phase 6C delivery commit and push explicitly authorized
- Branch: `phase/6-enhancements`
- Pre-delivery baseline: `b7da3c4c7712db0f8fb01f14cd2d141008c5186a`
- Delivery identity: the single child of the baseline containing this handoff; verify its SHA after
  creation rather than embedding a self-determining SHA in the commit content
- Baseline predecessor: `f9ee0b330a5a22a99d48cb787356445d044fb2ae`
- Remote Phase 6 ref: `origin/phase/6-enhancements` is the same baseline SHA
- `origin/main`: `eedc46d1a607c6169cb43eca79ef56bdd137efac`

## Startup and baseline evidence

`git fetch origin` exited 0. The branch, local HEAD, remote Phase 6 ref, R0 parent, and handoff
identity matched the authorized start gate. Tracked changes were empty. Nonignored untracked paths
were only the previously attributed historical `.pytest-tmp-*` evidence directories preserved by
R0; ignored environments and caches were also preserved.

The managed sandbox baseline collected 190 tests but produced `62 passed / 3 skipped / 125 errors`
in 12.46s, exit 1. Every error was `tmp_path` setup/cleanup `PermissionError`; no product assertion
failed. Fresh host basetemps then passed the same baseline: Python 3.13.14 had 186 passed / 4 skipped
in 34.23s, and Python 3.12.10 had 186 passed / 4 skipped in 33.63s, both exit 0.

## Decisions and compatibility

- ADR-034 freezes the provider-neutral adapter boundary and digest/platform/provenance identity.
- ADR-035 freezes finite resources, mount/network fail closure, and reference-only secret handling.
- ADR-036 freezes durable start/handle recovery, bounded stop, stable owner cleanup, and residual
  disclosure.
- SQLite migration 9 adds `container_executions`. Migrations 1–9 apply once and historical data is
  upgraded monotonically. Compatibility properties remain capped at their phase heads:
  `parallel_migration_version=8` and `service_migration_version=7`.
- The internal Verifier SDK adds `project/container`; the public 1.0 Schema set remains 36 files
  with zero drift. Existing Graph, Result, Service, IPC 1.0, MCP, and Plugin wire contracts do not
  change. Historical serial Graph canonical content is untouched.

## Implemented scope

- Exact Registry integration and unified `VerifierResult` routing distinguish acceptance failure,
  infrastructure error, cancellation, cleanup failure, and residual/unknown effects.
- Immutable image identity rejects tags and binds exact registry, repository, digest, platform,
  provenance, entrypoint, config, and fingerprint allowlists before any side effect.
- Docker-compatible adapter preflight is typed and never installs a runtime or changes a daemon.
  The Docker CLI implementation applies CPU, memory, PID, timeout coordination, read-only root,
  mount, platform, and `network=none` flags. stdout/stderr are concurrently read with per-stream
  bounds instead of unbounded post-process capture.
- Mount sources use explicit authorized roots and are re-resolved immediately before start.
  Windows and POSIX absolute/traversal forms, symlink/junction/reparse escape, Docker sockets,
  credentials/home/system targets, and writable frozen/evidence mounts fail closed.
- Networking defaults to none. Exact protocol/host/port policy requires an adapter that can reliably
  enforce DNS, redirect, proxy, and custom-host boundaries. The default Docker CLI adapter refuses
  enabled networking because it cannot make that claim.
- Secrets remain reference names in frozen data. Values enter only an ephemeral adapter request or
  owner-tracked mode-0600 environment file, are never placed in image/entrypoint/command identity,
  and are removed during owned cleanup. Raw, URL-encoded, base64, overlapping, and cross-chunk forms
  are redacted before persistence.
- Start intent precedes the adapter call; handle checkpoint immediately follows it. Recovery polls a
  known handle, reuses a completed result, and never repeats a no-handle uncertain start. Identities
  include Phase 6B qualified branch/node keys. Durable Run barriers are checked before start.
- Bounded stop/settlement and idempotent label-verified cleanup act only on the stable attempt owner.
  Cleanup/residual evidence enters events, content-addressed Artifacts, SQLite, and
  `external-effects.json`; late provider data is not an alternative authority for Run state.

## Test and fixture evidence

The final Phase 6C focused command covered the container suite, Registry compatibility, migration 7
view compatibility, and migration 8 view compatibility: 32 passed in 5.13s, exit 0. Versioned valid
and invalid container Manifest fixtures distinguish a pinned digest from a mutable tag. Deterministic
fake adapters/processes cover:

- image/provenance/allowlist and frozen config drift;
- POSIX/Windows traversal, symlink and reparse/junction mounts, read/write modes, socket/system paths;
- default network none and unenforceable exact policy;
- CPU, memory, PID, wall-clock, per-stream output, Artifact, and concurrency limits;
- raw/URL/base64/overlap/cross-chunk secret redaction;
- verifier failure versus infrastructure/cleanup/residual results;
- handle restart, completed-result reuse, uncertain start, barrier, cancel, cleanup, and report data;
- qualified active parallel branch container identity and deterministic settlement;
- migration 1–9 repeatability with earlier compatibility views.

## Final verification

- Python 3.13.14 host full regression: 215 collected / 211 passed / 4 skipped in 39.41s, exit 0.
- Python 3.12.10 host full regression: 215 collected / 211 passed / 4 skipped in 38.36s, exit 0.
- mypy strict: no issues in 126 source files, exit 0.
- Ruff root lint: all checks passed; format: 126 files clean, exit 0.
- Schema export: 36 files, committed drift zero, exit 0; migration head 9.
- Historical valid Graph and Phase 6B parallel Graph validation exited 0.
- `ge verifier list` exited 0 and includes `project/container`; historical Verifier Manifest
  validation exited 0.

The four skipped instances are unchanged opt-in real-Codex acceptance tests. Phase 6C adds no skip.

## Changed areas

- Scope/status/decisions: README, CURRENT, Phase 6 roadmap/status, Phase 6C scope/handoff, and
  ADR-034–036.
- Verifier boundary: container types/provider/Docker adapter, Registry exports, lifecycle permission
  summary, immutable fingerprint, policy validation, redaction, cancellation, and cleanup.
- Persistence/report: migration 9 and delivery external-effect facts.
- Tests/fixtures: Phase 6C container suite and valid/invalid Manifest fixtures; migration/Registry
  expectations updated only for the additive provider and storage head.

## Security invariants and unverified evidence

SQLite remains authoritative. Frozen inputs are checked before effects; barriers forbid later
starts; secrets are absent from persisted identity and evidence; cleanup verifies stable ownership;
unknown effects never become success; verifier failures never masquerade as infrastructure errors;
query/status/report remain read-only; accept still never merges.

Docker and Podman are unavailable on this host. Real container isolation, cgroup enforcement,
namespace/mount/network behavior, live daemon recovery, and live container cleanup therefore remain
explicitly **unverified**. No runtime was installed, no service was started, and no image was pulled.
Fixture evidence is not represented as real isolation evidence. No container, volume, namespace,
provider write, or external effect remains; host-managed pytest basetemp roots may remain under the
system temporary directory and contain only deterministic test data.

## Delivery authorization and next step

The Human reviewed this result and explicitly authorized one Phase 6C delivery commit and push to
`phase/6-enhancements`. This authorization does not include a PR, main mutation/merge, Plugin
installation/publication, real provider write, or Phase 6D implementation.

Next phase is Phase 6D Autonomous Delivery Closure. Its startup prompt is
`docs/prompts/phase-6d-start.md`; supplying the prompt does not itself start or authorize Phase 6D.
