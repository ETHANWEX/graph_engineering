# ADR-002: Python 3.12 Phase 0 toolchain

- Status: Accepted
- Date: 2026-08-16

## Context

Phase 0 needs installable packaging, strongly validated language-neutral schemas, a small CLI, type
checking, and fast tests. The design baseline selected Python for the MVP.

## Decision

Use Python 3.12+, a `src` layout, Pydantic v2, Typer, PyYAML, pytest, mypy in strict mode, and Ruff
for linting and formatting. Use standard `pyproject.toml` packaging with setuptools. Export JSON
Schema draft 2020-12 documents from Pydantic models.

## Consequences

Development requires Python. The wire formats remain JSON/YAML and do not depend on Python object
serialization. SQLite, asyncio, HTTP, executors, and runtime behavior are intentionally not added in
Phase 0.

