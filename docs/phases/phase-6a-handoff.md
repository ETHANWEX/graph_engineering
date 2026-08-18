# Phase 6A Handoff

- Status: Human Review approved on 2026-08-19; local delivery commit authorized.
- Branch: `phase/6-enhancements`.
- Baseline commit: `51fad9e05c4b4d68f25d9c8bd1d269dcb0cd129f`. The commit containing this
  handoff is the single Phase 6A delivery commit; its exact SHA is reported after creation.
- Baseline parent / `origin/main`: `eedc46d1a607c6169cb43eca79ef56bdd137efac`.
- Phase 5 predecessor: `db7dd54`; handoff `4ebeb2da969e3cce9210fc3ed8dc23dbf3986662`;
  both verified ancestors of `origin/main` with exit 0.

## Startup and baseline evidence

`git fetch origin` exited 0. The branch and exact roadmap SHA matched the Human instruction; no remote
Phase 6 branch existed. Initial tracked and nonignored untracked counts were zero. The ignored set
contained 9734 historical `.local`, pytest evidence, virtual-environment, and cache entries and was
preserved. Python 3.12.10 from `.local/venv312` and Codex CLI 0.147.0/ChatGPT login were verified.

The startup full baseline collected 156 tests: 152 passed and four opt-in real-Codex tests skipped in
21.77s. The first sandboxed basetemp attempt hit the known Windows ACL `PermissionError` without an
assertion failure; the host-boundary rerun exited 0. Baseline mypy strict, Ruff lint/format, 30-schema
export/drift, valid/invalid Graph and Verifier CLI, and migration 1–6 repeatability all exited 0.

## Decisions and compatibility

- ADR-029: one project-owned foreground Runtime Service, authoritative persisted state, Windows
  lifecycle/endpoint ownership and controlled cleanup.
- ADR-030: IPC 1.0 authenticated loopback framing, identity, limits, typed errors, reconnect,
  persisted mutation replay, uncertain-effect stop, and secret-safe errors.
- ADR-031: one Human Gateway for CLI/MCP/Plugin, confirmation binding/expiry, independent version
  compatibility, repository Plugin boundary, and deterministic versus real E2E evidence.

Package/`ge` is 0.7.0; Runtime API, IPC, and MCP tools are independently 1.0; Plugin is 0.1.0.
Incompatible IPC/Runtime major versions fail closed. The existing 30 Core Schema 1.0 files and model
wire formats did not change. New IPC/MCP wire formats remain outside Core and have committed strict
fixtures. SQLite migration 7 adds pending-confirmation actor/project/protocol/expiry binding and the
IPC mutation replay ledger. Compatibility properties remain 2/3/4/5/6; `service_migration_version`
is the actual head at 7. Historical databases migrate monotonically and remain readable.

## Implemented scope

- `.ge/service/endpoint.json` is atomically published with loopback address, PID, resolved project
  root/workspace hash, random capability, and versions. A live owner blocks duplicate startup; stale
  metadata is replaced only during project-scoped startup. Shutdown is authenticated and cleanup
  removes only the current PID's descriptor. No daemon, OS service, or startup entry is created.
- IPC uses a one-MiB newline-delimited UTF-8 JSON frame, bounded strings, request/idempotency/project/
  workspace identity, a five-second client timeout, and at most two connection attempts. Auth uses
  constant-time comparison. Validation and internal errors are generic and never echo capabilities.
- `start`, `message`, and `confirm` mutations claim a durable fingerprint before work and persist the
  completed response. Same-key/same-request replay returns that response; collision or an executing
  record fails closed. `health`, `status`, and `report` are absent from the replay ledger.
- Human Gateway persists `HumanMessage` before compilation, reuses the fail-closed Intent Compiler,
  binds confirmations to actor/project/protocol/expiry, and invokes Runtime only through typed
  `ControlIntent`. Query snapshots use a read-only facade so they do not initialize Runtime or flush
  outbox. Status/report open read-only connections. Pause/interrupt retain Runtime's durable barrier.
