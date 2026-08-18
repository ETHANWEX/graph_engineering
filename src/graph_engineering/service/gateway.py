"""Single Human Gateway shared by local IPC and MCP."""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from graph_engineering.control import NaturalLanguageControlService
from graph_engineering.conversation import ConversationRepository, IntentCompiler
from graph_engineering.models import (
    ControlActionResult,
    HumanMessage,
    QueryControlIntent,
    StateChangeControlIntent,
)
from graph_engineering.runtime import FakeExecutor, FakeVerifier, GraphRuntime, StateStore

from .protocol import IPC_VERSION, RUNTIME_API_VERSION, ServiceError, ServiceErrorCode


class HumanGateway:
    def __init__(self, project_root: Path, project_id: str) -> None:
        self.project_root = project_root.resolve()
        self.project_id = project_id
        self.control_root = self.project_root / ".ge" / "control"
        self.state = StateStore(self.control_root / "phase3.db")
        self.conversations = ConversationRepository(self.state)

    def dispatch(self, operation: str, payload: dict[str, Any]) -> dict[str, Any]:
        if operation == "start":
            return self.start(payload)
        if operation == "message":
            return self.message(payload)
        if operation == "confirm":
            return self.confirm(payload)
        if operation == "status":
            return self.status(payload)
        if operation == "report":
            return self.report(payload)
        raise ServiceError(ServiceErrorCode.INVALID_REQUEST, "unsupported gateway operation")

    def start(self, payload: dict[str, Any]) -> dict[str, Any]:
        project_id = self._required(payload, "project_id")
        if project_id != self.project_id:
            raise ServiceError(ServiceErrorCode.IDENTITY_MISMATCH, "project identity mismatch")
        actor_id = self._required(payload, "actor_id")
        conversation_id = str(payload.get("conversation_id") or f"{project_id}-main")
        try:
            conversation = self.conversations.get(conversation_id)
        except KeyError:
            conversation = self.conversations.create(conversation_id, project_id, actor_id)
        if conversation.project_id != project_id or conversation.actor_id != actor_id:
            raise ServiceError(ServiceErrorCode.IDENTITY_MISMATCH, "conversation identity mismatch")
        return {
            "conversation_id": conversation.conversation_id,
            "project_id": conversation.project_id,
            "actor_id": conversation.actor_id,
            "active_run_id": conversation.active_run_id,
        }

    def message(self, payload: dict[str, Any]) -> dict[str, Any]:
        conversation_id = self._required(payload, "conversation_id")
        conversation = self.conversations.get(conversation_id)
        message = self._message(payload, conversation.project_id, conversation.actor_id)
        service = self._control_service()
        result = service.handle(conversation_id, message)
        return result.model_dump(mode="json", exclude_none=True)

    def confirm(self, payload: dict[str, Any]) -> dict[str, Any]:
        conversation_id = self._required(payload, "conversation_id")
        confirmation_id = self._required(payload, "confirmation_id")
        conversation = self.conversations.get(conversation_id)
        message = self._message(payload, conversation.project_id, conversation.actor_id)
        result = self._control_service().confirm(
            conversation_id, confirmation_id, message, protocol_major=1
        )
        return result.model_dump(mode="json", exclude_none=True)

    def status(self, payload: dict[str, Any]) -> dict[str, Any]:
        run_id = self._target_run(payload)
        database = self._run_root(run_id) / "state.db"
        if not database.is_file():
            raise ServiceError(ServiceErrorCode.NOT_FOUND, "Run was not found")
        state = StateStore(database)
        with state.read_connection() as connection:
            row = connection.execute(
                "SELECT run_id,project_id,status,barrier,current_node_id,updated_at "
                "FROM runs WHERE run_id=?",
                (run_id,),
            ).fetchone()
        if row is None:
            raise ServiceError(ServiceErrorCode.NOT_FOUND, "Run was not found")
        if str(row["project_id"]) != self.project_id:
            raise ServiceError(ServiceErrorCode.IDENTITY_MISMATCH, "Run belongs to another project")
        return dict(row)

    def report(self, payload: dict[str, Any]) -> dict[str, Any]:
        run_id = self._target_run(payload)
        database = self._run_root(run_id) / "state.db"
        if not database.is_file():
            raise ServiceError(ServiceErrorCode.NOT_FOUND, "Run was not found")
        state = StateStore(database)
        try:
            with state.read_connection() as connection:
                row = connection.execute(
                    "SELECT manifest_json FROM delivery_report_revisions WHERE run_id=? "
                    "ORDER BY revision DESC LIMIT 1",
                    (run_id,),
                ).fetchone()
        except sqlite3.OperationalError as exc:
            raise ServiceError(ServiceErrorCode.NOT_FOUND, "delivery report was not found") from exc
        if row is None:
            raise ServiceError(ServiceErrorCode.NOT_FOUND, "delivery report was not found")
        value = json.loads(str(row["manifest_json"]))
        if not isinstance(value, dict):
            raise ServiceError(ServiceErrorCode.INTERNAL, "persisted report is invalid")
        return value

    def _control_service(self) -> NaturalLanguageControlService:
        return NaturalLanguageControlService(
            self.conversations,
            IntentCompiler(),
            runtime_resolver=self._runtime,
            observer=lambda _intent: None,
        )

    def _runtime(self, run_id: str) -> _GatewayRuntime:
        return _GatewayRuntime(self._run_root(run_id))

    def _run_root(self, run_id: str) -> Path:
        if not run_id or any(value in run_id for value in ("/", "\\", "..")):
            raise ServiceError(ServiceErrorCode.INVALID_REQUEST, "Run identity is invalid")
        root = (self.project_root / ".ge" / "runs" / run_id).resolve()
        expected = (self.project_root / ".ge" / "runs").resolve()
        if root.parent != expected:
            raise ServiceError(ServiceErrorCode.IDENTITY_MISMATCH, "Run path escaped project")
        return root

    def _target_run(self, payload: dict[str, Any]) -> str:
        if payload.get("run_id"):
            return str(payload["run_id"])
        conversation_id = self._required(payload, "conversation_id")
        run_id = self.conversations.get(conversation_id).active_run_id
        if run_id is None:
            raise ServiceError(ServiceErrorCode.INVALID_REQUEST, "target Run is missing")
        return run_id

    @staticmethod
    def _required(payload: dict[str, Any], name: str) -> str:
        value = payload.get(name)
        if not isinstance(value, str) or not value.strip():
            raise ServiceError(ServiceErrorCode.INVALID_REQUEST, f"{name} is required")
        return value

    def _message(self, payload: dict[str, Any], project_id: str, actor_id: str) -> HumanMessage:
        requested_project = str(payload.get("project_id", project_id))
        requested_actor = str(payload.get("actor_id", actor_id))
        if requested_project != project_id or requested_actor != actor_id:
            raise ServiceError(ServiceErrorCode.IDENTITY_MISMATCH, "message identity mismatch")
        content = self._required(payload, "content")
        return HumanMessage(
            schema_version="1.0",
            message_id=str(payload.get("message_id") or f"message:{uuid.uuid4()}"),
            actor_id=actor_id,
            project_id=project_id,
            run_id=str(payload["run_id"]) if payload.get("run_id") else None,
            content=content,
            created_at=datetime.now(UTC),
        )


