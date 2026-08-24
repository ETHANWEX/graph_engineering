# Phase 6E Handoff: Integration Qualification

- Date: 2026-08-25
- Status: implementation and authorized local qualification complete; uncommitted pending Human Review
- Branch: `phase/6-enhancements`
- Phase 6D delivery baseline/current committed HEAD: `651352c056c5402c6a4a4057946822948a23ea66`
- Phase 6D parent / Phase 6C delivery: `50f1d0a47d6c210c407af79b5c00e73b43ea984e`
- `origin/phase/6-enhancements`: `651352c056c5402c6a4a4057946822948a23ea66`
- `origin/main`: `eedc46d1a607c6169cb43eca79ef56bdd137efac`
- Local/remote Phase 6 ahead/behind at startup: `0/0`

## Startup gate and baseline

`git fetch origin` exited 0. Branch, local/remote Phase 6 SHA, main SHA, and commit parent matched the
Human gate. Phase 6D is the single child of Phase 6C and its diff contains the frozen handoff,
ADR-037–039, migration-10 storage/coordinator integration, CLI/MCP/Plugin changes, and Phase 6D tests.
No tracked modification was present. Nonignored untracked paths were only the previously attributed
historical `.pytest-tmp-*` evidence directories documented by R0/6C; they were preserved.

The managed sandbox baseline collected 225 tests and ended with 70 passed, 3 skipped, and 152
pytest temporary-root ACL errors, exit 1. No product assertion failed, and the sandbox result was
not mapped to passed. Fresh short host basetemps passed the exact baseline on Python 3.13.14 and
3.12.10: 221 passed / 4 skipped on each, exit 0. The four skips were exactly the historical opt-in
real-Codex cases.

Baseline mypy reported 128 clean source files. Ruff lint/format, 36-schema export/drift, historical
serial and Phase 6B parallel Graph validation, Verifier list/Manifest validation, Python support
window, migration 1–10 repeatability, migration-1 historical read, serial canonical SHA, and static
Plugin/Skill/MCP compatibility all passed. The migration/history/static focused run passed 15 tests.

## Decisions and compatibility

- ADR-040 adds qualification evidence 1.0 outside Runtime SQLite with strict classification,
  secret safety, append-only run identity, and read-only query semantics.
- ADR-041 records the observed non-reproducible sdist failure and the explicit
  `SOURCE_DATE_EPOCH` setuptools fix.
- Product/package remains 0.8.0, Plugin 0.1.0, Runtime API/IPC/MCP 1.0, migration head 10, and
  public Schema count 36. Package metadata now uses SPDX `Apache-2.0`, and the stale source
  `__version__` is aligned to 0.8.0.
- No public Core protocol, JSON Schema, SQLite migration, Runtime state machine, Plugin manifest,
  Service/IPC/MCP protocol, Graph, Verifier, or frozen Phase 6D evidence changed.

## Implemented scope

- `graph_engineering.qualification` provides immutable models for run/product/Git/host/tool/auth
  identity, typed claims, classifications, operation timing/counts, Artifacts, cleanup, residuals,
  limitations, recovery guidance, and aggregate validation.
- Model invariants forbid blocked/unverified evidence from becoming passed and forbid passing claims
  with failed/blocked/unverified counts. Explicit historical skips require a disclosed limitation.
- Secret checks reject token/cookie/password/authorization/credential/secret-bearing keys and
  configured raw, URL-encoded, base64, overlapping, or cross-chunk values before serialization.
- Local tool collection uses argv-only bounded subprocesses, explicit UTF-8 replacement on Windows,
  and enum-only authentication state. It does not persist command output or credentials.
- `QualificationRepository` refuses overwrite, writes one atomic new document, and reads existing
  evidence without Runtime initialization or source-file mutation.
- `ge qualification collect` and `report` expose the explicit writer and read-only reader. Default
  claims honestly mark real Plugin/Codex, GitHub, and container work blocked and Linux/macOS
  unverified.
- `setup.py` contains only the conditional reproducible-sdist hook. Normal build behavior is
  unchanged when `SOURCE_DATE_EPOCH` is absent.

## Packaging, install, upgrade, and local integration

The build environment downloaded fixed build tools from `https://pypi.org/simple`: build 1.3.0,
setuptools 80.9.0, wheel 0.45.1, packaging 26.3, pyproject-hooks 1.2.0, and colorama 0.4.6.
Clean wheel installs resolved the declared dependencies to Pydantic 2.13.4/core 2.46.4, PyYAML
6.0.3, Typer 0.27.1, annotated-types 0.8.0, annotated-doc 0.0.5, typing-extensions 4.16.0,
typing-inspection 0.4.4, shellingham 1.5.4, Rich 15.0.0, markdown-it-py 4.2.0, mdurl 0.1.2,
Pygments 2.21.0, and colorama 0.4.6. No global Python or PATH was changed.

The first two wheel hashes matched, while the first two sdist hashes differed. Extraction proved
all file bytes identical and only generated tar/gzip timestamps differed. After ADR-041, the final
snapshot was built twice with identical results:

