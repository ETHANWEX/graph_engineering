# Contributing

Graph Engineering is implemented phase by phase. Read `AGENTS.md`, `DESIGN.md`,
`docs/status/CURRENT.md`, and the active phase document before changing code. Preserve unrelated
work, use a phase- or change-specific branch, and do not implement a later phase before the active
phase acceptance criteria pass.

## Development setup

Python 3.12 or newer is required.

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
```

Run the complete Phase 0–2 checks (the real Codex test is an explicit acceptance command):

```powershell
.venv\Scripts\python -m pytest
.venv\Scripts\python -m mypy src tests
.venv\Scripts\python -m ruff check src tests
.venv\Scripts\python -m ruff format --check src tests
.venv\Scripts\ge schema export --output schemas
git diff --exit-code -- schemas
$env:GE_RUN_REAL_CODEX="1"
$env:GE_REAL_CODEX_FIXTURE_ROOT="<ignored-isolated-fixture-root>"
.venv\Scripts\python -m pytest tests/test_phase2_real_codex.py -m real_codex
```

The committed JSON Schemas are compatibility surfaces. Update models, fixtures, tests, schemas,
and an ADR together when deliberately changing a public protocol. Contract revisions append a new
revision; they never overwrite a frozen revision.

## Scope and safety

- Core protocols must remain independent from Codex, Claude Code, and other provider session data.
- Route conditions are structured data and must never evaluate Python or shell source.
- Natural-language Human input belongs in `HumanMessage`; runtime controls use typed
  `ControlIntent` values.
- Keep frozen contracts, verifier definitions, acceptance locks, and evidence outside writable
  implementation worktrees in phases that introduce execution.
- Do not merge a delivery branch into `main` without Human review and explicit approval.
