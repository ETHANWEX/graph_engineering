# Phase 4 Handoff

## Delivery summary and stacked baseline

- Branch: `phase/4-dynamic-verifiers`.
- Phase 2 approved commit: `53df64ceea904bdad1f39f04a5d3168f5ae40d25`.
- Phase 3 approved commit: `b746b3f6b9f70838a6fe063e8a90104be7bca8a8`.
- Phase 3 was reverified at 108 collected / 106 passed / 2 skipped, committed with
  `feat: implement phase 3 discovery and contract freeze`, pushed, and verified with both
  `git rev-parse phase/3-discovery-contract` and
  `git rev-parse origin/phase/3-discovery-contract` returning the full Phase 3 SHA above.
- Phase 4 was created directly from that exact commit. `merge-base` and Phase 4 initial HEAD both
  equal the Phase 3 SHA.
- `origin/main=a069b36fc0169dc51400265ea72a64c7b0b2839f`; Phase 2 and Phase 3 remain unmerged.
- Mandatory integration order is Phase 2 → Phase 3 → Phase 4. No pseudo-merge, rebase, reset,
  force, PR, main mutation, or automatic merge occurred.
- Human explicitly approved committing and pushing Phase 4 on 2026-08-18. Delivery is limited to
  `origin/phase/4-dynamic-verifiers`; PR creation, main mutation, merge, and Phase 5 remain forbidden.

## Scope and ADRs

- Scope: `docs/phases/phase-4.md`.
- ADR-019: exact Verifier Registry/SDK and unified result semantics.
- ADR-020: HTTP pipeline state machine, idempotent trigger, durable handle, recovery, and cancel.
- ADR-021: argv-only subprocess, capability policy, secret references, and redaction.
- ADR-022: validate/test/dry-run/freeze lifecycle and acceptance hashes.
- ADR-023: declaration-first Codex generation trust boundary.

## SQLite migration 5

Migration 5 adds:

- `verifier_revisions` with canonical Manifest, source/tests/fixtures paths and hashes, lifecycle,
  permission summary, confirmation, and freeze time;
- `verifier_lifecycle_evidence` for append-only validate/test/dry-run evidence;
- `contract_verifier_bindings` as the acceptance-lock extension containing the exact Verifier
  revision and Manifest/source/tests/fixtures hashes for a Contract revision;
- external-handle verifier owner/revision, cancellation state, report Artifact ID, and residual
  effect columns.

Compatibility views remain `schema_version == 2`, `latest_migration_version == 3`, and
`storage_migration_version == 4`; `database_migration_version == 5` is the actual head.

## Registry, SDK, and result semantics

`VerifierRegistry` uses exact type keys, sorted inventory, and fails on duplicate or unknown types.
The builtin registry contains `builtin/command`, `builtin/http-pipeline`, and
`project/subprocess`. Phase 4 internal immutable SDK models define Manifest, capabilities,
revision hashes, requests, outcomes, and execute/poll/cancel protocol. Public Schema 1.0
`VerifierResult` remains unchanged: only `failed` is an acceptance failure eligible for repair;
`error` is verifier/infrastructure failure; `cancelled` is cancellation; `pending` owns a handle.

## HTTP Pipeline

- Declarative method, URL, header, JSON body, external-ID path, status path/mapping, report, and
  cancellation requests.
- Stable Runtime `run_id:node_id` idempotency key is sent as `Idempotency-Key` and available to
  body/header templates.
- Trigger intent is committed before I/O. A returned handle is checkpointed before poll. Runtime
  restart resolves the saved Verifier owner and polls the saved handle without retrigger.
- Per-request timeout, response cap, bounded retries, exponential backoff, pending/passed/failed
  mapping, report Artifact download, and cancellation are implemented.
- Redirects are not followed; any Location host is checked independently and exact-host allowlist
  prevents subdomain/redirect bypass.
- A local `ThreadingHTTPServer` fixture completed trigger → pending poll → passed poll → report;
  trigger count stayed one and report secret content was redacted.

## project/subprocess protocol

- Manifest entrypoint is an argv tuple; launch always uses `shell=False`.
- One bounded JSON request enters stdin and one public `VerifierResult` exits stdout.
- Minimal inherited process environment plus declared secret references only; no arbitrary shell
  string, Python evaluation, or expression execution exists.
- Timeout, combined output cap, invalid JSON/schema, spawn error, and abnormal exit map to
  infrastructure `error`. Valid `failed` remains an acceptance failure.
- stdout/stderr are redacted before content-addressed Artifact persistence.

## Manifest, capability policy, and secret safety

- Manifest fields: runtime, argv entrypoint, exact network hosts, explicit filesystem read/write
  paths, secret reference names, and external-side-effect disclosure.
- Network is default-deny; URL schemes are limited to HTTP(S); host entries reject wildcard,
  scheme, path, and duplicate forms. Filesystem access must stay under explicit resolved roots.
- Secret resolution fails closed and injects only Manifest-declared names.
- Redaction covers overlapping values, URL encoding, standard/URL-safe base64, and values split
  across chunks. Longest values are replaced first.
- Codex prompts receive reference names only. Generated last-message files, raw JSONL/stderr,
  subprocess logs, downloaded reports, errors, events, and reports do not retain secret values.

## Lifecycle, acceptance lock, and drift

Revisions progress `draft → validated → tested → dry_run → frozen`. Every transition requires
passed evidence; freeze requires an explicit Human confirmation message ID. Permission summary
lists exact entrypoint, network, filesystem, secret names, and external side effects. Freeze binds
canonical Manifest/source/tests/optional-fixtures SHA-256 values to the Contract revision. Frozen
rows have no update operation. Execution calls `verify_frozen` before HTTP trigger or subprocess
spawn; any drift rejects before side effects. A higher Verifier revision cannot bind to the same or
an older Contract revision.

