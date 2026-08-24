# Phase 6E Release Readiness Report v1

- Evidence schema / qualification version: `1.0` / `1.0`
- Baseline and current committed identity: `651352c056c5402c6a4a4057946822948a23ea66`
- Branch: `phase/6-enhancements`; dirty state: `true` (attributed Phase 6E work)
- Repository: `E:\project\graph_engineering`
- Host: Windows `10.0.26200`, AMD64, Windows path/filesystem semantics, PowerShell orchestration
- Python: 3.13.14 and 3.12.10
- Product/package/Plugin/Runtime/IPC/MCP: `0.8.0` / `0.8.0` / `0.1.0` / `1.0` / `1.0` / `1.0`
- Migration head / public Schema count: 10 / 36
- Identity evidence: `phase-6e-local-identity-v1.json` (locale decode-limited), v2 (Codex auth
  stream-limited), and `phase-6e-local-identity-v3.json` (current identity result). Earlier runs are
  retained and are not overwritten by v3.

## Claim and evidence matrix

| Claim | Required environment | Classification | Exact operation / Artifact | Result | Limitation | Cleanup / residual | Conclusion |
|---|---|---|---|---|---|---|---|
| Phase 0–6D implementation remains compatible | Windows Python 3.12/3.13 host | deterministic fixture | `.venv\Scripts\python.exe -m pytest -q --basetemp <fresh-host-root>` and `.local\venv312\Scripts\python.exe -m pytest -q --basetemp <fresh-host-root>` | baseline: 225 collected, 221 passed, 4 explicit historical real-Codex skips on each interpreter; exit 0 | Fakes/fixtures do not qualify real providers | pytest-owned temporary data only; no external effect | implementation passed; fixture passed |
| wheel is reproducible | fixed source + build tools | real local integration | final snapshot built twice; `sha256:3b1baf9f0dc1d5e8d3e85082c5d4e04265b5ad2c5830203bc9d984a207a1779a` | passed, exit 0 | Local Windows build only | disposable artifact removed after hashing; no residual | supported locally |
| sdist is reproducible | fixed `SOURCE_DATE_EPOCH` + build tools | real local integration | initial hashes differed; ADR-041 fix; final snapshot built twice as `sha256:383673ba52daa88ad39b02f874c206d05f01d2372422135f2a70aaac7df59eec` | failed first, passed after preserved fix | Setuptools hook is qualified on Windows only | disposable artifact removed after hashing; no residual | supported locally |
| package metadata, dependencies and `ge` entry point | clean Python 3.12/3.13 venvs | real local integration | local wheel install; import metadata; `ge --help` | passed on 3.12.10 and 3.13.14, exit 0 | Dependencies were resolved from PyPI for this authorized run | venvs are disposable; no PATH/global Python change | supported locally |
| install smoke covers Schema/Graph/Verifier | clean Python 3.12/3.13 venvs | real local integration | 36-schema export; serial and Phase 6B Graph validate; Verifier list/validate | passed on both interpreters, exit 0 | No provider effect was started | temporary files only | supported locally |
| installed Service/IPC/MCP lifecycle | clean Python 3.12/3.13 Windows venvs | real local integration | foreground `ge service start/status/stop`; endpoint/PID cleanup; MCP `initialize` | passed on both interpreters, exit 0 | MCP was invoked directly, not through a loaded Codex Plugin | endpoint removed, PID exited, no service registration | supported locally |
| Phase 6D 0.8.x state upgrade and reinstall | exact Phase 6D SHA wheel + current wheel | real local integration | Phase 6D wheel `sha256:b92ab0f2958eb3e949c56026164a5e000e4f8c1b112190105defc00c5bff6c0f`; force-reinstall current wheel; uninstall/reinstall | passed, exit 0 | Both uncommitted development builds report 0.8.0; Git/artifact identity distinguishes them | Runtime DB and historical evidence hashes unchanged | supported locally with versioning limitation |
| migrations 1–10 and history remain readable | local SQLite | deterministic fixture + real local install | migration-focused suite; installed wheel double migration | passed; migration head 10 | No production database was modified | disposable databases only | implementation passed |
| deterministic GitHub state machine | deterministic provider fixtures | deterministic fixture | full regression and Phase 5 suites | passed | Cannot qualify GitHub API, Checks, auth, protection, or cleanup | no external write | fixture passed only |
| real GitHub PR/Checks/recovery | exact approved repository/auth/cleanup scope | blocked | not executed | blocked by authorization; `gh 2.97.0` is unauthenticated | No owner/repository/branch/write/cleanup authority | no branch, PR, Check, comment, setting, or merge | blocked |
| deterministic container policy/recovery | fake adapter fixtures | deterministic fixture | full Phase 6C regression | passed | Cannot qualify daemon isolation, resources, mounts, network, or cleanup | no container effect | fixture passed only |
| real container pinned-image isolation | approved runtime + daemon + local digest | blocked | read-only availability check: Docker/Podman absent | blocked by environment and authorization | No runtime or pinned local image | no install, service start, pull, container, volume, or network | blocked |
| static Plugin/MCP compatibility | repository Plugin + Codex 0.147.0 + ge 0.8.x | deterministic fixture | manifest/Skill/MCP strict tests; direct installed MCP handshake | passed | Plugin was not installed or loaded | no Codex config/marketplace mutation | fixture passed only |
| real Codex Plugin load and autonomous execution | approved isolated CODEX_HOME + disposable Git repo | blocked | not executed | blocked by authorization | Codex 0.147.0 is authenticated, but auth alone is not execution authority | no Plugin/config/repository effect | blocked |
| Windows supported-platform matrix | real Windows host | supported-platform evidence | double-Python full suite plus installed package, Service/IPC, worktree, subprocess, parallel, barrier and recovery tests | local core boundaries passed | Real Plugin-load/Codex and container boundaries remain blocked; Windows release as a whole is not fully qualified | no external residual effect | partially supported; overall unverified |
| Linux supported-platform matrix | approved real Linux host/runner | unverified | not executed | no runner or authority | Windows evidence cannot substitute | none | unverified |
| macOS supported-platform matrix | approved real macOS host/runner | unverified | not executed | no runner or authority | Windows evidence cannot substitute | none | unverified |

