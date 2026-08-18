"""SQLite persistence for recoverable Discovery sessions."""

from __future__ import annotations

import json

from graph_engineering.runtime.store import StateStore, timestamp

from .models import DiscoverySession


class DiscoveryRepository:
    def __init__(self, state: StateStore) -> None:
        self.state = state
        self.state.migrate()

    def save(self, session: DiscoverySession) -> None:
        now = timestamp()
        with self.state.transaction() as connection:
            connection.execute(
                """
                INSERT INTO discovery_sessions(
                    session_id, conversation_id, project_root, state, scan_json,
                    unknowns_json, answers_json, draft_json, source_message_id,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    state = excluded.state,
                    scan_json = excluded.scan_json,
                    unknowns_json = excluded.unknowns_json,
                    answers_json = excluded.answers_json,
                    draft_json = excluded.draft_json,
                    updated_at = excluded.updated_at
                """,
                (
                    session.session_id,
                    session.conversation_id,
                    session.project_root,
                    session.state.value,
                    session.scan.model_dump_json(),
                    json.dumps(
                        [item.model_dump(mode="json") for item in session.unknowns],
                        ensure_ascii=False,
                        separators=(",", ":"),
                        sort_keys=True,
                    ),
                    json.dumps(
                        session.answers, ensure_ascii=False, separators=(",", ":"), sort_keys=True
                    ),
                    session.draft.canonical_json() if session.draft is not None else None,
                    session.source_message_id,
                    now,
                    now,
                ),
            )
            self.state.enqueue_event(
                connection,
                "discovery.checkpointed",
                f"conversation:{session.conversation_id}",
                payload={"session_id": session.session_id, "state": session.state.value},
            )

    def get(self, session_id: str) -> DiscoverySession:
        with self.state.read_connection() as connection:
            row = connection.execute(
                "SELECT * FROM discovery_sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
        if row is None:
            raise KeyError(session_id)
        scan = json.loads(str(row["scan_json"]))
        unknowns = json.loads(str(row["unknowns_json"]))
        answers = json.loads(str(row["answers_json"]))
        draft = json.loads(str(row["draft_json"])) if row["draft_json"] is not None else None
        return DiscoverySession.model_validate(
            {
                "session_id": row["session_id"],
                "conversation_id": row["conversation_id"],
                "source_message_id": row["source_message_id"],
                "initial_request": answers.pop("__initial_request"),
                "project_root": row["project_root"],
                "state": row["state"],
                "scan": scan,
                "unknowns": unknowns,
                "answers": answers,
                "draft": draft,
            }
        )

    def latest_for_conversation(self, conversation_id: str) -> DiscoverySession | None:
        with self.state.read_connection() as connection:
            row = connection.execute(
                "SELECT session_id FROM discovery_sessions WHERE conversation_id = ? "
                "ORDER BY created_at DESC, rowid DESC LIMIT 1",
                (conversation_id,),
            ).fetchone()
        return self.get(str(row["session_id"])) if row is not None else None
