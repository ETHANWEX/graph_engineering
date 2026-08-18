"""Deterministic single-run, serial Phase 1 Graph Runtime."""

from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol, cast

from graph_engineering.models.common import (
    Artifact,
    ArtifactKind,
    Budget,
    ContractRef,
    Error,
    ErrorKind,
    RestartFrom,
    RestartStrategy,
    RunRelationship,
)
from graph_engineering.models.control import (
    ControlActionResult,
    ControlOutcome,
    QueryControlIntent,
    StateChangeAction,
    StateChangeControlIntent,
)
from graph_engineering.models.graph import (
    Edge,
    ExecutionGraph,
    Node,
    NodeType,
    RouteField,
    RouteOperator,
)
from graph_engineering.models.reports import (
    BudgetUsage,
    ExternalEffect,
    FinalReport,
    LiveReport,
    RunStatus,
    TerminalReason,
    TerminalStatus,
    UnverifiedItem,
)
from graph_engineering.models.results import (
    ExecutorResult,
    ExecutorStatus,
    VerifierResult,
    VerifierStatus,
)

from .artifacts import ArtifactStore
from .errors import RecoveryError, RuntimeInvariantError
from .events import EventStore
from .fakes import FakeExecutor
from .store import StateStore, timestamp, utc_now
from .types import RunSnapshot

Result = ExecutorResult | VerifierResult

_TERMINAL_VALUES = {status.value for status in TerminalStatus}


class _BudgetExhausted(RuntimeError):
    pass


class RuntimeVerifier(Protocol):
    def execute(
        self,
        run_id: str,
        node: Node,
        attempt_id: str,
        *,
        idempotency_key: str | None = None,
    ) -> VerifierResult: ...

    def query(self, handle: str) -> VerifierResult: ...