- `ge service start|status|stop` and `ge mcp-server` were added. MCP implements JSON-RPC initialize,
  ping, list, and call over stdio and exposes exactly `start/message/confirm/status/report`. Its
  bounded schemas reject missing targets, unknown fields, oversized text, shell fields, and invalid
  shapes before IPC. MCP never opens SQLite or worktrees.
- `plugins/graph-engineering` contains `.codex-plugin/plugin.json`, `.mcp.json`, the Graph Engineering
  Skill, and README. It calls `ge mcp-server`, declares compatibility and safe workflow, and contains
  no authoritative Run state, endpoint capability, SQLite, worktree, or external handle.

## Final verification evidence

- Phase 6A focused, host boundary: 15 collected / 15 passed in 4.51s, exit 0.
- Full Phase 0–6A regression, host boundary: 171 collected / 167 passed / 4 skipped in 26.50s,
  exit 0. Skips are the existing opt-in real-Codex tests.
- mypy strict: no issues in 80 source files, exit 0.
- Ruff lint: all checks passed; Ruff format: 120 files formatted/check clean, exit 0.
- Schema export: 30; SHA-256 drift comparison: all identical, exit 0.
- Graph valid exit 0; invalid exit 2 with expected field errors.
- Verifier Manifest valid exit 0; invalid wildcard-host fixture exit 2.
- Migration 7 double-application: versions 1–7 exactly once; compatibility head 6/service head 7.
- `ge service --help` exposes start/status/stop; `ge mcp-server --help` exits 0.
- `plugin-creator/scripts/validate_plugin.py plugins/graph-engineering`: passed, exit 0.
- Isolated Windows service subprocess E2E: endpoint/health, persistent Conversation and Run status,
  controlled stop/cleanup, restart, and recovery passed.
- Isolated MCP stdio → actual Runtime Service E2E: initialize, five-tool list, and `start` routing
  passed. This is deterministic local evidence and is not represented as a real Codex Plugin load.

One post-format sandbox run again encountered the known Windows basetemp ACL failure during fixture
setup (no assertion failure); an independent host-boundary rerun of the focused tests passed and is
the recorded evidence.

## Security and invariant review

Runtime SQLite remains the sole authority. Natural language enters only as `HumanMessage`; Runtime
receives only typed control. Read-only operations do not change authoritative Run execution state.
Replay, confirmation, identity, version, and ambiguity paths fail closed. Capability values do not
enter replay rows, responses, errors, events, Artifacts, or reports. Existing barrier guards remain
immediately before side effects. No arbitrary Python, shell, or expression evaluation was added.
Accept still never merges, and no external provider write occurred.

## Explicit non-scope and unverified items

Phase 6B and later work, Claude Code Adapter, parallel graphs, container Verifiers, OpenTelemetry,
UI, distributed workers, OS services/startup, Plugin publication, and automatic merge were not
implemented. The Plugin was not installed and no personal marketplace/config was modified.

A real Codex Plugin-load + MCP E2E is unverified because the Human explicitly withheld Plugin
installation/personal-config authority. No fixture is substituted for it. Cross-platform service/IPC
behavior is also unverified; process/endpoint evidence is Windows only. The service is intentionally
foreground and project-local rather than a background scheduler or system daemon.

## Changed areas

- Scope/status/docs: README, Phase 6A scope/handoff, ADR-029–031, CURRENT, Phase 6B startup prompt.
- Package/storage/control/CLI: pyproject 0.7.0, migration 7, confirmation binding, service package,
  MCP adapter, and service/MCP CLI commands.
- Plugin: repository package under `plugins/graph-engineering`.
- Tests/fixtures: Phase 6A service/IPC/MCP/Plugin tests and versioned IPC/MCP fixtures.

## Next step

Human approved creation of the single local Phase 6A delivery commit on 2026-08-19. Push remains
unauthorized. Phase 6B has not started; its ready-to-use startup prompt is
`docs/prompts/phase-6b-start.md` and requires the exact delivered SHA and a clean branch before any
Phase 6B implementation.
