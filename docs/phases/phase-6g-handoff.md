# Phase 6G Optional Project UI handoff

## Delivery identity and startup gate

Phase 6G was implemented on the required long-lived branch `phase/6-enhancements`. The exact local
and remote starting HEAD was the Human-reviewed, accepted and pushed Phase 6F delivery
`ba30339922f9412cc369063efa2c136e0a3aef1f`; its only parent is the Phase 6E delivery
`e1aa9c61f568b7dda6c77248bc87a000f539a0ca`. `origin/main` remained
`eedc46d1a607c6169cb43eca79ef56bdd137efac`, and startup ahead/behind was `0/0`. The tracked and
untracked worktree was clean. Historical ignored `.pytest-*` ACL evidence was preserved.

This handoff belongs to the single local Phase 6G delivery commit authorized by the Human. Its exact
commit identity is the repository `HEAD` containing this file and is reported at handoff; no push,
PR, main mutation, merge or publication is part of Phase 6G.

## Baseline

Before edits, the managed-sandbox Python 3.13 run collected 248 tests and reached 82 passed / 3
skipped with 163 setup errors caused solely by the known Windows `tmp_path` ACL boundary. It had no
product assertion failure and was not represented as passed. Fresh host basetemps produced 244
passed / 4 skipped on Python 3.13 and Python 3.12. The four skips were exactly the historical opt-in
real-Codex acceptance cases. Mypy reported 136 source files clean; Ruff lint/format, 36-schema drift,
serial/parallel Graph validation and Verifier list/validate all passed.

## Architecture and provider boundary

ADR-043 selects an optional Python standard-library IPv4-loopback HTTP process. It server-renders
escaped semantic HTML, serves package-owned dependency-free CSS/JavaScript, exposes UI/API contract
1.0 full JSON snapshots, and performs one-at-a-time 5-second conditional polling. No Node, npm,
React, browser driver, CDN, analytics, font, frontend framework or new product dependency was added.

The UI process only calls `RuntimeServiceUIProvider`, which uses authenticated IPC 1.0. Additive
read-only `project_snapshot` and `run_snapshot` operations compile persisted facts at the existing
Human Gateway. Runtime SQLite remains the only Run authority. UI/browser/session/poll/ETag state is
disposable and never opens SQLite, routes recovery, starts providers, writes worktrees or becomes
evidence. Migration head remains 10; public Schema count remains 36; package remains 0.8.0 and
Python remains `>=3.12,<3.14`.

## Pages, controls and recovery

Project and Run pages display Run/terminal state, nodes, attempts, parallel branches, Sessions,
risks, budgets, frozen Contract identity, Requirement Matrix classification, Verifier/repair,
Review/review-fix, read-only GitHub delivery/check handles, Final Report, Artifact/container metadata,
Human conversations, persisted pending confirmations and Human decisions. Missing data is rendered
as unavailable/unverified rather than authoritative or passed.

Package-owned JavaScript submits messages and pause/resume/interrupt/cancel/accept/reject/revise
forms as bounded same-origin JSON. Natural-language-capable controls persist `HumanMessage` and
re-enter the Intent Compiler; the action route and compiled message are bound fail-closed. Cancel
uses its existing typed Gateway route while preserving the optional Human message. Confirmation
and execution remain separate. Cards bind project, actor/session context, source message, pending
action, intent/action, Run, Contract revision/hash, creation/expiry, snapshot, request and
idempotency identities. Expired, stale, mismatched, replayed or consumed cards fail closed. Delivery
accept/reject/revise use the existing Phase 6D decision boundary; accept records a Human decision
and `merge_performed=False`.

Polling carries no deltas and no recovery facts. An ETag duplicate returns 304. A changed digest,
source instance, stale/disconnected request, Runtime restart or endpoint rotation causes a fresh
full snapshot. Terminal late persisted facts can therefore appear without changing terminal Run
authority. Client polling and mutation requests are single-flight; server handlers, request queue,
body, response, header count, timeout, burst and rate are finite. Slow/disconnected clients are
closed or recover from the next snapshot.

## Security, rendering and accessibility

The server accepts only IPv4 loopback binding and loopback peers. Exact Host and Origin are checked;
mutations additionally require the HttpOnly `SameSite=Strict` session cookie,
`Sec-Fetch-Site: same-origin`, JSON MIME and exact bounded content length. CSP is default-deny with
only same-origin package scripts/styles/connect, plus frame denial, nosniff, no-referrer,
permissions policy and no-store for sensitive pages/API. Static assets have fixed MIME and immutable
cache policy. Header read timeout and listen backlog are established before request handling; known
unsupported HTTP methods return the same generic secured 405 boundary rather than framework errors.

