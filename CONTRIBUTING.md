# Contributing

Graph Engineering is implemented phase by phase. Read `AGENTS.md`, `DESIGN.md`,
`docs/status/CURRENT.md`, and the active phase document before changing code. Preserve unrelated
work, use a phase- or change-specific branch, and do not implement a later phase before the active
phase acceptance criteria pass.

## Development setup

Python 3.12 and 3.13 are the supported development interpreters. Future Python versions require an
explicit compatibility update instead of being claimed implicitly.

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
```

Run the complete current checks (real Codex tests remain explicit acceptance commands):

```powershell
.venv\Scripts\python -m pytest
.venv\Scripts\python -m mypy src tests
.venv\Scripts\python -m ruff check src tests
.venv\Scripts\python -m ruff format --check src tests
.venv\Scripts\ge schema export --output schemas
git diff --exit-code -- schemas
$env:GE_RUN_REAL_CODEX="1"
.venv\Scripts\python -m pytest tests/test_phase5_real_codex_review.py -m real_codex
```

Pytest uses its platform-managed temporary root; do not restore a repository-local global
`--basetemp`. Historical `.pytest-*` and `.local` evidence may have restrictive Windows ACLs and
is excluded from Ruff discovery. Verification commands should target `src tests` as shown above.

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