class GraphRuntime:
    """A synchronous serial scheduler around deterministic Fake boundaries."""

    def __init__(
        self,
        root: Path,
        *,
        executor: FakeExecutor,
        verifier: RuntimeVerifier,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.state = StateStore(root / "state.db")
        self.state.migrate()
        self.events = EventStore(root / "events.jsonl")
        self.artifacts = ArtifactStore(root / "artifacts")
        self.executor = executor
        self.verifier = verifier
        self.clock = clock
        self._graphs: dict[str, ExecutionGraph] = {}
        self.events.flush(self.state)

    def create_run(
        self,
        run_id: str,
        project_id: str,
        graph: ExecutionGraph,
        contract_hash: str,
        budget: Budget,
        relationship: RunRelationship | None = None,
        restart_from: RestartFrom | None = None,
    ) -> None:
        relationship = relationship or RunRelationship(schema_version="1.0", run_id=run_id)
        if relationship.run_id != run_id:
            raise ValueError("RunRelationship.run_id must equal run_id")
        now = self._timestamp()
        with self.state.transaction() as connection:
            checkpoint_state = self._validate_run_lineage(
                connection,
                graph,
                contract_hash,
                relationship,
                restart_from,
            )
            connection.execute(
                """
                INSERT INTO runs(
                    run_id, project_id, contract_id, contract_revision, contract_hash,
                    graph_id, graph_hash, graph_json, status, barrier, current_node_id,
                    parent_run_id, supersedes_run_id, restart_from_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    project_id,
                    graph.contract.contract_id,
                    graph.contract.revision,
                    contract_hash,
                    graph.graph_id,
                    graph.sha256(),
                    graph.canonical_json(),
                    RunStatus.RUNNING.value,
                    (
                        str(checkpoint_state["current_node_id"])
                        if checkpoint_state is not None
                        and checkpoint_state.get("current_node_id") is not None
                        else graph.entry_node_id
                    ),
                    relationship.parent_run_id,
                    relationship.supersedes_run_id,
                    restart_from.canonical_json() if restart_from is not None else None,
                    now,
                    now,
                ),
            )
            inherited_nodes = {
                str(item["node_id"]): item
                for item in cast(list[dict[str, Any]], (checkpoint_state or {}).get("nodes", []))
            }
            for node in graph.nodes:
                inherited = inherited_nodes.get(node.node_id)
                if inherited is None:
                    node_status = "ready" if node.node_id == graph.entry_node_id else "pending"
                    attempt_count = 0
                    result_json = None
                    route_resolved = 0
                else:
                    inherited_status = str(inherited["status"])
                    node_status = "ready" if inherited_status == "running" else inherited_status
                    attempt_count = int(inherited["attempt_count"])
                    result_json = cast(str | None, inherited.get("result_json"))
                    route_resolved = int(inherited["route_resolved"])
                connection.execute(
                    """
                    INSERT INTO nodes(
                        run_id, node_id, node_type, status, attempt_count,
                        result_json, route_resolved
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        node.node_id,
                        node.node_type.value,
                        node_status,
                        attempt_count,
                        result_json,
                        route_resolved,
                    ),
                )
            connection.execute(
                """
                INSERT INTO budgets(
                    run_id, max_duration_seconds, max_executor_calls,
                    max_repair_iterations, max_cost_units, cost_units, started_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    budget.max_duration_seconds,
                    budget.max_executor_calls,
                    budget.max_repair_iterations,
                    budget.max_cost_units,
                    0.0 if budget.max_cost_units is not None else None,
                    now,
                ),
            )
            if checkpoint_state is not None:
                for edge in cast(list[dict[str, Any]], checkpoint_state.get("edges", [])):
                    connection.execute(
                        """
                        INSERT INTO edge_traversals(
                            run_id, from_node, to_node, traversal_count
                        ) VALUES (?, ?, ?, ?)
                        """,
                        (
                            run_id,
                            str(edge["from_node"]),
                            str(edge["to_node"]),
                            int(edge["traversal_count"]),
                        ),
                    )
                source_run_id = str(checkpoint_state["run_id"])
                for artifact in cast(list[dict[str, Any]], checkpoint_state.get("artifacts", [])):
                    connection.execute(
                        """
                        INSERT OR IGNORE INTO run_artifacts(
                            run_id, artifact_id, node_id, role, inherited_from_run_id
                        ) VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            run_id,
                            str(artifact["artifact_id"]),
                            str(artifact["node_id"]),
                            str(artifact["role"]),
                            source_run_id,
                        ),
                    )
            self._checkpoint(connection, run_id, "run_created")
            self.state.enqueue_event(
                connection,
                "run.created",
                run_id,
                payload={
                    "graph_hash": graph.sha256(),
                    "contract_hash": contract_hash,
                    "parent_run_id": relationship.parent_run_id,
                    "supersedes_run_id": relationship.supersedes_run_id,
                    "restart_from": (
                        restart_from.model_dump(mode="json") if restart_from is not None else None
                    ),
                },
            )
        self._graphs[run_id] = graph
        self.events.flush(self.state)

    def recover(self, run_id: str, graph: ExecutionGraph, contract_hash: str) -> None:
        with self.state.read_connection() as connection:
            run = self._required_run(connection, run_id)
            if str(run["contract_hash"]) != contract_hash:
                raise RecoveryError("Contract hash mismatch; refusing recovery")
            if str(run["graph_hash"]) != graph.sha256():
                raise RecoveryError("Graph hash mismatch; refusing recovery")
            uncertain = connection.execute(
                "SELECT node_id FROM external_handles "
                "WHERE run_id = ? AND trigger_state = 'triggering' AND handle IS NULL",
                (run_id,),
            ).fetchone()
            local_running = connection.execute(
                """
                SELECT n.node_id FROM nodes n
                LEFT JOIN external_handles h
                  ON h.run_id = n.run_id AND h.node_id = n.node_id
                WHERE n.run_id = ? AND n.status = 'running' AND h.handle IS NULL
                """,
                (run_id,),
            ).fetchone()
        self._graphs[run_id] = graph
        self.events.flush(self.state)
        if uncertain is not None or local_running is not None:
            node_id = str((uncertain or local_running)["node_id"])
            self._finish_uncertain_external_effect(run_id, node_id)

    def run(self, run_id: str, *, max_steps: int | None = None) -> TerminalStatus | RunStatus:
        graph = self._graph(run_id)
        steps = 0
        while max_steps is None or steps < max_steps:
            status = self._run_status(run_id)
            if status.value in _TERMINAL_VALUES:
                return TerminalStatus(status.value)
            if status is RunStatus.PAUSED:
                return status
            if status in {RunStatus.PAUSE_REQUESTED, RunStatus.QUIESCING}:
                self._pause_at_safe_point(run_id)
                return RunStatus.PAUSED
            if self._barrier(run_id) == StateChangeAction.INTERRUPT.value:
                self._finish(run_id, TerminalStatus.INTERRUPTED, TerminalReason.HUMAN_INTERRUPTED)
                return TerminalStatus.INTERRUPTED
            if self._budget_limit_reached(run_id):
                self._finish(run_id, TerminalStatus.FAILED, TerminalReason.BUDGET_EXHAUSTED)
                return TerminalStatus.FAILED

            node_row = self._next_node_row(run_id)
            if node_row is None:
                unresolved = self._unresolved_result_row(run_id)
                if unresolved is not None:
                    self._route_result(run_id, graph, str(unresolved["node_id"]))
                    continue
                raise RuntimeInvariantError("running Run has no schedulable or unresolved node")

            node_id = str(node_row["node_id"])
            node = self._node(graph, node_id)
            if str(node_row["status"]) == "running":
                self._continue_external(run_id, node)
                steps += 1
                continue

            try:
                attempt_id = self._start_attempt(run_id, node)
            except _BudgetExhausted:
                self._finish(run_id, TerminalStatus.FAILED, TerminalReason.BUDGET_EXHAUSTED)
                return TerminalStatus.FAILED
            result = self._invoke(run_id, node, attempt_id)
            steps += 1
            if result is not None:
                self._persist_result(run_id, node, attempt_id, result)
                if isinstance(result, VerifierResult) and result.status is VerifierStatus.PENDING:
                    continue
                self._honor_barrier_after_result(run_id)
                post_result_status = self._run_status(run_id)
                if post_result_status is RunStatus.PAUSED:
                    return post_result_status
                if post_result_status.value in _TERMINAL_VALUES:
                    return TerminalStatus(post_result_status.value)
                if self._budget_limit_reached(run_id, node):
                    self._finish(run_id, TerminalStatus.FAILED, TerminalReason.BUDGET_EXHAUSTED)
                    return TerminalStatus.FAILED
                self._route_result(run_id, graph, node.node_id)

        return self._run_status(run_id)

    def cancel(self, run_id: str) -> None:
        self._finish(run_id, TerminalStatus.CANCELLED, TerminalReason.HUMAN_CANCELLED)

    def charge_cost(self, run_id: str, cost_units: float, *, node_id: str | None = None) -> None:
        if cost_units <= 0:
            raise ValueError("cost_units must be positive")
        graph = self._graph(run_id)
        node = self._node(graph, node_id) if node_id is not None else None
        with self.state.transaction() as connection:
            run = self._required_run(connection, run_id)
            if str(run["status"]) in _TERMINAL_VALUES:
                raise RuntimeInvariantError("cannot charge cost to a terminal Run")
            connection.execute(
                "UPDATE budgets SET cost_units = COALESCE(cost_units, 0) + ? WHERE run_id = ?",
                (cost_units, run_id),
            )
            if node is not None:
                connection.execute(
                    "UPDATE nodes SET cost_units = cost_units + ? WHERE run_id = ? AND node_id = ?",
                    (cost_units, run_id, node.node_id),
                )
            self._checkpoint(connection, run_id, "cost_charged")
            self.state.enqueue_event(
                connection,
                "budget.updated",
                run_id,
                node_id=node_id,
                payload={"cost_units": cost_units},
            )
        self.events.flush(self.state)
        if self._budget_limit_reached(run_id, node, cost_check_after_charge=True):
            self._finish(run_id, TerminalStatus.FAILED, TerminalReason.BUDGET_EXHAUSTED)

    def store_artifact(
        self,
        run_id: str,
        content: bytes,
        *,
        media_type: str | None = None,
        kind: ArtifactKind = ArtifactKind.EVIDENCE,
    ) -> Artifact:
        artifact = self.artifacts.put_bytes(content, media_type=media_type, kind=kind)
        with self.state.transaction() as connection:
            self._required_run(connection, run_id)
            self._register_artifact(connection, run_id, "", "runtime", artifact)
            self._checkpoint(connection, run_id, "artifact_registered")
        self.events.flush(self.state)
        return artifact

    def latest_checkpoint(self, run_id: str) -> str:
        with self.state.read_connection() as connection:
            self._required_run(connection, run_id)
            row = connection.execute(
                "SELECT checkpoint_ref FROM checkpoints WHERE run_id = ? "
                "ORDER BY checkpoint_id DESC LIMIT 1",
                (run_id,),
            ).fetchone()
        if row is None or row["checkpoint_ref"] is None:
            raise RuntimeInvariantError("Run has no checkpoint")
        return str(row["checkpoint_ref"])

    def control(self, intent: QueryControlIntent | StateChangeControlIntent) -> ControlActionResult:
        if isinstance(intent, QueryControlIntent):
            self.snapshot(intent.run_id)
            self._record_control(intent, ControlOutcome.APPLIED)
            result = ControlActionResult(
                schema_version="1.0",
                intent_id=intent.intent_id,
                outcome=ControlOutcome.APPLIED,
                state_changed=False,
                resulting_run_status=self._run_status(intent.run_id).value,
                message="read-only snapshot generated",
            )
            self.events.flush(self.state)
            return result

        changed = False
        outcome = ControlOutcome.APPLIED
        message = "control applied"
        with self.state.transaction() as connection:
            run = self._required_run(connection, intent.run_id)
            current = RunStatus(str(run["status"]))
            if intent.action is StateChangeAction.PAUSE and current is RunStatus.RUNNING:
                connection.execute(
                    "UPDATE runs SET status = ?, barrier = ?, updated_at = ? WHERE run_id = ?",
                    (
                        RunStatus.PAUSE_REQUESTED.value,
                        StateChangeAction.PAUSE.value,
                        timestamp(),
                        intent.run_id,
                    ),
                )
                changed = True
                event_type = "run.pause_requested"
            elif intent.action is StateChangeAction.RESUME and current is RunStatus.PAUSED:
                connection.execute(
                    "UPDATE runs SET status = ?, barrier = NULL, updated_at = ? WHERE run_id = ?",
                    (RunStatus.RUNNING.value, timestamp(), intent.run_id),
                )
                changed = True
                event_type = "run.resumed"
            elif intent.action is StateChangeAction.INTERRUPT and current in {
                RunStatus.RUNNING,
                RunStatus.PAUSE_REQUESTED,
                RunStatus.PAUSED,
            }:
                connection.execute(
                    "UPDATE runs SET status = ?, barrier = ?, updated_at = ? WHERE run_id = ?",
                    (
                        RunStatus.QUIESCING.value,
                        StateChangeAction.INTERRUPT.value,
                        timestamp(),
                        intent.run_id,
                    ),
                )
                changed = True
                event_type = "run.interrupt_requested"
            else:
                outcome = ControlOutcome.REJECTED
                message = f"{intent.action.value} is invalid from {current.value}"
                event_type = "control.action.rejected"
            connection.execute(
                """
                INSERT INTO control_intents(
                    intent_id, run_id, intent_kind, action, intent_json, outcome, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    intent.intent_id,
                    intent.run_id,
                    intent.intent_kind,
                    intent.action.value,
                    intent.model_dump_json(exclude_none=True),
                    outcome.value,
                    timestamp(),
                ),
            )
            self._checkpoint(connection, intent.run_id, f"control:{intent.action.value}")
            self.state.enqueue_event(
                connection,
                event_type,
                intent.run_id,
                payload={"intent_id": intent.intent_id},
            )
        self.events.flush(self.state)
        if (
            isinstance(intent, StateChangeControlIntent)
            and intent.action is StateChangeAction.INTERRUPT
            and changed
        ):
            self._cancel_external_handles(intent.run_id)
        return ControlActionResult(
            schema_version="1.0",
            intent_id=intent.intent_id,
            outcome=outcome,
            state_changed=changed,
            resulting_run_status=self._run_status(intent.run_id).value,
            message=message,
        )

    def _cancel_external_handles(self, run_id: str) -> None:
        with self.state.read_connection() as connection:
            rows = list(
                connection.execute(
                    "SELECT node_id, handle, verifier_id, verifier_revision "
                    "FROM external_handles WHERE run_id = ? "
                    "AND handle IS NOT NULL AND trigger_state = 'checkpointed'",
                    (run_id,),
                )
            )
        cancel = getattr(self.verifier, "cancel", None)
        cancel_for = getattr(self.verifier, "cancel_for", None)
        for row in rows:
            handle = str(row["handle"])
            cancel_state = "unsupported"
            residual: str | None = (
                "external handle cancellation is unsupported; effect may continue"
            )
            if callable(cancel_for) and row["verifier_id"] is not None:
                try:
                    outcome = cancel_for(
                        str(row["verifier_id"]),
                        int(row["verifier_revision"]),
                        handle,
                    )
                    result = outcome.result if hasattr(outcome, "result") else outcome
                    if (
                        isinstance(result, VerifierResult)
                        and result.status is VerifierStatus.CANCELLED
                    ):
                        cancel_state = "cancelled"
                        residual = None
                    else:
                        cancel_state = "unknown"
                        residual = (
                            "external handle cancellation result is unknown; effect may continue"
                        )
                except Exception:
                    cancel_state = "unknown"
                    residual = "external handle cancellation raised an error; effect may continue"
            elif callable(cancel):
                try:
                    outcome = cancel(handle)
                    result = outcome.result if hasattr(outcome, "result") else outcome
                    if (
                        isinstance(result, VerifierResult)
                        and result.status is VerifierStatus.CANCELLED
                    ):
                        cancel_state = "cancelled"
                        residual = None
                    else:
                        cancel_state = "unknown"
                        residual = (
                            "external handle cancellation result is unknown; effect may continue"
                        )
                except Exception:
                    cancel_state = "unknown"
                    residual = "external handle cancellation raised an error; effect may continue"
            with self.state.transaction() as connection:
                connection.execute(
                    "UPDATE external_handles SET cancel_state = ?, residual_effect = ?, "
                    "updated_at = ? WHERE run_id = ? AND node_id = ?",
                    (cancel_state, residual, timestamp(), run_id, str(row["node_id"])),
                )
                self._checkpoint(connection, run_id, "external_handle_cancelled")
                self.state.enqueue_event(
                    connection,
                    "verifier.cancelled"
                    if cancel_state == "cancelled"
                    else "verifier.cancel_unknown",
                    run_id,
                    node_id=str(row["node_id"]),
                    payload={"cancel_state": cancel_state, "residual_effect": residual},
                )
        self.events.flush(self.state)

    def snapshot(self, run_id: str) -> RunSnapshot:
        with self.state.read_connection() as connection:
            run = self._required_run(connection, run_id)
            nodes = list(
                connection.execute(
                    "SELECT node_id, status, attempt_count FROM nodes "
                    "WHERE run_id = ? ORDER BY node_id",
                    (run_id,),
                )
            )
            attempts = list(
                connection.execute(
                    "SELECT DISTINCT node_id FROM attempts WHERE run_id = ? ORDER BY node_id",
                    (run_id,),
                )
            )
            edges = list(
                connection.execute(
                    "SELECT from_node, to_node, traversal_count FROM edge_traversals "
                    "WHERE run_id = ? ORDER BY from_node, to_node",
                    (run_id,),
                )
            )
            budget_row = connection.execute(
                "SELECT * FROM budgets WHERE run_id = ?", (run_id,)
            ).fetchone()
            if budget_row is None:
                raise RuntimeInvariantError("budget row is missing")
        configured_budget = Budget(
            schema_version="1.0",
            max_duration_seconds=int(budget_row["max_duration_seconds"]),
            max_executor_calls=int(budget_row["max_executor_calls"]),
            max_repair_iterations=int(budget_row["max_repair_iterations"]),
            max_cost_units=(
                float(budget_row["max_cost_units"])
                if budget_row["max_cost_units"] is not None
                else None
            ),
        )
        usage = BudgetUsage(
            schema_version="1.0",
            duration_seconds=max(
                0,
                int(
                    (
                        self.clock() - self._parse_timestamp(str(budget_row["started_at"]))
                    ).total_seconds()
                ),
            ),
            executor_calls=int(budget_row["executor_calls"]),
            repair_iterations=int(budget_row["repair_iterations"]),
            cost_units=(
                float(budget_row["cost_units"]) if budget_row["cost_units"] is not None else None
            ),
        )
        relationship = RunRelationship(
            schema_version="1.0",
            run_id=run_id,
            parent_run_id=cast(str | None, run["parent_run_id"]),
            supersedes_run_id=cast(str | None, run["supersedes_run_id"]),
        )
        restart_json = cast(str | None, run["restart_from_json"])
        restart = RestartFrom.model_validate_json(restart_json) if restart_json else None
        return RunSnapshot(
            run_id=run_id,
            run_status=RunStatus(str(run["status"])),
            barrier=cast(str | None, run["barrier"]),
            current_node_id=cast(str | None, run["current_node_id"]),
            node_states=tuple(
                (str(row["node_id"]), str(row["status"]), int(row["attempt_count"]))
                for row in nodes
            ),
            started_node_ids=tuple(str(row["node_id"]) for row in attempts),
            edge_traversals=tuple(
                (str(row["from_node"]), str(row["to_node"]), int(row["traversal_count"]))
                for row in edges
            ),
            budget=configured_budget,
            budget_usage=usage,
            relationship=relationship,
            restart_from=restart,
        )

    def live_report(self, run_id: str) -> LiveReport:
        snapshot = self.snapshot(run_id)
        completed = [
            node_id
            for node_id, status, _ in snapshot.node_states
            if status in {"succeeded", "failed", "error", "cancelled"}
        ]
        return LiveReport(
            schema_version="1.0",
            report_id=f"live:{run_id}",
            run_id=run_id,
            contract=self._graph(run_id).contract,
            generated_at=utc_now(),
            run_status=snapshot.run_status,
            current_node_id=snapshot.current_node_id,
            completed_node_ids=completed,
            progress_summary=f"{len(completed)} node result(s) checkpointed",
            budget=snapshot.budget,
            budget_usage=snapshot.budget_usage,
        )

    def final_report(self, run_id: str) -> FinalReport:
        with self.state.read_connection() as connection:
            row = connection.execute(
                "SELECT report_json FROM reports WHERE run_id = ?", (run_id,)
            ).fetchone()
        if row is None:
            raise RuntimeInvariantError("FinalReport is not available for a non-terminal Run")
        return FinalReport.model_validate_json(str(row["report_json"]))

    def _graph(self, run_id: str) -> ExecutionGraph:
        graph = self._graphs.get(run_id)
        if graph is None:
            raise RecoveryError("Run must be created or recovered before scheduling")
        return graph

    @staticmethod
    def _node(graph: ExecutionGraph, node_id: str) -> Node:
        for node in graph.nodes:
            if node.node_id == node_id:
                return node
        raise RuntimeInvariantError(f"persisted node {node_id} is absent from Graph")

    @staticmethod
    def _required_run(connection: sqlite3.Connection, run_id: str) -> sqlite3.Row:
        row = connection.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(f"unknown Run: {run_id}")
        return cast(sqlite3.Row, row)

    def _run_status(self, run_id: str) -> RunStatus:
        with self.state.read_connection() as connection:
            return RunStatus(str(self._required_run(connection, run_id)["status"]))

    def _barrier(self, run_id: str) -> str | None:
        with self.state.read_connection() as connection:
            return cast(str | None, self._required_run(connection, run_id)["barrier"])

    def _next_node_row(self, run_id: str) -> sqlite3.Row | None:
        with self.state.read_connection() as connection:
            row = connection.execute(
                "SELECT * FROM nodes WHERE run_id = ? AND status IN ('running', 'ready') "
                "ORDER BY CASE status WHEN 'running' THEN 0 ELSE 1 END, node_id LIMIT 1",
                (run_id,),
            ).fetchone()
            return cast(sqlite3.Row | None, row)

    def _unresolved_result_row(self, run_id: str) -> sqlite3.Row | None:
        with self.state.read_connection() as connection:
            row = connection.execute(
                "SELECT * FROM nodes WHERE run_id = ? AND route_resolved = 0 "
                "AND result_json IS NOT NULL ORDER BY node_id LIMIT 1",
                (run_id,),
            ).fetchone()
            return cast(sqlite3.Row | None, row)

    def _start_attempt(self, run_id: str, node: Node) -> str:
        with self.state.transaction() as connection:
            run = self._required_run(connection, run_id)
            if str(run["status"]) != RunStatus.RUNNING.value or run["barrier"] is not None:
                raise RuntimeInvariantError("execution barrier forbids a new attempt")
            budget = connection.execute(
                "SELECT * FROM budgets WHERE run_id = ?", (run_id,)
            ).fetchone()
            if budget is None or int(budget["executor_calls"]) >= int(budget["max_executor_calls"]):
                raise _BudgetExhausted
            node_row = connection.execute(
                "SELECT attempt_count, status, first_started_at, cost_units, repair_iterations "
                "FROM nodes WHERE run_id = ? AND node_id = ?",
                (run_id, node.node_id),
            ).fetchone()
            if node_row is None or str(node_row["status"]) != "ready":
                raise RuntimeInvariantError("only a ready node can start an attempt")
            if self._node_budget_limit_reached(node, node_row):
                raise _BudgetExhausted
            number = int(node_row["attempt_count"]) + 1
            attempt_id = f"{run_id}:{node.node_id}:{number}"
            connection.execute(
                "UPDATE nodes SET status = 'running', attempt_count = ?, result_json = NULL, "
                "route_resolved = 0, first_started_at = COALESCE(first_started_at, ?) "
                "WHERE run_id = ? AND node_id = ?",
                (number, self._timestamp(), run_id, node.node_id),
            )
            connection.execute(
                "INSERT INTO attempts("
                "attempt_id, run_id, node_id, attempt_number, status, started_at"
                ") "
                "VALUES (?, ?, ?, ?, 'running', ?)",
                (attempt_id, run_id, node.node_id, number, self._timestamp()),
            )
            connection.execute(
                "UPDATE budgets SET executor_calls = executor_calls + 1 WHERE run_id = ?",
                (run_id,),
            )
            if node.node_type is NodeType.VERIFIER and node.config.get("external") is True:
                connection.execute(
                    """
                    INSERT INTO external_handles(
                        run_id, node_id, idempotency_key, trigger_state, updated_at,
                        verifier_id, verifier_revision
                    ) VALUES (?, ?, ?, 'triggering', ?, ?, ?)
                    ON CONFLICT(run_id, node_id) DO UPDATE SET
                        idempotency_key = excluded.idempotency_key,
                        trigger_state = 'triggering', handle = NULL,
                        updated_at = excluded.updated_at
                    """,
                    (
                        run_id,
                        node.node_id,
                        f"{run_id}:{node.node_id}",
                        self._timestamp(),
                        str(node.config.get("verifier_id", node.node_id)),
                        int(node.config.get("verifier_revision", 1)),
                    ),
                )
            self._checkpoint(connection, run_id, "attempt_started")
            self.state.enqueue_event(
                connection, "node.started", run_id, node_id=node.node_id, attempt_id=attempt_id
            )
        self.events.flush(self.state)
        return attempt_id

    def _invoke(self, run_id: str, node: Node, attempt_id: str) -> Result | None:
        try:
            if node.node_type is NodeType.VERIFIER:
                external = node.config.get("external") is True
                return self.verifier.execute(
                    run_id,
                    node,
                    attempt_id,
                    idempotency_key=f"{run_id}:{node.node_id}" if external else None,
                )
            return self.executor.execute(run_id, node, attempt_id)
        except Exception as exc:  # Fake boundary is deliberately converted to protocol error.
            error = Error(
                schema_version="1.0",
                kind=(
                    ErrorKind.VERIFIER
                    if node.node_type is NodeType.VERIFIER
                    else ErrorKind.EXECUTOR
                ),
                code="runtime.boundary_exception",
                message=str(exc),
                retryable=False,
            )
            if node.node_type is NodeType.VERIFIER:
                return VerifierResult(
                    schema_version="1.0", status=VerifierStatus.ERROR, summary=str(exc), error=error
                )
            return ExecutorResult(
                schema_version="1.0", status=ExecutorStatus.ERROR, summary=str(exc), error=error
            )

    def _persist_result(self, run_id: str, node: Node, attempt_id: str, result: Result) -> None:
        if isinstance(result, VerifierResult) and result.status is VerifierStatus.PENDING:
            if not result.external_handle:
                raise RuntimeInvariantError("pending Verifier result requires an external handle")
            with self.state.transaction() as connection:
                connection.execute(
                    "UPDATE external_handles SET trigger_state = 'checkpointed', handle = ?, "
                    "updated_at = ? WHERE run_id = ? AND node_id = ?",
                    (result.external_handle, timestamp(), run_id, node.node_id),
                )
                connection.execute(
                    "UPDATE attempts SET result_json = ? WHERE attempt_id = ?",
                    (result.canonical_json(), attempt_id),
                )
                for artifact in result.artifacts:
                    self._register_artifact(connection, run_id, node.node_id, "verifier", artifact)
                self._checkpoint(connection, run_id, "external_handle_checkpointed")
                self.state.enqueue_event(
                    connection,
                    "verifier.pending",
                    run_id,
                    node_id=node.node_id,
                    attempt_id=attempt_id,
                    payload={"external_handle": result.external_handle},
                )
            self.events.flush(self.state)
            return

        node_status = self._node_status(result)
        with self.state.transaction() as connection:
            connection.execute(
                "UPDATE attempts SET status = ?, result_json = ?, finished_at = ? "
                "WHERE attempt_id = ?",
                (node_status, result.canonical_json(), timestamp(), attempt_id),
            )
            connection.execute(
                "UPDATE nodes SET status = ?, result_json = ?, route_resolved = 0 "
                "WHERE run_id = ? AND node_id = ?",
                (node_status, result.canonical_json(), run_id, node.node_id),
            )
            role = "verifier" if isinstance(result, VerifierResult) else "executor"
            for artifact in result.artifacts:
                self._register_artifact(connection, run_id, node.node_id, role, artifact)
            self._checkpoint(connection, run_id, "result_checkpointed")
            self.state.enqueue_event(
                connection,
                "node.finished",
                run_id,
                node_id=node.node_id,
                attempt_id=attempt_id,
                payload={"status": self._result_status(result)},
            )
        self.events.flush(self.state)

    def _continue_external(self, run_id: str, node: Node) -> None:
        with self.state.read_connection() as connection:
            handle_row = connection.execute(
                "SELECT handle, verifier_id, verifier_revision FROM external_handles "
                "WHERE run_id = ? AND node_id = ?",
                (run_id, node.node_id),
            ).fetchone()
            attempt = connection.execute(
                "SELECT attempt_id FROM attempts WHERE run_id = ? AND node_id = ? "
                "ORDER BY attempt_number DESC LIMIT 1",
                (run_id, node.node_id),
            ).fetchone()
        if handle_row is None or handle_row["handle"] is None or attempt is None:
            self._finish_uncertain_external_effect(run_id, node.node_id)
            return
        query_for = getattr(self.verifier, "query_for", None)
        if callable(query_for) and handle_row["verifier_id"] is not None:
            result = query_for(
                str(handle_row["verifier_id"]),
                int(handle_row["verifier_revision"]),
                str(handle_row["handle"]),
            )
        else:
            result = self.verifier.query(str(handle_row["handle"]))
        self._persist_result(run_id, node, str(attempt["attempt_id"]), result)
        if result.status is not VerifierStatus.PENDING:
            self._honor_barrier_after_result(run_id)
            if self._run_status(run_id) is RunStatus.RUNNING:
                self._route_result(run_id, self._graph(run_id), node.node_id)

    @staticmethod
    def _node_status(result: Result) -> str:
        if isinstance(result, ExecutorResult):
            return result.status.value
        mapping = {
            VerifierStatus.PASSED: "succeeded",
            VerifierStatus.FAILED: "failed",
            VerifierStatus.ERROR: "error",
            VerifierStatus.CANCELLED: "cancelled",
        }
        if result.status is VerifierStatus.PENDING:
            return "running"
        return mapping[result.status]

    @staticmethod
    def _result_status(result: Result) -> str:
        return result.status.value

    def _route_result(self, run_id: str, graph: ExecutionGraph, node_id: str) -> None:
        if self._barrier(run_id) is not None:
            self._honor_barrier_after_result(run_id)
            return
        with self.state.read_connection() as connection:
            node_row = connection.execute(
                "SELECT result_json, route_resolved, attempt_count FROM nodes "
                "WHERE run_id = ? AND node_id = ?",
                (run_id, node_id),
            ).fetchone()
            if node_row is None or node_row["result_json"] is None:
                raise RuntimeInvariantError("cannot route a node without a result")
            if int(node_row["route_resolved"]) == 1:
                return
            result_data = cast(dict[str, Any], json.loads(str(node_row["result_json"])))
            counts = {
                (str(row["from_node"]), str(row["to_node"])): int(row["traversal_count"])
                for row in connection.execute(
                    "SELECT * FROM edge_traversals WHERE run_id = ?", (run_id,)
                )
            }
        selected: Edge | None = None
        for edge in graph.edges:
            if edge.from_node != node_id:
                continue
            count = counts.get((edge.from_node, edge.to_node), 0)
            if edge.max_iterations is not None and count >= edge.max_iterations:
                continue
            if edge.condition is None or self._condition_matches(
                edge, result_data, int(node_row["attempt_count"])
            ):
                selected = edge
                break
        if selected is None:
            status = str(result_data["status"])
            error = None
            if status == "error" and result_data.get("error") is not None:
                error = Error.model_validate(result_data["error"])
            if status in {"succeeded", "passed"}:
                self._finish(run_id, TerminalStatus.SUCCEEDED, TerminalReason.COMPLETED)
            elif status == "failed":
                self._finish(run_id, TerminalStatus.FAILED, TerminalReason.ACCEPTANCE_FAILED)
            elif status == "cancelled":
                self._finish(run_id, TerminalStatus.CANCELLED, TerminalReason.HUMAN_CANCELLED)
            else:
                self._finish(
                    run_id, TerminalStatus.ERROR, TerminalReason.EXECUTION_ERROR, error=error
                )
            return

        with self.state.transaction() as connection:
            run = self._required_run(connection, run_id)
            if run["barrier"] is not None:
                return
            budget = connection.execute(
                "SELECT repair_iterations, max_repair_iterations FROM budgets WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            node_budget_row = connection.execute(
                "SELECT repair_iterations FROM nodes WHERE run_id = ? AND node_id = ?",
                (run_id, node_id),
            ).fetchone()
            source_node_budget = self._node(graph, node_id).budget
            is_repair = (
                selected.max_iterations is not None and str(result_data["status"]) == "failed"
            )
            if (
                is_repair
                and budget is not None
                and int(budget["repair_iterations"]) >= int(budget["max_repair_iterations"])
            ) or (
                is_repair
                and source_node_budget is not None
                and node_budget_row is not None
                and int(node_budget_row["repair_iterations"])
                >= source_node_budget.max_repair_iterations
            ):
                exhausted = True
            else:
                exhausted = False
                connection.execute(
                    """
                    INSERT INTO edge_traversals(run_id, from_node, to_node, traversal_count)
                    VALUES (?, ?, ?, 1)
                    ON CONFLICT(run_id, from_node, to_node)
                    DO UPDATE SET traversal_count = traversal_count + 1
                    """,
                    (run_id, selected.from_node, selected.to_node),
                )
                if is_repair:
                    connection.execute(
                        "UPDATE budgets SET repair_iterations = repair_iterations + 1 "
                        "WHERE run_id = ?",
                        (run_id,),
                    )
                    connection.execute(
                        "UPDATE nodes SET repair_iterations = repair_iterations + 1 "
                        "WHERE run_id = ? AND node_id = ?",
                        (run_id, node_id),
                    )
                connection.execute(
                    "UPDATE nodes SET route_resolved = 1 WHERE run_id = ? AND node_id = ?",
                    (run_id, node_id),
                )
                connection.execute(
                    "UPDATE nodes SET status = 'ready', result_json = NULL, route_resolved = 0 "
                    "WHERE run_id = ? AND node_id = ?",
                    (run_id, selected.to_node),
                )
                connection.execute(
                    "UPDATE runs SET current_node_id = ?, updated_at = ? WHERE run_id = ?",
                    (selected.to_node, timestamp(), run_id),
                )
                self._checkpoint(connection, run_id, "route_selected")
                self.state.enqueue_event(
                    connection,
                    "route.selected",
                    run_id,
                    node_id=node_id,
                    payload={"to_node": selected.to_node},
                )
        if exhausted:
            self._finish(run_id, TerminalStatus.FAILED, TerminalReason.BUDGET_EXHAUSTED)
        self.events.flush(self.state)

    @staticmethod
    def _condition_matches(edge: Edge, result: dict[str, Any], attempt_number: int) -> bool:
        condition = edge.condition
        if condition is None:
            return True
        if condition.field is RouteField.RESULT_STATUS:
            actual: object = result.get("status")
        elif condition.field is RouteField.RESULT_RETRYABLE:
            actual = result.get("retryable", False)
        else:
            actual = attempt_number
        expected = condition.value
        if condition.operator is RouteOperator.EQUALS:
            return actual == expected
        if condition.operator is RouteOperator.NOT_EQUALS:
            return actual != expected
        if condition.operator is RouteOperator.IN:
            return actual in cast(list[object], expected)
        return actual not in cast(list[object], expected)

    def _honor_barrier_after_result(self, run_id: str) -> None:
        barrier = self._barrier(run_id)
        if barrier == StateChangeAction.PAUSE.value:
            self._pause_at_safe_point(run_id)
        elif barrier == StateChangeAction.INTERRUPT.value:
            self._finish(run_id, TerminalStatus.INTERRUPTED, TerminalReason.HUMAN_INTERRUPTED)

    def _pause_at_safe_point(self, run_id: str) -> None:
        with self.state.transaction() as connection:
            run = self._required_run(connection, run_id)
            if str(run["status"]) == RunStatus.PAUSED.value:
                return
            connection.execute(
                "UPDATE runs SET status = ?, updated_at = ? WHERE run_id = ?",
                (RunStatus.PAUSED.value, timestamp(), run_id),
            )
            self._checkpoint(connection, run_id, "paused")
            self.state.enqueue_event(connection, "run.paused", run_id)
        self.events.flush(self.state)

    def _finish(
        self,
        run_id: str,
        status: TerminalStatus,
        reason: TerminalReason,
        *,
        error: Error | None = None,
    ) -> None:
        with self.state.transaction() as connection:
            run = self._required_run(connection, run_id)
            if str(run["status"]) in _TERMINAL_VALUES:
                return
            connection.execute(
                "UPDATE runs SET status = ?, barrier = NULL, terminal_reason = ?, error_json = ?, "
                "updated_at = ? WHERE run_id = ?",
                (
                    status.value,
                    reason.value,
                    error.canonical_json() if error is not None else None,
                    timestamp(),
                    run_id,
                ),
            )
            self._checkpoint(connection, run_id, "terminal")
            self.state.enqueue_event(
                connection,
                "run.finished",
                run_id,
                payload={"status": status.value, "reason": reason.value},
            )
        self._freeze_report(run_id)
        self.events.flush(self.state)

    def _freeze_report(self, run_id: str) -> None:
        snapshot = self.snapshot(run_id)
        with self.state.read_connection() as connection:
            run = self._required_run(connection, run_id)
            unverified_data = cast(list[dict[str, Any]], json.loads(str(run["unverified_json"])))
            effect_data = cast(list[dict[str, Any]], json.loads(str(run["external_effects_json"])))
            error_json = cast(str | None, run["error_json"])
            completed = [
                str(row["node_id"])
                for row in connection.execute(
                    "SELECT node_id FROM nodes WHERE run_id = ? AND status = 'succeeded' "
                    "ORDER BY node_id",
                    (run_id,),
                )
            ]
            intent_ids = [
                str(row["intent_id"])
                for row in connection.execute(
                    "SELECT intent_id FROM control_intents WHERE run_id = ? ORDER BY created_at",
                    (run_id,),
                )
            ]
            result_payloads = [
                cast(dict[str, Any], json.loads(str(row["result_json"])))
                for row in connection.execute(
                    "SELECT result_json FROM attempts "
                    "WHERE run_id = ? AND result_json IS NOT NULL "
                    "UNION SELECT result_json FROM nodes "
                    "WHERE run_id = ? AND result_json IS NOT NULL",
                    (run_id, run_id),
                )
            ]
            verification_artifacts = [
                Artifact(
                    schema_version="1.0",
                    artifact_id=str(row["artifact_id"]),
                    kind=ArtifactKind(str(row["kind"])),
                    uri=str(row["uri"]),
                    sha256_digest=str(row["sha256_digest"]),
                    media_type=cast(str | None, row["media_type"]),
                    size_bytes=int(row["size_bytes"]),
                    created_at=self._parse_timestamp(str(row["created_at"])),
                )
                for row in connection.execute(
                    """
                    SELECT DISTINCT m.* FROM run_artifacts r
                    JOIN artifact_metadata m ON m.artifact_id = r.artifact_id
                    WHERE r.run_id = ? AND r.role = 'verifier'
                    ORDER BY m.artifact_id
                    """,
                    (run_id,),
                )
            ]
        changed_files = sorted(
            {
                str(path)
                for payload in result_payloads
                for path in cast(list[object], payload.get("changed_files", []))
            }
        )
        terminal_status = TerminalStatus(snapshot.run_status.value)
        report = FinalReport(
            schema_version="1.0",
            report_id=f"final:{run_id}:1",
            report_revision=1,
            frozen_at=self.clock(),
            relationship=snapshot.relationship,
            contract=ContractRef(
                schema_version="1.0",
                contract_id=str(run["contract_id"]),
                revision=int(run["contract_revision"]),
            ),
            terminal_status=terminal_status,
            terminal_reason=TerminalReason(str(run["terminal_reason"])),
            summary=f"Run {run_id} finished as {terminal_status.value}",
            changed_files=changed_files,
            completed_node_ids=completed,
            verification_artifacts=verification_artifacts,
            control_intent_ids=intent_ids,
            unverified_items=[UnverifiedItem.model_validate(value) for value in unverified_data],
            external_effects=[ExternalEffect.model_validate(value) for value in effect_data],
            budget_usage=snapshot.budget_usage,
            error=Error.model_validate_json(error_json) if error_json else None,
        )
        with self.state.transaction() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO reports(run_id, report_json, frozen_at) VALUES (?, ?, ?)",
                (run_id, report.canonical_json(), self._timestamp()),
            )
            self.state.enqueue_event(connection, "report.final.frozen", run_id)

    def _finish_uncertain_external_effect(self, run_id: str, node_id: str) -> None:
        error = Error(
            schema_version="1.0",
            kind=ErrorKind.INFRASTRUCTURE,
            code="external_effect.uncertain",
            message="external side effect cannot be confirmed after recovery",
            retryable=False,
            details={"node_id": node_id},
        )
        item = UnverifiedItem(
            schema_version="1.0",
            item_id=f"unverified:{run_id}:{node_id}",
            description="External trigger outcome",
            reason="process stopped before a handle was checkpointed",
            impact="the Runtime cannot safely retry or classify the external operation",
        )
        effect = ExternalEffect(
            schema_version="1.0",
            effect_id=f"effect:{run_id}:{node_id}",
            description="An external trigger may have occurred",
            reversible=False,
            compensation_status="unknown",
        )
        with self.state.transaction() as connection:
            connection.execute(
                "UPDATE runs SET unverified_json = ?, external_effects_json = ? WHERE run_id = ?",
                (
                    json.dumps([item.model_dump(mode="json")], ensure_ascii=False),
                    json.dumps([effect.model_dump(mode="json")], ensure_ascii=False),
                    run_id,
                ),
            )
        self._finish(run_id, TerminalStatus.ERROR, TerminalReason.EXECUTION_ERROR, error=error)

    def _record_control(self, intent: QueryControlIntent, outcome: ControlOutcome) -> None:
        with self.state.transaction() as connection:
            connection.execute(
                "INSERT INTO control_intents("
                "intent_id, run_id, intent_kind, action, intent_json, outcome, created_at"
                ") VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    intent.intent_id,
                    intent.run_id,
                    intent.intent_kind,
                    intent.action.value,
                    intent.model_dump_json(exclude_none=True),
                    outcome.value,
                    timestamp(),
                ),
            )
            self.state.enqueue_event(
                connection,
                "query.snapshot.generated",
                intent.run_id,
                payload={"intent_id": intent.intent_id, "action": intent.action.value},
            )

    def _timestamp(self) -> str:
        return self.clock().isoformat().replace("+00:00", "Z")

    def _validate_run_lineage(
        self,
        connection: sqlite3.Connection,
        graph: ExecutionGraph,
        contract_hash: str,
        relationship: RunRelationship,
        restart_from: RestartFrom | None,
    ) -> dict[str, Any] | None:
        referenced = {
            run_id
            for run_id in (relationship.parent_run_id, relationship.supersedes_run_id)
            if run_id is not None
        }
        for referenced_run_id in referenced:
            exists = connection.execute(
                "SELECT 1 FROM runs WHERE run_id = ?", (referenced_run_id,)
            ).fetchone()
            if exists is None:
                label = (
                    "parent Run"
                    if referenced_run_id == relationship.parent_run_id
                    else "superseded Run"
                )
                raise ValueError(f"{label} does not exist: {referenced_run_id}")
        if restart_from is None or restart_from.strategy is not RestartStrategy.CHECKPOINT:
            return None
        if not referenced:
            raise ValueError("checkpoint restart requires a parent or superseded Run")
        checkpoint = connection.execute(
            "SELECT run_id, state_json FROM checkpoints WHERE checkpoint_ref = ?",
            (restart_from.reference,),
        ).fetchone()
        if checkpoint is None:
            raise ValueError(f"checkpoint does not exist: {restart_from.reference}")
        source_run_id = str(checkpoint["run_id"])
        if source_run_id not in referenced:
            raise ValueError("checkpoint does not belong to the parent or superseded Run")
        state = cast(dict[str, Any], json.loads(str(checkpoint["state_json"])))
        if state.get("graph_hash") != graph.sha256():
            raise ValueError("checkpoint Graph hash does not match the new Run")
        if state.get("contract_hash") != contract_hash:
            raise ValueError("checkpoint Contract hash does not match the new Run")
        return state

    def _budget_limit_reached(
        self,
        run_id: str,
        node: Node | None = None,
        *,
        cost_check_after_charge: bool = False,
        check_attempt_limit: bool = False,
    ) -> bool:
        with self.state.read_connection() as connection:
            budget = connection.execute(
                "SELECT * FROM budgets WHERE run_id = ?", (run_id,)
            ).fetchone()
            if budget is None:
                raise RuntimeInvariantError("budget row is missing")
            started_at = self._parse_timestamp(str(budget["started_at"]))
            elapsed = (self.clock() - started_at).total_seconds()
            if elapsed >= int(budget["max_duration_seconds"]):
                return True
            if budget["max_cost_units"] is not None and budget["cost_units"] is not None:
                actual = float(budget["cost_units"])
                limit = float(budget["max_cost_units"])
                if actual > limit or (not cost_check_after_charge and actual >= limit):
                    return True
            if node is None:
                return False
            node_row = connection.execute(
                "SELECT attempt_count, first_started_at, cost_units, repair_iterations "
                "FROM nodes WHERE run_id = ? AND node_id = ?",
                (run_id, node.node_id),
            ).fetchone()
            if node_row is None:
                raise RuntimeInvariantError("node budget row is missing")
            return self._node_budget_limit_reached(
                node,
                node_row,
                cost_check_after_charge=cost_check_after_charge,
                check_attempt_limit=check_attempt_limit,
            )

    def _node_budget_limit_reached(
        self,
        node: Node,
        row: sqlite3.Row,
        *,
        cost_check_after_charge: bool = False,
        check_attempt_limit: bool = True,
    ) -> bool:
        budget = node.budget
        if budget is None:
            return False
        if check_attempt_limit and int(row["attempt_count"]) >= budget.max_executor_calls:
            return True
        if row["first_started_at"] is not None:
            elapsed = (
                self.clock() - self._parse_timestamp(str(row["first_started_at"]))
            ).total_seconds()
            if elapsed >= budget.max_duration_seconds:
                return True
        if budget.max_cost_units is not None:
            actual = float(row["cost_units"])
            if actual > budget.max_cost_units or (
                not cost_check_after_charge and actual >= budget.max_cost_units
            ):
                return True
        return False

    @staticmethod
    def _parse_timestamp(value: str) -> datetime:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))

    def _register_artifact(
        self,
        connection: sqlite3.Connection,
        run_id: str,
        node_id: str,
        role: str,
        artifact: Artifact,
    ) -> None:
        if artifact.sha256_digest is None or artifact.size_bytes is None:
            raise RuntimeInvariantError("persisted artifacts require digest and size metadata")
        connection.execute(
            """
            INSERT OR IGNORE INTO artifact_metadata(
                artifact_id, run_id, uri, sha256_digest, media_type,
                size_bytes, created_at, kind
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                artifact.artifact_id,
                run_id,
                artifact.uri,
                artifact.sha256_digest,
                artifact.media_type,
                artifact.size_bytes,
                artifact.created_at.isoformat(),
                artifact.kind.value,
            ),
        )
        stored = connection.execute(
            "SELECT uri, sha256_digest FROM artifact_metadata WHERE artifact_id = ?",
            (artifact.artifact_id,),
        ).fetchone()
        if (
            stored is None
            or str(stored["uri"]) != artifact.uri
            or str(stored["sha256_digest"]) != artifact.sha256_digest
        ):
            raise RuntimeInvariantError("artifact metadata collision")
        cursor = connection.execute(
            "INSERT OR IGNORE INTO run_artifacts("
            "run_id, artifact_id, node_id, role"
            ") VALUES (?, ?, ?, ?)",
            (run_id, artifact.artifact_id, node_id, role),
        )
        if cursor.rowcount:
            self.state.enqueue_event(
                connection,
                "artifact.created",
                run_id,
                node_id=node_id or None,
                payload={"artifact_id": artifact.artifact_id, "role": role},
            )

    def _checkpoint(self, connection: sqlite3.Connection, run_id: str, reason: str) -> str:
        run = self._required_run(connection, run_id)
        nodes = [
            dict(row)
            for row in connection.execute(
                "SELECT node_id, node_type, status, attempt_count, result_json, route_resolved "
                "FROM nodes WHERE run_id = ? ORDER BY node_id",
                (run_id,),
            )
        ]
        edges = [
            dict(row)
            for row in connection.execute(
                "SELECT from_node, to_node, traversal_count FROM edge_traversals "
                "WHERE run_id = ? ORDER BY from_node, to_node",
                (run_id,),
            )
        ]
        artifacts = [
            dict(row)
            for row in connection.execute(
                "SELECT artifact_id, node_id, role FROM run_artifacts "
                "WHERE run_id = ? ORDER BY artifact_id, node_id, role",
                (run_id,),
            )
        ]
        state = {
            "run_id": run_id,
            "reason": reason,
            "graph_hash": str(run["graph_hash"]),
            "contract_hash": str(run["contract_hash"]),
            "current_node_id": cast(str | None, run["current_node_id"]),
            "nodes": nodes,
            "edges": edges,
            "artifacts": artifacts,
        }
        checkpoint_ref = f"checkpoint:{uuid.uuid4()}"
        connection.execute(
            "INSERT INTO checkpoints("
            "run_id, reason, state_json, created_at, checkpoint_ref"
            ") VALUES (?, ?, ?, ?, ?)",
            (
                run_id,
                reason,
                json.dumps(state, separators=(",", ":"), sort_keys=True),
                self._timestamp(),
                checkpoint_ref,
            ),
        )
        return checkpoint_ref