All untrusted HTML, Markdown, path, repository URL, command, report and Artifact content is escaped
text and never made a link, event handler, HTML or script. Generic failures omit exception bodies,
paths and credentials. Snapshot secret-bearing keys fail closed, and configured raw, URL-encoded,
base64, overlapping and cross-chunk secret variants are rejected before output. No secret or
authoritative Run state is written to URL/query, JavaScript constants, DOM storage, localStorage or
sessionStorage. The real HTTP smoke and deterministic renderer tests cover semantic headings,
labels, keyboard-focusable facts/forms, skip navigation, live status text and non-color-only status.

## Test-first and verification evidence

The first Phase 6G test collection failed because `graph_engineering.ui` did not exist. After the
initial implementation, 18 focused tests passed. Delivery review then identified that the rendered
form was inert and polling had no browser controller; three new tests first failed on the missing
form bindings, `script-src` policy and packaged JavaScript, then passed after the dependency-free
controller was implemented.

Final product verification:

- Phase 6G focused: 18 passed.
- Affected Conversation/Control/Service/Phase 6D/6F/6G regression: 60 passed.
- Python 3.13 full: 262 passed / 4 skipped.
- Python 3.12 full: 262 passed / 4 skipped.
- Phase 6E qualification focused: 10 passed on a host basetemp.
- Mypy strict: 145 source files clean; Ruff lint and 145-file format check passed.
- 36 public schemas exported with zero drift; serial and parallel Graph validation plus Verifier
  list/validate passed. SQLite migration remains 10 with no migration or public protocol Schema.

The final package hash placeholders are replaced after the last documentation-complete build:

- wheel SHA-256: `eed8761bab2ae5f31ec38ef863b95b669bbd0fcebc018780009bfa518d7e762f`
- sdist SHA-256: `8be131b5220b11379889b172558bbf04771f95a103d4ad71871b3bb24884f01c`

Each archive was built twice with the Phase 6E-qualified toolchain (build 1.3.0, setuptools 80.9.0,
wheel 0.45.1, packaging 26.3, pyproject-hooks 1.2.0 and colorama 0.4.6) and fixed
`SOURCE_DATE_EPOCH`; both pairs were byte-identical. Fresh Python 3.13 and 3.12 venvs resolved only
the declared project dependencies and installed the local wheel. Both passed distribution/source
version 0.8.0, CLI and `ge ui` help, package static assets, 36-schema export, serial/parallel Graph
and Verifier list/validate smoke.

## Preserved failures, cleanup and residual effects

The first package-smoke orchestration created child venvs with `--system-site-packages`; those child
venvs did not inherit project dependencies and the install failed on missing Pydantic. It also tried
to copy a repository `LICENSE` file that does not exist. That failure is preserved and was not
classified as product success. A corrected clean install resolved declared dependencies. A later
custom smoke asserted the valid 805-byte CSS was larger than 1000 bytes; the wheel build/install was
successful but that invalid assertion stopped the run. The corrected semantic assertion checked the
actual focus style and passed. One focused command also named nonexistent `tests/test_migrations.py`;
the real Phase 6E qualification file and both full suites passed. Managed-sandbox pytest attempts
that hit the known tmp ACL are retained separately from host success.

All exact package-smoke roots were removed in `finally`; only normal shared pip cache entries may
remain and were not deleted as shared user data. Host pytest basetemps are local verification
residue. No browser process/farm, container runtime/image, Runtime provider side effect, GitHub
write, Plugin install, system service, external UI, collector/telemetry endpoint, cloud resource,
DNS, TLS, CDN, analytics or paid resource was created or contacted. No package or UI was published.

## Honest limitations and roadmap-end gate

The deterministic renderer/API/real-loopback-HTTP tests are not a real browser matrix. Real browser
behavior, automated accessibility tooling, screenshots, external hosting/TLS, Linux and macOS UI
remain unverified. Existing real Codex Plugin, GitHub and container limitations from the frozen
Phase 6E qualification report are unchanged; Phase 6E evidence and Phase 6F handoff were not
rewritten.

Phase 6G is the last scheduled Phase 6 roadmap item. After the authorized local delivery commit,
the next gate is Human review. Do not push, create a PR, modify/merge main, publish/install package,
Plugin or UI, perform real external writes, enable auto-merge, or start Claude Code Adapter,
distributed workers, startup services, Phase 6H or any unscheduled phase without new explicit scope.