def workspace_identity(project_root: Path) -> str:
    import hashlib

    normalized = os.path.normcase(str(project_root.resolve())).encode("utf-8")
    return hashlib.sha256(normalized).hexdigest()


def gateway_versions() -> dict[str, str]:
    return {"package": "0.7.0", "runtime_api": RUNTIME_API_VERSION, "ipc": IPC_VERSION}


class _ReadOnlyExecutionSnapshot:
    def __init__(self, fingerprint: tuple[object, ...]) -> None:
        self._fingerprint = fingerprint

    def execution_fingerprint(self) -> tuple[object, ...]:
        return self._fingerprint


class _GatewayRuntime:
    """Avoid Runtime initialization writes on the query path."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.state = StateStore(root / "state.db")

    def snapshot(self, run_id: str) -> _ReadOnlyExecutionSnapshot:
        with self.state.read_connection() as connection:
            run = connection.execute(
                "SELECT status,barrier,current_node_id,terminal_reason,error_json,"
                "unverified_json,external_effects_json FROM runs WHERE run_id=?",
                (run_id,),
            ).fetchone()
            if run is None:
                raise KeyError(run_id)
            nodes = tuple(
                tuple(row)
                for row in connection.execute(
                    "SELECT node_id,status,attempt_count,result_json,route_resolved FROM nodes "
                    "WHERE run_id=? ORDER BY node_id",
                    (run_id,),
                )
            )
            attempts = tuple(
                tuple(row)
                for row in connection.execute(
                    "SELECT attempt_id,status,result_json,finished_at FROM attempts "
                    "WHERE run_id=? ORDER BY attempt_id",
                    (run_id,),
                )
            )
        return _ReadOnlyExecutionSnapshot((tuple(run), nodes, attempts))

    def control(self, intent: QueryControlIntent | StateChangeControlIntent) -> ControlActionResult:
        runtime = GraphRuntime(self.root, executor=FakeExecutor(), verifier=FakeVerifier())
        return runtime.control(intent)
