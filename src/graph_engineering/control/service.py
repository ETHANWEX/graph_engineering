"""Persist-first natural-language control with confirmation and query isolation."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from graph_engineering.conversation import ConversationRepository, IntentCompiler
from graph_engineering.models import (
    ControlActionResult,
    HumanMessage,
    QueryControlIntent,
    StateChangeControlIntent,
)
from graph_engineering.runtime.store import timestamp


class ExecutionSnapshot(Protocol):
    def execution_fingerprint(self) -> tuple[object, ...]: ...


class RuntimeControl(Protocol):
    def control(
        self, intent: QueryControlIntent | StateChangeControlIntent
    ) -> ControlActionResult: ...

    def snapshot(self, run_id: str) -> ExecutionSnapshot: ...


class ControlServiceResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    applied: bool
    message: str
    intent_id: str | None = None
    pending_confirmation_id: str | None = None
    action_result: ControlActionResult | None = None


class NaturalLanguageControlService:
    def __init__(
        self,
        conversations: ConversationRepository,
        compiler: IntentCompiler,
        *,
        runtime_resolver: Callable[[str], RuntimeControl],
        observer: Callable[[QueryControlIntent], object] | None = None,
        confirmation_ttl: timedelta = timedelta(minutes=15),
    ) -> None:
        self.conversations = conversations
        self.compiler = compiler
        self.runtime_resolver = runtime_resolver
        self.observer = observer
        self.confirmation_ttl = confirmation_ttl

    def handle(self, conversation_id: str, message: HumanMessage) -> ControlServiceResult:
        # The durable HumanMessage boundary deliberately precedes all interpretation and effects.
        self.conversations.append(conversation_id, message)
        conversation = self.conversations.get(conversation_id)
        compiled = self.compiler.compile(message, active_run_id=conversation.active_run_id)
        self._record_compilation(conversation_id, message.message_id, compiled)
        if compiled.intent is None:
            return ControlServiceResult(
                applied=False, message=compiled.clarification or "ambiguous"
            )
        intent = compiled.intent
        if isinstance(intent, StateChangeControlIntent) and intent.requires_confirmation:
            confirmation_id = f"confirmation:{intent.intent_id}"
            with self.conversations.state.transaction() as connection:
                connection.execute(
                    "INSERT OR IGNORE INTO pending_confirmations("
                    "confirmation_id, conversation_id, intent_json, status, created_at, actor_id, "
                    "project_id, protocol_major, expires_at) "
                    "VALUES (?, ?, ?, 'pending', ?, ?, ?, 1, ?)",
                    (
                        confirmation_id,
                        conversation_id,
                        intent.canonical_json(),
                        timestamp(),
                        message.actor_id,
                        message.project_id,
                        (datetime.now(UTC) + self.confirmation_ttl).isoformat(),
                    ),
                )
                self.conversations.state.enqueue_event(
                    connection,
                    "control.confirmation.requested",
                    intent.run_id,
                    payload={"confirmation_id": confirmation_id, "intent_id": intent.intent_id},
                )
            return ControlServiceResult(
                applied=False,
                message="Explicit confirmation is required before applying this action.",
                intent_id=intent.intent_id,
                pending_confirmation_id=confirmation_id,
            )
        return self._apply(intent)

    def confirm(
        self,
        conversation_id: str,
        confirmation_id: str,
        message: HumanMessage,
        *,
        protocol_major: int = 1,
    ) -> ControlServiceResult:
        self.conversations.append(conversation_id, message)
        if not any(token in message.content.casefold() for token in ("confirm", "确认", "同意")):
            return ControlServiceResult(applied=False, message="Explicit confirmation was absent.")
        with self.conversations.state.read_connection() as connection:
            row = connection.execute(
                "SELECT * FROM pending_confirmations WHERE confirmation_id = ? "
                "AND conversation_id = ?",
                (confirmation_id, conversation_id),
            ).fetchone()
        if row is None:
            raise KeyError(confirmation_id)
        if row["actor_id"] is not None and str(row["actor_id"]) != message.actor_id:
            raise PermissionError("pending confirmation belongs to another actor")
        if row["project_id"] is not None and str(row["project_id"]) != message.project_id:
            raise PermissionError("pending confirmation belongs to another project")
        if int(row["protocol_major"]) != protocol_major:
            raise ValueError("pending confirmation protocol is incompatible")
        if row["expires_at"] is not None:
            expires_at = datetime.fromisoformat(str(row["expires_at"]).replace("Z", "+00:00"))
            if expires_at <= datetime.now(UTC):
                raise TimeoutError("pending confirmation has expired")
        if str(row["status"]) == "applied" and row["result_json"] is not None:
            return ControlServiceResult.model_validate_json(str(row["result_json"]))
        intent = StateChangeControlIntent.model_validate_json(str(row["intent_json"]))
        result = self._apply(intent)
        with self.conversations.state.transaction() as connection:
            connection.execute(
                "UPDATE pending_confirmations SET status = 'applied', result_json = ?, "
                "resolved_at = ? WHERE confirmation_id = ? AND status = 'pending'",
                (result.model_dump_json(), timestamp(), confirmation_id),
            )
            self.conversations.state.enqueue_event(
                connection,
                "control.confirmation.applied",
                intent.run_id,
                payload={
                    "confirmation_id": confirmation_id,
                    "confirmation_message_id": message.message_id,
                },
            )
        return result

    def _apply(self, intent: QueryControlIntent | StateChangeControlIntent) -> ControlServiceResult:
        runtime = self.runtime_resolver(intent.run_id)
        if isinstance(intent, QueryControlIntent) and self.observer is not None:
            before = runtime.snapshot(intent.run_id)
            before_fingerprint = before.execution_fingerprint()
            self.observer(intent)
            after = runtime.snapshot(intent.run_id)
            if after.execution_fingerprint() != before_fingerprint:
                raise RuntimeError("read-only Observer changed the main Run")
            return ControlServiceResult(
                applied=True,
                message="Read-only Observer completed without execution-state changes.",
                intent_id=intent.intent_id,
            )
        action_result = runtime.control(intent)
        return ControlServiceResult(
            applied=action_result.outcome.value == "applied",
            message=action_result.message,
            intent_id=intent.intent_id,
            action_result=action_result,
        )

    def _record_compilation(
        self, conversation_id: str, source_message_id: str, compiled: object
    ) -> None:
        from graph_engineering.conversation.compiler import IntentCompilation

        if not isinstance(compiled, IntentCompilation):
            raise TypeError("compiled value must be IntentCompilation")
        intent = compiled.intent
        compilation_id = f"compilation:{source_message_id}"
        with self.conversations.state.transaction() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO intent_compilations("
                "compilation_id, conversation_id, source_message_id, intent_json, confidence, "
                "clarification, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    compilation_id,
                    conversation_id,
                    source_message_id,
                    intent.canonical_json() if intent is not None else None,
                    compiled.confidence,
                    compiled.clarification,
                    "compiled" if intent is not None else "clarification_required",
                    timestamp(),
                ),
            )
            self.conversations.state.enqueue_event(
                connection,
                "control.intent.compiled",
                intent.run_id if intent is not None else f"conversation:{conversation_id}",
                payload={
                    "compilation_id": compilation_id,
                    "intent_id": intent.intent_id if intent is not None else None,
                    "confidence": compiled.confidence,
                },
            )