## Failure and recovery evidence

- Managed sandbox baseline: 225 collected, 70 passed, 3 skipped, 152 pytest temporary-root ACL
  errors, exit 1. It is classified environment failure, not passed and not a product assertion
  failure. Fresh host basetemps passed.
- Development venv distribution metadata was stale at 0.2.0 while source was 0.8.0. Existing venvs
  were not modified to hide the mismatch; clean wheel installs proved 0.8.0/0.8.0 identity.
- First sdist builds had identical file bytes but different tar/gzip timestamps. ADR-041 records the
  product packaging fix and final reproducible hashes.
- First clean-install smoke truncated Rich help through a pipe; second cleanup check read a stale
  process handle. Both were qualification orchestration failures. New directories and factual
  PID/endpoint checks produced exit-0 evidence.
- Identity v1 failed reader decoding under the Windows locale; v2 fixed decoding but checked only
  the wrong Codex auth stream; v3 records the corrected enum-only authentication state. All three
  evidence files are retained.

## Release conclusion

The Phase 6E evidence implementation and authorized local Windows packaging/product boundaries are
ready for Human Review. Graph Engineering is **not release-qualified across all declared providers
or platforms**: real Codex Plugin load/autonomous execution, GitHub, and container E2E are blocked,
and Linux/macOS are unverified. No unavailable environment is represented as passed.

All 13 verified `ge-phase6e-*20260825*` system-temp roots used for basetemp, builds, venvs, package
artifacts, and smoke projects were removed after evidence hashes were recorded; cleanup found zero
matching residual roots. Historical workspace `.pytest-*` evidence was not deleted or overwritten.
