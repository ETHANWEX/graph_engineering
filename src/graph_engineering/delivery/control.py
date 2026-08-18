"""Confirmed append-only Human delivery decisions; no merge capability exists."""

# ruff: noqa: E501

from __future__ import annotations

import uuid
from typing import Literal, cast

from graph_engineering.contracts import ContractDelta, ContractRepository, RunPlanner
from graph_engineering.conversation import ConversationRepository, IntentCompiler
from graph_engineering.models import HumanMessage
from graph_engineering.models.control import StateChangeAction, StateChangeControlIntent
from graph_engineering.runtime.store import StateStore, timestamp

from .models import HumanAcceptanceRecord


class HumanDecisionService:
    def __init__(self, state: StateStore) -> None:
        self.state = state
        state.migrate()
        self.conversations = ConversationRepository(state)

    def accept(self, message: HumanMessage, *, report_revision: int) -> HumanAcceptanceRecord:
        return self._apply(
            message, StateChangeAction.ACCEPT, reason=None, report_revision=report_revision
        )

    def reject(
        self, message: HumanMessage, *, reason: str, report_revision: int
    ) -> HumanAcceptanceRecord:
        if not reason.strip():
            raise ValueError("reject reason is required")
        return self._apply(
            message,
            StateChangeAction.REJECT,
            reason=reason.strip(),
            report_revision=report_revision,
        )

    def revise(
        self, message: HumanMessage, *, reason: str, report_revision: int
    ) -> HumanAcceptanceRecord:
        if not reason.strip():
            raise ValueError("revise reason is required")
        return self._apply(
            message,
            StateChangeAction.REVISE,
            reason=reason.strip(),
            report_revision=report_revision,
        )

    def _apply(
        self,
        message: HumanMessage,
        action: StateChangeAction,
        *,
        reason: str | None,
        report_revision: int,
    ) -> HumanAcceptanceRecord:
        if message.run_id is None:
            raise ValueError("Human delivery decision requires an explicit Run target")
        existing = self._by_message(message.message_id)
        if existing is not None:
            return existing
        conversation_id = f"delivery:{message.project_id}:{message.actor_id}"
        try:
            self.conversations.get(conversation_id)
            self.conversations.set_active_run(conversation_id, message.run_id)
        except KeyError:
            self.conversations.create(
                conversation_id, message.project_id, message.actor_id, active_run_id=message.run_id
            )
        self.conversations.append(conversation_id, message)
        compiled = IntentCompiler().compile(message, active_run_id=message.run_id)
        intent = compiled.intent
        if not isinstance(intent, StateChangeControlIntent) or intent.action is not action:
            raise ValueError("HumanMessage did not compile to the requested typed delivery action")
        if not intent.requires_confirmation or (
            "confirm" not in message.content.casefold() and "确认" not in message.content
        ):
            raise ValueError("explicit Human confirmation is required")
        contract_id, contract_revision = self._contract(message.run_id)
        new_revision: int | None = None
        new_run_id: str | None = None
        if action in {StateChangeAction.REJECT, StateChangeAction.REVISE}:
            new_revision = contract_revision + 1
            with self.state.read_connection() as connection:
                frozen = connection.execute(
                    "SELECT contract_json FROM contract_revisions WHERE contract_id=? AND revision=?",
                    (contract_id, contract_revision),
                ).fetchone()
            if frozen is not None:
                from graph_engineering.models import TaskContract

                source = TaskContract.model_validate_json(str(frozen["contract_json"]))
                delta = ContractDelta(
                    delta_id=f"delta:{message.message_id}",
                    contract_id=contract_id,
                    source_revision=contract_revision,
                    description=reason or "Human revision",
                    replacement_description=f"{source.task.description}\n\nHuman revision: {reason}",
                )
                revised = ContractRepository(self.state).apply_delta(delta, message)
                new_revision = revised.contract.revision
                if action is StateChangeAction.REVISE:
                    planned = RunPlanner(self.state).create(
                        message.project_id,
                        revised,
                        source_run_id=message.run_id,
                        run_id=f"run:{contract_id}:r{new_revision}:{uuid.uuid4().hex[:8]}",
                    )
                    new_run_id = planned.run_id
        decision = cast("Literal['accept', 'reject', 'revise']", action.value)
        record = HumanAcceptanceRecord(
            record_id=f"acceptance:{uuid.uuid4()}",
            source_message_id=message.message_id,
            intent_id=intent.intent_id,
            run_id=message.run_id,
            actor_id=message.actor_id,
            action=decision,
            reason=reason,
            contract_revision=contract_revision,
            report_revision=report_revision,
            new_contract_revision=new_revision,
            new_run_id=new_run_id,
        )
        with self.state.transaction() as connection:
            connection.execute(
                "INSERT INTO human_acceptance_records(record_id, source_message_id, intent_id, run_id, actor_id, action, reason, contract_revision, report_revision, new_contract_revision, new_run_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    record.record_id,
                    record.source_message_id,
                    record.intent_id,
                    record.run_id,
                    record.actor_id,
                    record.action,
                    record.reason,
                    record.contract_revision,
                    record.report_revision,
                    record.new_contract_revision,
                    record.new_run_id,
                    timestamp(),
                ),
            )
            self.state.enqueue_event(
                connection,
                f"human.delivery.{action.value}",
                message.run_id,
                payload={
                    "record_id": record.record_id,
                    "message_id": message.message_id,
                    "contract_revision": contract_revision,
                    "report_revision": report_revision,
                    "new_contract_revision": new_revision,
                    "new_run_id": new_run_id,
                    "merge_performed": False,
                },
            )
        return record

    def history(self, run_id: str) -> list[HumanAcceptanceRecord]:
        with self.state.read_connection() as connection:
            rows = list(
                connection.execute(
                    "SELECT * FROM human_acceptance_records WHERE run_id=? ORDER BY created_at, rowid",
                    (run_id,),
                )
            )
        return [self._record(row) for row in rows]

    def _by_message(self, message_id: str) -> HumanAcceptanceRecord | None:
        with self.state.read_connection() as connection:
            row = connection.execute(
                "SELECT * FROM human_acceptance_records WHERE source_message_id=?", (message_id,)
            ).fetchone()
        return self._record(row) if row is not None else None

    def _contract(self, run_id: str) -> tuple[str, int]:
        with self.state.read_connection() as connection:
            row = connection.execute(
                "SELECT contract_id, contract_revision FROM runs WHERE run_id=?", (run_id,)
            ).fetchone()
            if row is None:
                row = connection.execute(
                    "SELECT contract_id, contract_revision FROM delivery_terminal_fixtures WHERE run_id=?",
                    (run_id,),
                ).fetchone()
        if row is None:
            raise KeyError(run_id)
        return str(row["contract_id"]), int(row["contract_revision"])

    @staticmethod
    def _record(row: object) -> HumanAcceptanceRecord:
        import sqlite3

        assert isinstance(row, sqlite3.Row)
        action = cast("Literal['accept', 'reject', 'revise']", str(row["action"]))
        return HumanAcceptanceRecord(
            record_id=str(row["record_id"]),
            source_message_id=str(row["source_message_id"]),
            intent_id=str(row["intent_id"]),
            run_id=str(row["run_id"]),
            actor_id=str(row["actor_id"]),
            action=action,
            reason=str(row["reason"]) if row["reason"] is not None else None,
            contract_revision=int(row["contract_revision"]),
            report_revision=int(row["report_revision"]),
            new_contract_revision=int(row["new_contract_revision"])
            if row["new_contract_revision"] is not None
            else None,
            new_run_id=str(row["new_run_id"]) if row["new_run_id"] is not None else None,
        )
