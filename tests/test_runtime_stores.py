from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from graph_engineering.runtime import ArtifactStore, EventStore, StateStore
from graph_engineering.runtime.store import _MIGRATION_1


def test_state_store_migrations_are_repeatable_and_transactions_roll_back(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "state.db")
    store.migrate()
    store.migrate()

    assert store.schema_version == 2
    with pytest.raises(RuntimeError, match="rollback"), store.transaction() as connection:
        connection.execute(
            "INSERT INTO event_outbox(event_id, event_json, created_at) VALUES (?, ?, ?)",
            ("rolled-back", "{}", "2026-08-16T00:00:00Z"),
        )
        raise RuntimeError("rollback")
    assert store.outbox_rows() == []


def test_event_store_flushes_outbox_idempotently(tmp_path: Path) -> None:
    state = StateStore(tmp_path / "state.db")
    state.migrate()
    state.record_event("run.created", "run-1", payload={"value": 1})
    events = EventStore(tmp_path / "events.jsonl")

    assert events.flush(state) == 1
    assert events.flush(state) == 0
    lines = (tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["event_type"] == "run.created"


def test_state_store_upgrades_an_existing_migration_1_database(tmp_path: Path) -> None:
    path = tmp_path / "state.db"
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        connection.executescript(_MIGRATION_1)
        connection.execute(
            "INSERT INTO schema_migrations(version, applied_at) VALUES (1, ?)",
            ("2026-08-16T00:00:00Z",),
        )
    store = StateStore(path)

    store.migrate()

    assert store.schema_version == 2
    with store.read_connection() as connection:
        node_columns = {str(row["name"]) for row in connection.execute("PRAGMA table_info(nodes)")}
        run_artifacts_exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'run_artifacts'"
        ).fetchone()
    assert {"first_started_at", "cost_units", "repair_iterations"} <= node_columns
    assert run_artifacts_exists is not None


def test_artifact_store_is_content_addressed_and_append_only(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path / "artifacts")
    first = store.put_bytes(b"evidence", media_type="text/plain")
    second = store.put_bytes(b"evidence", media_type="text/plain")

    assert first == second
    assert store.read_bytes(first.uri) == b"evidence"
    assert first.sha256_digest is not None
