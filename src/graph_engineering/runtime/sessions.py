"""Durable provider-neutral Session metadata and recovery operations."""

from __future__ import annotations

import json
import uuid
from typing import cast

from graph_engineering.executor.types import (
    ExecutorEvent,
    ExecutorOutcome,
    ExecutorRole,
    SessionHandle,
    SessionRecord,
    SessionStatus,
)
from graph_engineering.models import Artifact, ExecutorResult

from .store import StateStore, timestamp


class SessionRepository:
    def __init__(self, state: StateStore) -> None:
        self.state = state
        self.state.migrate()

    def ensure_run_fixture(self, run_id: str) -> None:
        """Compatibility no-op: Session rows deliberately do not own authoritative Run state."""

        if not run_id:
            raise ValueError("run_id must not be empty")

    def start(
        self,
        run_id: str,
        node_id: str,
        attempt_id: str,
        role: ExecutorRole,
        provider: str,
        provider_session_id: str,
        provider_version: str,
        *,
        process_id: int | None = None,
        continuation_count: int = 0,
        failure_count: int = 0,
    ) -> SessionRecord:
        session_id = f"session:{uuid.uuid4()}"
        now = timestamp()
        with self.state.transaction() as connection:
            connection.execute(
                """
                INSERT INTO executor_sessions(
                    session_id, run_id, node_id, attempt_id, role, provider,
                    provider_session_id, provider_version, status, process_id,
                    continuation_count, failure_count,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    run_id,
                    node_id,
                    attempt_id,
                    role.value,
                    provider,
                    provider_session_id,
                    provider_version,
                    SessionStatus.RUNNING.value,
                    process_id,
                    continuation_count,
                    failure_count,
                    now,
                    now,
                ),
            )
            self.state.enqueue_event(
                connection,
                "executor.session.started",
                run_id,
                node_id=node_id,
                attempt_id=attempt_id,
                payload={
                    "session_id": session_id,
                    "provider": provider,
                    "provider_version": provider_version,
                    "role": role.value,
                },
            )
        return cast(SessionRecord, self.get(session_id))

    def get(self, session_id: str) -> SessionRecord | None:
        with self.state.read_connection() as connection:
            row = connection.execute(
                "SELECT * FROM executor_sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
        if row is None:
            return None
        return SessionRecord(
            session_id=str(row["session_id"]),
            run_id=str(row["run_id"]),
            node_id=str(row["node_id"]),
            attempt_id=str(row["attempt_id"]),
            role=ExecutorRole(str(row["role"])),
            provider=str(row["provider"]),
            provider_session_id=str(row["provider_session_id"]),
            provider_version=str(row["provider_version"]),
            status=SessionStatus(str(row["status"])),
            continuation_count=int(row["continuation_count"]),
            failure_count=int(row["failure_count"]),
            process_id=int(row["process_id"]) if row["process_id"] is not None else None,
        )

    def latest(self, run_id: str, node_id: str) -> SessionRecord | None:
        with self.state.read_connection() as connection:
            row = connection.execute(
                "SELECT session_id FROM executor_sessions WHERE run_id = ? AND node_id = ? "
                "ORDER BY created_at DESC, rowid DESC LIMIT 1",
                (run_id, node_id),
            ).fetchone()
        return self.get(str(row["session_id"])) if row is not None else None

    def completed_outcome(self, run_id: str, attempt_id: str) -> ExecutorOutcome | None:
        with self.state.read_connection() as connection:
            row = connection.execute(
                "SELECT outcome_json FROM executor_sessions WHERE run_id = ? AND attempt_id = ? "
                "AND status = ? ORDER BY created_at DESC LIMIT 1",
                (run_id, attempt_id, SessionStatus.COMPLETED.value),
            ).fetchone()
        if row is None or row["outcome_json"] is None:
            return None
        value = cast(dict[str, object], json.loads(str(row["outcome_json"])))
        session_data = cast(dict[str, str], value["session"])
        events_data = cast(list[dict[str, object]], value["events"])
        return ExecutorOutcome(
            session=SessionHandle(**session_data),
            result=ExecutorResult.model_validate(value["result"]),
            events=tuple(
                ExecutorEvent(
                    event_type=str(event["event_type"]),
                    provider_event_type=cast(str | None, event.get("provider_event_type")),
                    session_id=cast(str | None, event.get("session_id")),
                    data=cast(dict[str, object], event["data"]),
                )
                for event in events_data
            ),
            raw_stdout=Artifact.model_validate(value["raw_stdout"]),
            raw_stderr=(
                Artifact.model_validate(value["raw_stderr"])
                if value.get("raw_stderr") is not None
                else None
            ),
            exit_code=int(cast(int, value["exit_code"])),
        )

    def record_continuation(self, session_id: str) -> None:
        self._increment(session_id, "continuation_count")

    def record_failure(self, session_id: str) -> None:
        self._increment(session_id, "failure_count")

    def complete(
        self,
        session_id: str,
        *,
        stdout_artifact_id: str | None = None,
        stderr_artifact_id: str | None = None,
        outcome: ExecutorOutcome | None = None,
    ) -> None:
        with self.state.transaction() as connection:
            connection.execute(
                "UPDATE executor_sessions SET status = ?, raw_stdout_artifact_id = ?, "
                "raw_stderr_artifact_id = ?, outcome_json = ?, updated_at = ? WHERE session_id = ?",
                (
                    SessionStatus.COMPLETED.value,
                    stdout_artifact_id,
                    stderr_artifact_id,
                    self._outcome_json(outcome) if outcome is not None else None,
                    timestamp(),
                    session_id,
                ),
            )

    @staticmethod
    def _outcome_json(outcome: ExecutorOutcome) -> str:
        value = {
            "session": {
                "provider": outcome.session.provider,
                "provider_session_id": outcome.session.provider_session_id,
                "provider_version": outcome.session.provider_version,
            },
            "result": outcome.result.model_dump(mode="json"),
            "events": [
                {
                    "event_type": event.event_type,
                    "provider_event_type": event.provider_event_type,
                    "session_id": event.session_id,
                    "data": event.data,
                }
                for event in outcome.events
            ],
            "raw_stdout": outcome.raw_stdout.model_dump(mode="json"),
            "raw_stderr": (
                outcome.raw_stderr.model_dump(mode="json")
                if outcome.raw_stderr is not None
                else None
            ),
            "exit_code": outcome.exit_code,
        }
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)

    def request_cancel(self, session_id: str) -> None:
        self._set_status(session_id, SessionStatus.CANCEL_REQUESTED)

    def settle_cancel(self, session_id: str, *, terminated: bool) -> None:
        self._set_status(
            session_id, SessionStatus.CANCELLED if terminated else SessionStatus.QUIESCING
        )

    def rotate(self, session_id: str) -> None:
        self._set_status(session_id, SessionStatus.ROTATED)

    def _increment(self, session_id: str, column: str) -> None:
        if column not in {"continuation_count", "failure_count"}:
            raise ValueError("invalid Session counter")
        with self.state.transaction() as connection:
            cursor = connection.execute(
                f"UPDATE executor_sessions SET {column} = {column} + 1, updated_at = ? "
                "WHERE session_id = ?",
                (timestamp(), session_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(session_id)

    def _set_status(self, session_id: str, status: SessionStatus) -> None:
        with self.state.transaction() as connection:
            cursor = connection.execute(
                "UPDATE executor_sessions SET status = ?, updated_at = ? WHERE session_id = ?",
                (status.value, timestamp(), session_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(session_id)