CLI coverage: `ge verifier list`, `validate`, `permissions`, `test`, `dry-run`, and `freeze`.

## Runtime checkpoint, recovery, cancel, query, and routing

- `external_handles` persists the owner Verifier revision and stable idempotency key.
- A restart with a checkpointed handle uses `query_for` and never calls trigger again.
- Trigger intent without a handle retains the existing uncertain-side-effect terminal behavior.
- Interrupt persists the existing Runtime barrier transaction first, then calls `cancel_for`.
  Success stores `cancelled`; unsupported, exception, or unknown results store a residual-effect
  disclosure. Barrier tests prove no new HTTP/subprocess start after persistence.
- Existing read-only query fingerprints and Phase 4 read-only lifecycle queries do not mutate Run,
  handle, Verifier, budget, Session, route, or worktree state.
- The Phase 3 compiler already routes `failed` through bounded repair and supplies no repair edge
  for `error`; Phase 0–3 regression preserves that invariant.

## Codex generation evidence

Official OpenAI documentation used:
<https://learn.chatgpt.com/docs/developer-commands#codex-exec>. It confirms non-interactive
`codex exec`, JSONL via `--json`, final structured response via `--output-schema`, and explicit
sandbox selection. Local runtime facts are Windows, CPython 3.12.10, Codex CLI 0.147.0, and
`Logged in using ChatGPT`. No dangerous bypass was used.

The generator first requires Discovery to decide whether declarative HTTP is sufficient. When it
is insufficient, Codex emits a schema-validated Manifest plus implementation, fixtures, and tests
as safe relative file records. Raw JSONL/stderr are redacted Artifacts. Generation never executes
or freezes the bundle.

Real command:

```powershell
$env:GE_RUN_REAL_CODEX='1'
.local\venv312\Scripts\python.exe -m pytest tests\test_phase4_real_codex_verifier.py -vv -s --basetemp .local\phase4-real-codex-final
```

Final result: exit 0, 1 passed in 53.63s. Codex generated a project/subprocess Manifest,
implementation, fixture, and tests; generated tests passed; independent public-result validation,
policy dry-run, lifecycle evidence, Human-confirmed freeze, and hash recheck passed. The test secret
was absent from prompt and stored evidence.

Two earlier real attempts are intentionally disclosed: the first bundle invented a `passed`
boolean and was rejected by independent protocol validation; the second fixed result semantics but
omitted filesystem read capability and was rejected by policy before spawn. The prompt was then
tightened without weakening either gate. No Fake was substituted for real evidence.

## Deterministic verification

Expected final inventory is 135 tests: the Phase 0–3 baseline 108 plus 27 Phase 4 tests. Three
explicit real-Codex tests skip by default. Final commands and exact results are recorded in the
final review report; current full run is 135 collected / 132 passed / 3 skipped. Mypy strict and
Ruff lint/format pass. Public Schema remains 30 with no drift. Valid/invalid Graph and valid/invalid
Verifier Manifest CLI exit semantics pass.

Final deterministic commands and results:

- `.local\venv312\Scripts\python.exe -m pytest --basetemp .local\verify-phase4-final-host2`:
  exit 0, 135 collected / 132 passed / 3 skipped in 13.58s (14.0s wall time).
- `pytest --ignore-glob=tests/test_phase4_*`: exit 0, 108 collected / 106 passed / 2 skipped
  in 18.72s (19.4s wall time).
- Phase 0–2 ignore set: exit 0, 91 collected / 90 passed / 1 skipped in 15.00s
  (15.7s wall time).
- Phase 0–1 ignore set: exit 0, 62 passed in 12.97s (13.7s wall time).
- `python -m mypy src tests`: exit 0, no issues in 98 source files (1.1s recorded final run).
- `python -m ruff check src tests`: exit 0, all checks passed.
- `python -m ruff format --check src tests`: exit 0, 98 files already formatted.
- `ge schema export --output schemas`: exit 0, 30 schemas; schema drift exit 0.
- valid Graph CLI exit 0; invalid Graph CLI exit 2 with the expected two field paths.
- valid Verifier Manifest CLI exit 0; invalid wildcard-host Manifest exit 2.

One sandboxed final pytest retry is explicitly not counted: Windows denied its new basetemp and a
compound shell command allowed later static checks to mask pytest's nonzero status. The suite was
therefore rerun as a standalone host-boundary command above; only that direct exit 0 is acceptance
evidence.

## Risks and unverified items

- Production CI/webhooks were not called. HTTP E2E is a local isolated fixture only.
- subprocess isolation is an OS process with Manifest/policy/Human review, not a container.
- A malicious binary can exceed memory before post-collection output rejection; the configured
  byte cap prevents acceptance/persistence but streaming process I/O hard limits remain future
  defense-in-depth work.
- Cross-platform real Codex evidence is Windows only.
- Runtime is foreground and recoverable, not a daemon.
- GitHub/PR, auto-merge, Phase 5 review/delivery, Plugin/UI, parallel graphs, containers, and
  telemetry remain out of scope.

## Worktree and next step

- Human approved the Phase 4 delivery commit and push on 2026-08-18. The exact local/remote delivery
  SHA is verified with `git rev-parse` after creation because a commit cannot embed its own SHA.
- Historical `.pytest-tmp-phase*` and `.local/` verification evidence remains untracked/ignored and
  was not deleted or added.
- No PR or merge exists. Main was not modified.
- Phase 2 and Phase 3 must integrate before Phase 4. Do not begin Phase 5 before Phase 4 integration.
