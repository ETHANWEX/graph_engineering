"""SQLite state store with monotonic migrations and a transactional event outbox."""

from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def utc_now() -> datetime:
    return datetime.now(UTC)


def timestamp() -> str:
    return utc_now().isoformat().replace("+00:00", "Z")


class StateStore:
    """Authoritative Phase 1 state and atomic event intent storage."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _connect(self, *, readonly: bool = False) -> sqlite3.Connection:
        if readonly:
            connection = sqlite3.connect(
                f"file:{self.path.as_posix()}?mode=ro", uri=True, timeout=30
            )
        else:
            connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        if not readonly:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA synchronous = FULL")
        return connection

    def migrate(self) -> None:
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations "
                "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
            applied = {
                int(row[0]) for row in connection.execute("SELECT version FROM schema_migrations")
            }
            if 1 not in applied:
                connection.executescript(_MIGRATION_1)
                connection.execute(
                    "INSERT INTO schema_migrations(version, applied_at) VALUES (1, ?)",
                    (timestamp(),),
                )
            if 2 not in applied:
                connection.executescript(_MIGRATION_2)
                connection.execute(
                    "INSERT INTO schema_migrations(version, applied_at) VALUES (2, ?)",
                    (timestamp(),),
                )
            if 3 not in applied:
                connection.executescript(_MIGRATION_3)
                connection.execute(
                    "INSERT INTO schema_migrations(version, applied_at) VALUES (3, ?)",
                    (timestamp(),),
                )
            if 4 not in applied:
                connection.executescript(_MIGRATION_4)
                connection.execute(
                    "INSERT INTO schema_migrations(version, applied_at) VALUES (4, ?)",
                    (timestamp(),),
                )
            if 5 not in applied:
                connection.executescript(_MIGRATION_5)
                connection.execute(
                    "INSERT INTO schema_migrations(version, applied_at) VALUES (5, ?)",
                    (timestamp(),),
                )
            if 6 not in applied:
                connection.executescript(_MIGRATION_6)
                connection.execute(
                    "INSERT INTO schema_migrations(version, applied_at) VALUES (6, ?)",
                    (timestamp(),),
                )
            if 7 not in applied:
                connection.executescript(_MIGRATION_7)
                connection.execute(
                    "INSERT INTO schema_migrations(version, applied_at) VALUES (7, ?)",
                    (timestamp(),),
                )
            connection.commit()

    @property
    def schema_version(self) -> int:
        """Legacy Phase 1 compatibility level; use latest_migration_version for storage."""

        return min(self.latest_migration_version, 2)

    @property
    def latest_migration_version(self) -> int:
        """Phase 2 compatibility level; use storage_migration_version for the database head."""

        return min(self.storage_migration_version, 3)

    @property
    def storage_migration_version(self) -> int:
        """Phase 3 compatibility level; use database_migration_version for the actual head."""

        return min(self.database_migration_version, 4)

    @property
    def database_migration_version(self) -> int:
        """Phase 4 compatibility level; use delivery_migration_version for the actual head."""

        return min(self.delivery_migration_version, 5)

    @property
    def delivery_migration_version(self) -> int:
        """Compatibility level through Phase 5; use service_migration_version for head."""

        return min(self.service_migration_version, 6)

    @property
    def service_migration_version(self) -> int:
        """Actual storage head including Phase 6A service tables."""

        with self.read_connection() as connection:
            row = connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
            return int(row[0]) if row is not None and row[0] is not None else 0

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    @contextmanager
    def read_connection(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect(readonly=True)
        try:
            connection.execute("BEGIN")
            yield connection
            connection.rollback()
        finally:
            connection.close()

    def enqueue_event(
        self,
        connection: sqlite3.Connection,
        event_type: str,
        run_id: str,
        *,
        node_id: str | None = None,
        attempt_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> str:
        event_id = str(uuid.uuid4())
        event = {
            "event_id": event_id,
            "event_type": event_type,
            "run_id": run_id,
            "node_id": node_id,
            "attempt_id": attempt_id,
            "occurred_at": timestamp(),
            "payload": payload or {},
        }
        connection.execute(
            "INSERT INTO event_outbox(event_id, event_json, created_at) VALUES (?, ?, ?)",
            (
                event_id,
                json.dumps(event, ensure_ascii=False, separators=(",", ":"), sort_keys=True),
                timestamp(),
            ),
        )
        return event_id

    def record_event(
        self, event_type: str, run_id: str, *, payload: dict[str, Any] | None = None
    ) -> str:
        with self.transaction() as connection:
            return self.enqueue_event(connection, event_type, run_id, payload=payload)

    def outbox_rows(self) -> list[sqlite3.Row]:
        with self.read_connection() as connection:
            return list(
                connection.execute(
                    "SELECT event_id, event_json FROM event_outbox "
                    "WHERE delivered_at IS NULL ORDER BY rowid"
                )
            )

    def mark_event_delivered(self, event_id: str) -> None:
        with self.transaction() as connection:
            connection.execute(
                "UPDATE event_outbox SET delivered_at = ? "
                "WHERE event_id = ? AND delivered_at IS NULL",
                (timestamp(), event_id),
            )


_MIGRATION_1 = """
CREATE TABLE runs (
    run_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    contract_id TEXT NOT NULL,
    contract_revision INTEGER NOT NULL,
    contract_hash TEXT NOT NULL,
    graph_id TEXT NOT NULL,
    graph_hash TEXT NOT NULL,
    graph_json TEXT NOT NULL,
    status TEXT NOT NULL,
    barrier TEXT,
    current_node_id TEXT,
    parent_run_id TEXT,
    supersedes_run_id TEXT,
    restart_from_json TEXT,
    terminal_reason TEXT,
    error_json TEXT,
    unverified_json TEXT NOT NULL DEFAULT '[]',
    external_effects_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE nodes (
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    node_id TEXT NOT NULL,
    node_type TEXT NOT NULL,
    status TEXT NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    result_json TEXT,
    route_resolved INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY(run_id, node_id)
);

CREATE TABLE attempts (
    attempt_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    node_id TEXT NOT NULL,
    attempt_number INTEGER NOT NULL,
    status TEXT NOT NULL,
    result_json TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    UNIQUE(run_id, node_id, attempt_number),
    FOREIGN KEY(run_id, node_id) REFERENCES nodes(run_id, node_id)
);

CREATE TABLE edge_traversals (
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    from_node TEXT NOT NULL,
    to_node TEXT NOT NULL,
    traversal_count INTEGER NOT NULL,
    PRIMARY KEY(run_id, from_node, to_node)
);

CREATE TABLE budgets (
    run_id TEXT PRIMARY KEY REFERENCES runs(run_id),
    max_duration_seconds INTEGER NOT NULL,
    max_executor_calls INTEGER NOT NULL,
    max_repair_iterations INTEGER NOT NULL,
    max_cost_units REAL,
    executor_calls INTEGER NOT NULL DEFAULT 0,
    repair_iterations INTEGER NOT NULL DEFAULT 0,
    cost_units REAL
);

CREATE TABLE checkpoints (
    checkpoint_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    reason TEXT NOT NULL,
    state_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE external_handles (
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    node_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    trigger_state TEXT NOT NULL,
    handle TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(run_id, node_id)
);

CREATE TABLE control_intents (
    intent_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    intent_kind TEXT NOT NULL,
    action TEXT NOT NULL,
    intent_json TEXT NOT NULL,
    outcome TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE reports (
    run_id TEXT PRIMARY KEY REFERENCES runs(run_id),
    report_json TEXT NOT NULL,
    frozen_at TEXT NOT NULL
);

CREATE TABLE artifact_metadata (
    artifact_id TEXT PRIMARY KEY,
    run_id TEXT REFERENCES runs(run_id),
    uri TEXT NOT NULL UNIQUE,
    sha256_digest TEXT NOT NULL,
    media_type TEXT,
    size_bytes INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE event_outbox (
    event_id TEXT PRIMARY KEY,
    event_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    delivered_at TEXT
);
"""

_MIGRATION_2 = """
ALTER TABLE nodes ADD COLUMN first_started_at TEXT;
ALTER TABLE nodes ADD COLUMN cost_units REAL NOT NULL DEFAULT 0;
ALTER TABLE nodes ADD COLUMN repair_iterations INTEGER NOT NULL DEFAULT 0;
ALTER TABLE budgets ADD COLUMN started_at TEXT;
UPDATE budgets
SET started_at = (SELECT created_at FROM runs WHERE runs.run_id = budgets.run_id)
WHERE started_at IS NULL;
ALTER TABLE checkpoints ADD COLUMN checkpoint_ref TEXT;
UPDATE checkpoints
SET checkpoint_ref = 'checkpoint:' || checkpoint_id
WHERE checkpoint_ref IS NULL;
CREATE UNIQUE INDEX checkpoints_ref_unique ON checkpoints(checkpoint_ref);
ALTER TABLE artifact_metadata ADD COLUMN kind TEXT NOT NULL DEFAULT 'evidence';
CREATE TABLE run_artifacts (
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    artifact_id TEXT NOT NULL REFERENCES artifact_metadata(artifact_id),
    node_id TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL,
    inherited_from_run_id TEXT,
    PRIMARY KEY(run_id, artifact_id, node_id, role)
);
"""

_MIGRATION_3 = """
CREATE TABLE executor_sessions (
    session_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    node_id TEXT NOT NULL,
    attempt_id TEXT NOT NULL,
    role TEXT NOT NULL,
    provider TEXT NOT NULL,
    provider_session_id TEXT NOT NULL,
    provider_version TEXT NOT NULL,
    status TEXT NOT NULL,
    continuation_count INTEGER NOT NULL DEFAULT 0,
    failure_count INTEGER NOT NULL DEFAULT 0,
    process_id INTEGER,
    raw_stdout_artifact_id TEXT,
    raw_stderr_artifact_id TEXT,
    outcome_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(provider, provider_session_id, attempt_id)
);
CREATE INDEX executor_sessions_run_node ON executor_sessions(run_id, node_id, created_at);

CREATE TABLE supervised_processes (
    process_handle_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    session_id TEXT REFERENCES executor_sessions(session_id),
    process_id INTEGER NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    settled_at TEXT
);

CREATE TABLE review_attempts (
    review_attempt_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    session_id TEXT NOT NULL REFERENCES executor_sessions(session_id),
    attempt_number INTEGER NOT NULL,
    verdict TEXT,
    result_artifact_id TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(run_id, attempt_number)
);

CREATE TABLE verifier_executions (
    verifier_execution_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    node_id TEXT NOT NULL,
    attempt_id TEXT NOT NULL,
    argv_json TEXT NOT NULL,
    status TEXT NOT NULL,
    process_id INTEGER,
    stdout_artifact_id TEXT,
    stderr_artifact_id TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT
);
"""

_MIGRATION_4 = """
CREATE TABLE conversations (
    conversation_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    active_run_id TEXT,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE human_messages (
    message_id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(conversation_id),
    message_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX human_messages_conversation ON human_messages(conversation_id, created_at);

CREATE TABLE intent_compilations (
    compilation_id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(conversation_id),
    source_message_id TEXT NOT NULL REFERENCES human_messages(message_id),
    intent_json TEXT,
    confidence REAL NOT NULL,
    clarification TEXT,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE pending_confirmations (
    confirmation_id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(conversation_id),
    intent_json TEXT NOT NULL,
    status TEXT NOT NULL,
    result_json TEXT,
    created_at TEXT NOT NULL,
    resolved_at TEXT
);

CREATE TABLE discovery_sessions (
    session_id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    project_root TEXT NOT NULL,
    state TEXT NOT NULL,
    scan_json TEXT NOT NULL,
    unknowns_json TEXT NOT NULL,
    answers_json TEXT NOT NULL,
    draft_json TEXT,
    source_message_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE contract_drafts (
    draft_id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    contract_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    contract_json TEXT NOT NULL,
    contract_hash TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(contract_id, revision, contract_hash)
);

CREATE TABLE contract_revisions (
    contract_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    contract_json TEXT NOT NULL,
    contract_hash TEXT NOT NULL,
    confirmation_message_id TEXT NOT NULL,
    frozen_at TEXT NOT NULL,
    PRIMARY KEY(contract_id, revision),
    UNIQUE(contract_hash)
);

CREATE TABLE acceptance_locks (
    lock_id TEXT PRIMARY KEY,
    contract_id TEXT NOT NULL,
    contract_revision INTEGER NOT NULL,
    contract_hash TEXT NOT NULL,
    verifier_hashes_json TEXT NOT NULL,
    confirmation_message_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(contract_id, contract_revision),
    FOREIGN KEY(contract_id, contract_revision)
      REFERENCES contract_revisions(contract_id, revision)
);

CREATE TABLE contract_deltas (
    delta_id TEXT PRIMARY KEY,
    contract_id TEXT NOT NULL,
    source_revision INTEGER NOT NULL,
    new_revision INTEGER NOT NULL,
    delta_json TEXT NOT NULL,
    confirmation_message_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(contract_id, new_revision)
);

CREATE TABLE planned_runs (
    run_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    contract_id TEXT NOT NULL,
    contract_revision INTEGER NOT NULL,
    graph_json TEXT NOT NULL,
    graph_hash TEXT NOT NULL,
    parent_run_id TEXT,
    supersedes_run_id TEXT,
    restart_from_json TEXT,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""

_MIGRATION_5 = """
CREATE TABLE verifier_revisions (
    verifier_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    verifier_type TEXT NOT NULL,
    manifest_json TEXT NOT NULL,
    manifest_hash TEXT NOT NULL,
    source_hash TEXT NOT NULL,
    tests_hash TEXT NOT NULL,
    fixtures_hash TEXT,
    source_path TEXT NOT NULL,
    tests_path TEXT NOT NULL,
    fixtures_path TEXT,
    lifecycle TEXT NOT NULL,
    permission_summary TEXT NOT NULL,
    confirmation_message_id TEXT,
    created_at TEXT NOT NULL,
    frozen_at TEXT,
    PRIMARY KEY(verifier_id, revision)
);

CREATE TABLE verifier_lifecycle_evidence (
    evidence_id TEXT PRIMARY KEY,
    verifier_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    lifecycle TEXT NOT NULL,
    result_json TEXT NOT NULL,
    artifact_id TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(verifier_id, revision) REFERENCES verifier_revisions(verifier_id, revision)
);

CREATE TABLE contract_verifier_bindings (
    contract_id TEXT NOT NULL,
    contract_revision INTEGER NOT NULL,
    verifier_id TEXT NOT NULL,
    verifier_revision INTEGER NOT NULL,
    hashes_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(contract_id, contract_revision, verifier_id),
    FOREIGN KEY(verifier_id, verifier_revision)
      REFERENCES verifier_revisions(verifier_id, revision)
);

ALTER TABLE external_handles ADD COLUMN verifier_id TEXT;
ALTER TABLE external_handles ADD COLUMN verifier_revision INTEGER;
ALTER TABLE external_handles ADD COLUMN cancel_state TEXT;
ALTER TABLE external_handles ADD COLUMN report_artifact_id TEXT;
ALTER TABLE external_handles ADD COLUMN residual_effect TEXT;
"""

_MIGRATION_6 = """
CREATE TABLE phase5_review_attempts (
    run_id TEXT NOT NULL,
    attempt_number INTEGER NOT NULL,
    status TEXT NOT NULL,
    fix_count INTEGER NOT NULL DEFAULT 0,
    affected_verifiers_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    invalidated_at TEXT,
    PRIMARY KEY(run_id, attempt_number)
);

CREATE TABLE phase5_review_dimensions (
    run_id TEXT NOT NULL,
    attempt_number INTEGER NOT NULL,
    dimension TEXT NOT NULL,
    session_id TEXT NOT NULL,
    result_json TEXT,
    created_at TEXT NOT NULL,
    PRIMARY KEY(run_id, attempt_number, dimension),
    FOREIGN KEY(run_id, attempt_number)
      REFERENCES phase5_review_attempts(run_id, attempt_number)
);

CREATE TABLE requirement_matrix_revisions (
    contract_id TEXT NOT NULL,
    contract_revision INTEGER NOT NULL,
    matrix_revision INTEGER NOT NULL,
    matrix_json TEXT NOT NULL,
    matrix_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(contract_id, contract_revision, matrix_revision)
);

CREATE TABLE github_check_queries (
    query_id TEXT PRIMARY KEY,
    run_id TEXT,
    repository TEXT NOT NULL,
    commit_sha TEXT NOT NULL,
    status_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE pull_request_intents (
    idempotency_key TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    repository TEXT NOT NULL,
    base_branch TEXT NOT NULL,
    head_branch TEXT NOT NULL,
    spec_json TEXT NOT NULL,
    state TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE pull_request_handles (
    idempotency_key TEXT PRIMARY KEY REFERENCES pull_request_intents(idempotency_key),
    run_id TEXT NOT NULL,
    repository TEXT NOT NULL,
    base_branch TEXT NOT NULL,
    head_branch TEXT NOT NULL,
    pr_number INTEGER NOT NULL,
    pr_url TEXT NOT NULL,
    node_id TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE delivery_terminal_fixtures (
    run_id TEXT PRIMARY KEY,
    contract_id TEXT NOT NULL,
    contract_revision INTEGER NOT NULL,
    status TEXT NOT NULL,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE delivery_report_revisions (
    run_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    terminal_status TEXT NOT NULL,
    terminal_reason TEXT NOT NULL,
    manifest_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(run_id, revision)
);

CREATE TABLE human_acceptance_records (
    record_id TEXT PRIMARY KEY,
    source_message_id TEXT NOT NULL UNIQUE,
    intent_id TEXT NOT NULL UNIQUE,
    run_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    action TEXT NOT NULL,
    reason TEXT,
    contract_revision INTEGER NOT NULL,
    report_revision INTEGER NOT NULL,
    new_contract_revision INTEGER,
    new_run_id TEXT,
    created_at TEXT NOT NULL
);
"""

_MIGRATION_7 = """
ALTER TABLE pending_confirmations ADD COLUMN actor_id TEXT;
ALTER TABLE pending_confirmations ADD COLUMN project_id TEXT;
ALTER TABLE pending_confirmations ADD COLUMN protocol_major INTEGER NOT NULL DEFAULT 1;
ALTER TABLE pending_confirmations ADD COLUMN expires_at TEXT;

CREATE TABLE ipc_mutation_replays (
    idempotency_key TEXT PRIMARY KEY,
    request_fingerprint TEXT NOT NULL,
    project_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    operation TEXT NOT NULL,
    response_json TEXT,
    state TEXT NOT NULL,
    created_at TEXT NOT NULL,
    completed_at TEXT
);
"""