- wheel: `3b1baf9f0dc1d5e8d3e85082c5d4e04265b5ad2c5830203bc9d984a207a1779a`
- sdist: `383673ba52daa88ad39b02f874c206d05f01d2372422135f2a70aaac7df59eec`

Clean Python 3.12/3.13 installs both reported source/distribution version 0.8.0. Each passed `ge
--help`, 36-schema export, serial/parallel Graph validation, Verifier list/validate, migration-10
double application, foreground Service health/IPC stop with endpoint/PID cleanup, and MCP
initialize. The first help smoke was invalidated by a truncated Rich pipe; the next cleanup check
used a stale process object. New directories and factual endpoint/PID checks produced the recorded
exit-0 result.

An exact Phase 6D delivery archive produced wheel hash
`b92ab0f2958eb3e949c56026164a5e000e4f8c1b112190105defc00c5bff6c0f`. Installing it, creating a
migration-10 project database/evidence file, force-reinstalling the current build, uninstalling,
and reinstalling preserved both project files byte-for-byte. Both development builds report 0.8.0;
Git/artifact identity distinguishes them, and a future publication must choose a new version.

## Plugin/MCP/Codex, GitHub, container, and platform evidence

- Static Plugin manifest/Skill/MCP compatibility and direct installed MCP handshake passed as
  deterministic/real-local evidence. This is not a real Codex Plugin-load result.
- Codex CLI 0.147.0 is installed and authenticated through ChatGPT. Isolated CODEX_HOME/plugin
  installation and disposable-repository autonomous execution were not authorized, so real Plugin
  and Codex E2E are blocked, not passed.
- GitHub CLI 2.97.0 is installed but unauthenticated. No exact repository/write/cleanup scope was
  authorized. Deterministic Phase 5 provider tests passed; real GitHub remains blocked.
- Docker and Podman are absent. No runtime install, service change, image pull, or container action
  was authorized. Deterministic Phase 6C tests passed; real isolation remains blocked.
- Windows has real-local package/Service/IPC/MCP plus host fixture evidence for worktree,
  subprocess, parallel, barrier, cancellation, and recovery. The whole platform remains partially
  supported/unverified because real Plugin/Codex/container boundaries are blocked.
- Linux and macOS have no approved runner and remain unverified. Windows evidence is not reused.

## Failure/recovery and release-readiness evidence

`docs/qualification/phase-6e-release-readiness-v1.md` is the claim/evidence/limitation matrix.
Identity v1 retains the Windows locale decode failure; v2 retains the wrong Codex auth-stream
limitation; v3 is the corrected current identity. Earlier files were not overwritten. The report
also preserves stale development-venv metadata, first sdist drift, and smoke orchestration failures.

Focused Phase 6E + Phase 6D deterministic + Plugin/MCP/IPC + parallel/container regression passed
73 tests in 25.14s. Final full host regression collected 235 tests:

- Python 3.13.14: 231 passed / 4 skipped in 48.09s, exit 0.
- Python 3.12.10: 231 passed / 4 skipped in 48.74s, exit 0.
- Phase 6E qualification tests: 10 passed within focused/full evidence.
- mypy: 132 source files clean.
- Ruff root lint: passed; format: 133 files clean.
- Schema export: 36, zero drift.
- Historical/parallel Graph and Verifier list/validate: passed.

No skip, xfail, renamed real-Codex case, or weakened assertion was added.

## Cleanup, residuals, and external writes

All 13 validated system-temp roots matching this run's `ge-phase6e-*20260825*` owner pattern were
removed after hashes and results were recorded; zero matching residual root remained. All Service
PIDs exited and endpoint descriptors were removed. No project Runtime/evidence was removed during
upgrade/uninstall testing. Historical workspace `.pytest-*` evidence was not touched.

External traffic was limited to the explicitly approved PyPI GET/downloads listed above. Pip may
retain normal package-cache entries outside the disposable venvs; this cache was not deleted because
it may be shared user data. No package/Plugin upload, GitHub login/write, image pull, system service,
personal marketplace/config mutation, remote repository, PR, Checks, container, volume, network,
runner, VM, or paid resource was created. No external write-side effect remains.

## Changed files

- Scope/status/evidence: README, CURRENT, Phase 6E scope/handoff, ADR-040/041, three versioned
  identity JSON files, and release-readiness report.
- Package/CLI: `pyproject.toml`, `setup.py`, package version identity, qualification package, and
  `ge qualification collect|report`.
- Tests: `tests/test_phase6e_qualification.py`.

## Worktree and next gate

All Phase 6E changes are uncommitted and attributed. The only other nonignored untracked paths are
the preserved historical pytest evidence directories present at startup. No commit, push, PR, main
mutation, merge, publication, marketplace action, real provider write, or later-phase work occurred.

Human Review is the next gate. A Phase 6E delivery commit/push requires new explicit authorization.
Phase 6F OpenTelemetry must not start until Phase 6E review, any chosen real-integration limitations,
and delivery disposition are explicitly resolved.
