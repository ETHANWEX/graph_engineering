"""Append-only HumanMessage persistence for project conversations."""

from __future__ import annotations

import json
from dataclasses import dataclass

from graph_engineering.models import HumanMessage
from graph_engineering.runtime.store import StateStore, timestamp


@dataclass(frozen=True)
class ConversationRecord:
    conversation_id: str
    project_id: str
    actor_id: str
    active_run_id: str | None
    status: str


class ConversationRepository:
    def __init__(self, state: StateStore) -> None:
        self.state = state
        self.state.migrate()

    def create(
        self,
        conversation_id: str,
        project_id: str,
        actor_id: str,
        *,
        active_run_id: str | None = None,
    ) -> ConversationRecord:
        if not all(value.strip() for value in (conversation_id, project_id, actor_id)):
            raise ValueError("conversation, project, and actor IDs must not be empty")
        now = timestamp()
        with self.state.transaction() as connection:
            connection.execute(
                "INSERT INTO conversations(conversation_id, project_id, actor_id, active_run_id, "
                "status, created_at, updated_at) VALUES (?, ?, ?, ?, 'active', ?, ?)",
                (conversation_id, project_id, actor_id, active_run_id, now, now),
            )
            self.state.enqueue_event(
                connection,
                "conversation.created",
                active_run_id or f"conversation:{conversation_id}",
                payload={"conversation_id": conversation_id, "project_id": project_id},
            )
        return self.get(conversation_id)

    def get(self, conversation_id: str) -> ConversationRecord:
        with self.state.read_connection() as connection:
            row = connection.execute(
                "SELECT * FROM conversations WHERE conversation_id = ?", (conversation_id,)
            ).fetchone()
        if row is None:
            raise KeyError(conversation_id)
        return ConversationRecord(
            conversation_id=str(row["conversation_id"]),
            project_id=str(row["project_id"]),
            actor_id=str(row["actor_id"]),
            active_run_id=(str(row["active_run_id"]) if row["active_run_id"] is not None else None),
            status=str(row["status"]),
        )

    def set_active_run(self, conversation_id: str, run_id: str | None) -> None:
        with self.state.transaction() as connection:
            cursor = connection.execute(
                "UPDATE conversations SET active_run_id = ?, updated_at = ? "
                "WHERE conversation_id = ?",
                (run_id, timestamp(), conversation_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(conversation_id)

    def append(self, conversation_id: str, message: HumanMessage) -> HumanMessage:
        conversation = self.get(conversation_id)
        if (
            message.project_id != conversation.project_id
            or message.actor_id != conversation.actor_id
        ):
            raise ValueError("HumanMessage actor/project does not match the Conversation")
        document = message.canonical_json()
        with self.state.transaction() as connection:
            existing = connection.execute(
                "SELECT message_json FROM human_messages WHERE message_id = ?",
                (message.message_id,),
            ).fetchone()
            if existing is not None:
                if str(existing["message_json"]) != document:
                    raise ValueError("HumanMessage ID collision")
                return message
            connection.execute(
                "INSERT INTO human_messages(message_id, conversation_id, message_json, created_at) "
                "VALUES (?, ?, ?, ?)",
                (message.message_id, conversation_id, document, message.created_at.isoformat()),
            )
            connection.execute(
                "UPDATE conversations SET updated_at = ? WHERE conversation_id = ?",
                (timestamp(), conversation_id),
            )
            self.state.enqueue_event(
                connection,
                "human.message.received",
                message.run_id or f"conversation:{conversation_id}",
                payload={
                    "conversation_id": conversation_id,
                    "message_id": message.message_id,
                    "actor_id": message.actor_id,
                },
            )
        return message

    def messages(self, conversation_id: str) -> list[HumanMessage]:
        with self.state.read_connection() as connection:
            rows = list(
                connection.execute(
                    "SELECT message_json FROM human_messages WHERE conversation_id = ? "
                    "ORDER BY created_at, rowid",
                    (conversation_id,),
                )
            )
        return [HumanMessage.model_validate(json.loads(str(row["message_json"]))) for row in rows]
