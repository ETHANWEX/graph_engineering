"""Durable bounded branch scheduling for Phase 6B container nodes."""

from __future__ import annotations

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Any, cast

from graph_engineering.models import (
    BranchResult,
    Error,
    ExecutorResult,
    ParallelResult,
    VerifierResult,
)
from graph_engineering.models.common import ErrorKind
from graph_engineering.models.graph import Edge, Node, NodeType, ParallelBranch, Subgraph
from graph_engineering.models.results import (
    BranchStatus,
    ExecutorStatus,
    VerifierStatus,
)

from .errors import RuntimeInvariantError
from .store import timestamp

if TYPE_CHECKING:
    from .engine import GraphRuntime, Result

_TERMINAL_BRANCHES = {status.value for status in BranchStatus}


class ParallelCoordinator:
    def __init__(self, runtime: GraphRuntime) -> None:
        self.runtime = runtime

    def initialize(self, connection: sqlite3.Connection, run_id: str, nodes: list[Node]) -> None:
        for node in nodes:
            branches: list[ParallelBranch]
            if node.node_type is NodeType.PARALLEL:
                assert node.parallel is not None
                branches = list(node.parallel.branches)
            elif node.node_type is NodeType.SUBGRAPH:
                assert node.subgraph is not None
                branches = [
                    ParallelBranch(
                        schema_version="1.0", branch_id="subgraph", subgraph=node.subgraph
                    )
                ]
            else:
                continue
            for order, branch in enumerate(branches):
                connection.execute(
                    "INSERT INTO parallel_branches("
                    "run_id,container_node_id,branch_id,branch_order,subgraph_json,subgraph_hash,"
                    "status,current_node_id) VALUES (?,?,?,?,?,?,?,?)",
                    (
                        run_id,
                        node.node_id,
                        branch.branch_id,
                        order,
                        branch.subgraph.canonical_json(),
                        branch.subgraph.sha256(),
                        "pending",
                        branch.subgraph.entry_node_id,
                    ),
                )
                for nested in branch.subgraph.nodes:
                    connection.execute(
                        "INSERT INTO parallel_branch_nodes("
                        "run_id,container_node_id,branch_id,node_id,node_type,status) "
                        "VALUES (?,?,?,?,?,?)",
                        (
                            run_id,
                            node.node_id,
                            branch.branch_id,
                            nested.node_id,
                            nested.node_type.value,
                            "ready"
                            if nested.node_id == branch.subgraph.entry_node_id
                            else "pending",
                        ),
                    )

    def inherit(
        self, connection: sqlite3.Connection, run_id: str, checkpoint: dict[str, Any]
    ) -> None:
        for branch in checkpoint.get("branches", []):
            status = "pending" if str(branch["status"]) == "active" else str(branch["status"])
            connection.execute(
                "UPDATE parallel_branches SET status=?,current_node_id=?,result_json=?,"
                "started_at=?,finished_at=? WHERE run_id=? AND container_node_id=? AND branch_id=?",
                (
                    status,
                    branch.get("current_node_id"),
                    branch.get("result_json"),
                    branch.get("started_at"),
                    branch.get("finished_at"),
                    run_id,
                    str(branch["container_node_id"]),
                    str(branch["branch_id"]),
                ),
            )
        for node in checkpoint.get("branch_nodes", []):
            status = "ready" if str(node["status"]) == "running" else str(node["status"])
            connection.execute(
                "UPDATE parallel_branch_nodes SET status=?,attempt_count=?,result_json=?,"
                "route_resolved=?,first_started_at=?,cost_units=?,repair_iterations=? "
                "WHERE run_id=? AND container_node_id=? AND branch_id=? AND node_id=?",
                (
                    status,
                    int(node["attempt_count"]),
                    node.get("result_json"),
                    int(node["route_resolved"]),
                    node.get("first_started_at"),
                    float(node.get("cost_units", 0)),
                    int(node.get("repair_iterations", 0)),
                    run_id,
                    str(node["container_node_id"]),
                    str(node["branch_id"]),
                    str(node["node_id"]),
                ),
            )
        for edge in checkpoint.get("branch_edges", []):
            connection.execute(
                "INSERT INTO parallel_branch_edge_traversals("
                "run_id,container_node_id,branch_id,from_node,to_node,traversal_count) "
                "VALUES (?,?,?,?,?,?)",
                (
                    run_id,
                    str(edge["container_node_id"]),
                    str(edge["branch_id"]),
                    str(edge["from_node"]),
                    str(edge["to_node"]),
                    int(edge["traversal_count"]),
                ),
            )

    def step(
        self, run_id: str, container: Node, attempt_id: str
    ) -> ParallelResult | ExecutorResult | None:
        if self.runtime._barrier(run_id) is not None:
            return None
        limit = 1
        if container.node_type is NodeType.PARALLEL:
            assert container.parallel is not None
            limit = container.parallel.max_concurrency
        with self.runtime.state.read_connection() as connection:
            rows = list(
                connection.execute(
                    "SELECT branch_id,status FROM parallel_branches "
                    "WHERE run_id=? AND container_node_id=? "
                    "AND status NOT IN ('succeeded','failed','blocked','error','cancelled') "
                    "ORDER BY CASE status WHEN 'active' THEN 0 ELSE 1 END, branch_order, branch_id "
                    "LIMIT ?",
                    (run_id, container.node_id, limit),
                )
            )
        if rows:
            with ThreadPoolExecutor(
                max_workers=limit, thread_name_prefix=f"ge-{container.node_id}"
            ) as pool:
                futures = [
                    pool.submit(self._branch_step, run_id, container, str(row["branch_id"]))
                    for row in rows
                ]
                for future in futures:
                    future.result()
        if self.runtime._barrier(run_id) in {"interrupt", "cancel"}:
            self.cancel_incomplete(run_id, self.runtime._barrier(run_id) or "cancel")
            return None
        aggregate = self.aggregate(run_id, container.node_id)
        if aggregate is None:
            return None
        if container.node_type is NodeType.PARALLEL:
            return aggregate
        return self._subgraph_result(aggregate.branches[0])

    def aggregate(self, run_id: str, container_node_id: str) -> ParallelResult | None:
        with self.runtime.state.read_connection() as connection:
            rows = list(
                connection.execute(
                    "SELECT branch_id,status,result_json FROM parallel_branches "
                    "WHERE run_id=? AND container_node_id=? ORDER BY branch_id",
                    (run_id, container_node_id),
                )
            )
        if not rows or any(str(row["status"]) not in _TERMINAL_BRANCHES for row in rows):
            return None
        branches = [BranchResult.model_validate_json(str(row["result_json"])) for row in rows]
        precedence = {
            BranchStatus.SUCCEEDED: 0,
            BranchStatus.CANCELLED: 1,
            BranchStatus.FAILED: 2,
            BranchStatus.BLOCKED: 3,
            BranchStatus.ERROR: 4,
        }
        status = max((branch.status for branch in branches), key=precedence.__getitem__)
        changed_files = sorted({path for branch in branches for path in branch.changed_files})
        artifacts_by_id = {
            artifact.artifact_id: artifact for branch in branches for artifact in branch.artifacts
        }
        failures = [
            f"{branch.branch_id}: {detail}"
            for branch in branches
            for detail in branch.failure_details
        ]
        error = None
        if status in {BranchStatus.ERROR, BranchStatus.BLOCKED}:
            affected = [
                branch.branch_id
                for branch in branches
                if branch.status in {BranchStatus.ERROR, BranchStatus.BLOCKED}
            ]
            error = Error(
                schema_version="1.0",
                kind=ErrorKind.INFRASTRUCTURE,
                code=(
                    "parallel.branch_error" if status is BranchStatus.ERROR else "parallel.blocked"
                ),
                message=f"parallel branches did not succeed: {', '.join(affected)}",
                retryable=False,
                details={"branch_ids": affected},
            )
        return ParallelResult(
            schema_version="1.0",
            parallel_node_id=container_node_id,
            status=status,
            summary=f"{len(branches)} branch result(s) joined as {status.value}",
            branches=branches,
            changed_files=changed_files,
            artifacts=[artifacts_by_id[key] for key in sorted(artifacts_by_id)],
            failure_details=failures,
            error=error,
        )

    def join(self, run_id: str, join_node: Node) -> ParallelResult:
        assert join_node.join is not None
        with self.runtime.state.read_connection() as connection:
            row = connection.execute(
                "SELECT result_json FROM nodes WHERE run_id=? AND node_id=?",
                (run_id, join_node.join.parallel_node_id),
            ).fetchone()
        if row is None or row["result_json"] is None:
            raise RuntimeInvariantError("join source has no persisted parallel result")
        return ParallelResult.model_validate_json(str(row["result_json"]))

    def cancel_pending(self, run_id: str, reason: str) -> None:
        self._cancel_branches(run_id, reason, include_active=False)

    def cancel_incomplete(self, run_id: str, reason: str) -> None:
        self._cancel_branches(run_id, reason, include_active=True)

    def _cancel_branches(self, run_id: str, reason: str, *, include_active: bool) -> None:
        statuses = "('pending','active')" if include_active else "('pending')"
        with self.runtime.state.transaction() as connection:
            rows = list(
                connection.execute(
                    "SELECT container_node_id,branch_id FROM parallel_branches "
                    f"WHERE run_id=? AND status IN {statuses}",
                    (run_id,),
                )
            )
            for row in rows:
                branch_id = str(row["branch_id"])
                result = BranchResult(
                    schema_version="1.0",
                    branch_id=branch_id,
                    status=BranchStatus.CANCELLED,
                    summary=f"branch cancelled by durable {reason} barrier",
                )
                connection.execute(
                    "UPDATE parallel_branches SET status='cancelled',result_json=?,finished_at=? "
                    f"WHERE run_id=? AND container_node_id=? AND branch_id=? "
                    f"AND status IN {statuses}",
                    (
                        result.canonical_json(),
                        timestamp(),
                        run_id,
                        str(row["container_node_id"]),
                        branch_id,
                    ),
                )
            if rows:
                self.runtime._checkpoint(connection, run_id, f"parallel_{reason}_barrier")

    def _branch_step(self, run_id: str, container: Node, branch_id: str) -> None:
        if self.runtime._barrier(run_id) is not None:
            return
        subgraph = self._subgraph(container, branch_id)
        with self.runtime.state.read_connection() as connection:
            row = connection.execute(
                "SELECT current_node_id FROM parallel_branches "
                "WHERE run_id=? AND container_node_id=? AND branch_id=?",
                (run_id, container.node_id, branch_id),
            ).fetchone()
            if row is None or row["current_node_id"] is None:
                return
            node_row = connection.execute(
                "SELECT * FROM parallel_branch_nodes WHERE run_id=? AND container_node_id=? "
                "AND branch_id=? AND node_id=?",
                (run_id, container.node_id, branch_id, str(row["current_node_id"])),
            ).fetchone()
        if node_row is None:
            raise RuntimeInvariantError("parallel branch current node is missing")
        nested = self._node(subgraph, str(node_row["node_id"]))
        qualified = nested.model_copy(
            update={"node_id": f"{container.node_id}.{branch_id}.{nested.node_id}"}
        )
        if str(node_row["status"]) == "running":
            self._continue_external(run_id, container, branch_id, nested, qualified)
            return
        if node_row["result_json"] is not None and int(node_row["route_resolved"]) == 0:
            persisted: Result
            if nested.node_type is NodeType.VERIFIER:
                persisted = VerifierResult.model_validate_json(str(node_row["result_json"]))
            else:
                persisted = ExecutorResult.model_validate_json(str(node_row["result_json"]))
            self._route(run_id, container, branch_id, nested, persisted)
            return
        try:
            attempt_id = self._start_attempt(run_id, container, branch_id, nested, qualified)
        except RuntimeError as exc:
            if str(exc) != "parallel budget exhausted":
                raise
            self._block_branch(run_id, container.node_id, branch_id, "shared budget exhausted")
            return
        result = self.runtime._invoke(run_id, qualified, attempt_id)
        if result is None:
            return
        self._persist_result(run_id, container, branch_id, nested, qualified, attempt_id, result)

    def _start_attempt(
        self, run_id: str, container: Node, branch_id: str, nested: Node, qualified: Node
    ) -> str:
        with self.runtime.state.transaction() as connection:
            run = self.runtime._required_run(connection, run_id)
            if str(run["status"]) != "running" or run["barrier"] is not None:
                raise RuntimeInvariantError("execution barrier forbids a parallel branch attempt")
            budget = connection.execute(
                "SELECT * FROM budgets WHERE run_id=?", (run_id,)
            ).fetchone()
            if budget is None or int(budget["executor_calls"]) >= int(budget["max_executor_calls"]):
                raise RuntimeError("parallel budget exhausted")
            row = connection.execute(
                "SELECT * FROM parallel_branch_nodes WHERE run_id=? AND container_node_id=? "
                "AND branch_id=? AND node_id=?",
                (run_id, container.node_id, branch_id, nested.node_id),
            ).fetchone()
            if row is None or str(row["status"]) != "ready":
                raise RuntimeInvariantError("only a ready parallel branch node can start")
            if self.runtime._node_budget_limit_reached(nested, row):
                raise RuntimeError("parallel budget exhausted")
            number = int(row["attempt_count"]) + 1
            attempt_id = f"{run_id}:{container.node_id}:{branch_id}:{nested.node_id}:{number}"
            now = self.runtime._timestamp()
            connection.execute(
                "UPDATE parallel_branches SET status='active',started_at=COALESCE(started_at,?) "
                "WHERE run_id=? AND container_node_id=? AND branch_id=?",
                (now, run_id, container.node_id, branch_id),
            )
            connection.execute(
                "UPDATE parallel_branch_nodes SET status='running',attempt_count=?,"
                "result_json=NULL,"
                "route_resolved=0,first_started_at=COALESCE(first_started_at,?) "
                "WHERE run_id=? AND container_node_id=? AND branch_id=? AND node_id=?",
                (number, now, run_id, container.node_id, branch_id, nested.node_id),
            )
            connection.execute(
                "INSERT INTO parallel_branch_attempts("
                "attempt_id,run_id,container_node_id,branch_id,node_id,attempt_number,status,started_at"
                ") VALUES (?,?,?,?,?,?,'running',?)",
                (
                    attempt_id,
                    run_id,
                    container.node_id,
                    branch_id,
                    nested.node_id,
                    number,
                    now,
                ),
            )
            connection.execute(
                "UPDATE budgets SET executor_calls=executor_calls+1 WHERE run_id=?", (run_id,)
            )
            if nested.node_type is NodeType.VERIFIER and nested.config.get("external") is True:
                connection.execute(
                    "INSERT INTO external_handles("
                    "run_id,node_id,idempotency_key,trigger_state,updated_at,verifier_id,"
                    "verifier_revision) VALUES (?,?,?,'triggering',?,?,?) "
                    "ON CONFLICT(run_id,node_id) DO UPDATE SET "
                    "idempotency_key=excluded.idempotency_key,trigger_state='triggering',handle=NULL,"
                    "updated_at=excluded.updated_at",
                    (
                        run_id,
                        qualified.node_id,
                        f"{run_id}:{qualified.node_id}",
                        now,
                        str(nested.config.get("verifier_id", nested.node_id)),
                        int(nested.config.get("verifier_revision", 1)),
                    ),
                )
            self.runtime._checkpoint(connection, run_id, "parallel_attempt_started")
            self.runtime.state.enqueue_event(
                connection,
                "branch.node.started",
                run_id,
                node_id=qualified.node_id,
                attempt_id=attempt_id,
                payload={"container_node_id": container.node_id, "branch_id": branch_id},
            )
        self.runtime.events.flush(self.runtime.state)
        return attempt_id

    def _persist_result(
        self,
        run_id: str,
        container: Node,
        branch_id: str,
        nested: Node,
        qualified: Node,
        attempt_id: str,
        result: Result,
    ) -> None:
        if isinstance(result, VerifierResult) and result.status is VerifierStatus.PENDING:
            if not result.external_handle:
                raise RuntimeInvariantError("pending branch Verifier requires an external handle")
            with self.runtime.state.transaction() as connection:
                connection.execute(
                    "UPDATE external_handles SET trigger_state='checkpointed',handle=?,"
                    "updated_at=? "
                    "WHERE run_id=? AND node_id=?",
                    (result.external_handle, timestamp(), run_id, qualified.node_id),
                )
                connection.execute(
                    "UPDATE parallel_branch_attempts SET result_json=? WHERE attempt_id=?",
                    (result.canonical_json(), attempt_id),
                )
                self.runtime._checkpoint(connection, run_id, "parallel_external_checkpointed")
            self.runtime.events.flush(self.runtime.state)
            return
        status = self.runtime._node_status(result)
        with self.runtime.state.transaction() as connection:
            run = self.runtime._required_run(connection, run_id)
            if str(run["status"]) in {
                "succeeded",
                "failed",
                "error",
                "interrupted",
                "cancelled",
                "rejected",
            }:
                return
            connection.execute(
                "UPDATE parallel_branch_attempts SET status=?,result_json=?,finished_at=? "
                "WHERE attempt_id=?",
                (status, result.canonical_json(), timestamp(), attempt_id),
            )
            connection.execute(
                "UPDATE parallel_branch_nodes SET status=?,result_json=?,route_resolved=0 "
                "WHERE run_id=? AND container_node_id=? AND branch_id=? AND node_id=?",
                (
                    status,
                    result.canonical_json(),
                    run_id,
                    container.node_id,
                    branch_id,
                    nested.node_id,
                ),
            )
            role = "verifier" if isinstance(result, VerifierResult) else "executor"
            for artifact in result.artifacts:
                self.runtime._register_artifact(
                    connection, run_id, qualified.node_id, role, artifact
                )
            self.runtime._checkpoint(connection, run_id, "parallel_result_checkpointed")
        self.runtime.events.flush(self.runtime.state)
        self._route(run_id, container, branch_id, nested, result)

    def _route(
        self, run_id: str, container: Node, branch_id: str, nested: Node, result: Result
    ) -> None:
        subgraph = self._subgraph(container, branch_id)
        with self.runtime.state.read_connection() as connection:
            row = connection.execute(
                "SELECT attempt_count FROM parallel_branch_nodes WHERE run_id=? "
                "AND container_node_id=? AND branch_id=? AND node_id=?",
                (run_id, container.node_id, branch_id, nested.node_id),
            ).fetchone()
            counts = {
                (str(item["from_node"]), str(item["to_node"])): int(item["traversal_count"])
                for item in connection.execute(
                    "SELECT from_node,to_node,traversal_count "
                    "FROM parallel_branch_edge_traversals WHERE run_id=? "
                    "AND container_node_id=? AND branch_id=?",
                    (run_id, container.node_id, branch_id),
                )
            }
        if row is None:
            raise RuntimeInvariantError("parallel branch route source is missing")
        result_data = cast(dict[str, Any], json.loads(result.canonical_json()))
        selected: Edge | None = None
        for edge in subgraph.edges:
            if edge.from_node != nested.node_id:
                continue
            if (
                edge.max_iterations is not None
                and counts.get((edge.from_node, edge.to_node), 0) >= edge.max_iterations
            ):
                continue
            if edge.condition is None or self.runtime._condition_matches(
                edge, result_data, int(row["attempt_count"])
            ):
                selected = edge
                break
        if selected is not None:
            with self.runtime.state.transaction() as connection:
                if self.runtime._required_run(connection, run_id)["barrier"] is not None:
                    return
                is_repair = (
                    selected.max_iterations is not None
                    and str(result_data.get("status")) == "failed"
                )
                if is_repair:
                    budget = connection.execute(
                        "SELECT repair_iterations,max_repair_iterations "
                        "FROM budgets WHERE run_id=?",
                        (run_id,),
                    ).fetchone()
                    if budget is None or int(budget["repair_iterations"]) >= int(
                        budget["max_repair_iterations"]
                    ):
                        exhausted = True
                    else:
                        exhausted = False
                        connection.execute(
                            "UPDATE budgets SET repair_iterations=repair_iterations+1 "
                            "WHERE run_id=?",
                            (run_id,),
                        )
                        connection.execute(
                            "UPDATE parallel_branch_nodes SET "
                            "repair_iterations=repair_iterations+1 "
                            "WHERE run_id=? AND container_node_id=? AND branch_id=? AND node_id=?",
                            (run_id, container.node_id, branch_id, nested.node_id),
                        )
                else:
                    exhausted = False
                if exhausted:
                    pass
                else:
                    connection.execute(
                        "INSERT INTO parallel_branch_edge_traversals("
                        "run_id,container_node_id,branch_id,from_node,to_node,traversal_count) "
                        "VALUES (?,?,?,?,?,1) ON CONFLICT("
                        "run_id,container_node_id,branch_id,from_node,to_node) "
                        "DO UPDATE SET traversal_count=traversal_count+1",
                        (
                            run_id,
                            container.node_id,
                            branch_id,
                            selected.from_node,
                            selected.to_node,
                        ),
                    )
                    connection.execute(
                        "UPDATE parallel_branch_nodes SET route_resolved=1 WHERE run_id=? "
                        "AND container_node_id=? AND branch_id=? AND node_id=?",
                        (run_id, container.node_id, branch_id, nested.node_id),
                    )
                    connection.execute(
                        "UPDATE parallel_branch_nodes SET status='ready',result_json=NULL,"
                        "route_resolved=0 WHERE run_id=? AND container_node_id=? AND branch_id=? "
                        "AND node_id=?",
                        (run_id, container.node_id, branch_id, selected.to_node),
                    )
                    connection.execute(
                        "UPDATE parallel_branches SET current_node_id=? WHERE run_id=? "
                        "AND container_node_id=? AND branch_id=?",
                        (selected.to_node, run_id, container.node_id, branch_id),
                    )
                    self.runtime._checkpoint(connection, run_id, "parallel_route_selected")
            if exhausted:
                self._block_branch(
                    run_id, container.node_id, branch_id, "shared repair budget exhausted"
                )
            return
        self._finish_branch(run_id, container.node_id, branch_id, result)

    def _finish_branch(
        self, run_id: str, container_node_id: str, branch_id: str, result: Result
    ) -> None:
        status = self._branch_status(result)
        with self.runtime.state.read_connection() as connection:
            rows = list(
                connection.execute(
                    "SELECT node_id,status,result_json FROM parallel_branch_nodes WHERE run_id=? "
                    "AND container_node_id=? AND branch_id=? ORDER BY node_id",
                    (run_id, container_node_id, branch_id),
                )
            )
        payloads = [
            cast(dict[str, Any], json.loads(str(row["result_json"])))
            for row in rows
            if row["result_json"] is not None
        ]
        changed_files = sorted(
            {str(path) for payload in payloads for path in payload.get("changed_files", [])}
        )
        artifacts = {
            artifact.artifact_id: artifact
            for payload in payloads
            for artifact in self._result_artifacts(payload)
        }
        failure_details: list[str] = []
        error = None
        if isinstance(result, ExecutorResult):
            if result.failure_reason:
                failure_details.append(result.failure_reason)
            error = result.error
        elif isinstance(result, VerifierResult):
            failure_details.extend(result.failure_details)
            error = result.error
        branch_result = BranchResult(
            schema_version="1.0",
            branch_id=branch_id,
            status=status,
            summary=result.summary,
            completed_node_ids=sorted(
                str(row["node_id"]) for row in rows if str(row["status"]) == "succeeded"
            ),
            changed_files=changed_files,
            artifacts=[artifacts[key] for key in sorted(artifacts)],
            failure_details=failure_details,
            error=error,
        )
        with self.runtime.state.transaction() as connection:
            connection.execute(
                "UPDATE parallel_branches SET status=?,current_node_id=NULL,result_json=?,"
                "finished_at=? WHERE run_id=? AND container_node_id=? AND branch_id=?",
                (
                    status.value,
                    branch_result.canonical_json(),
                    timestamp(),
                    run_id,
                    container_node_id,
                    branch_id,
                ),
            )
            self.runtime._checkpoint(connection, run_id, "parallel_branch_finished")
            self.runtime.state.enqueue_event(
                connection,
                "branch.finished",
                run_id,
                node_id=container_node_id,
                payload={"branch_id": branch_id, "status": status.value},
            )
        self.runtime.events.flush(self.runtime.state)

    def _continue_external(
        self,
        run_id: str,
        container: Node,
        branch_id: str,
        nested: Node,
        qualified: Node,
    ) -> None:
        with self.runtime.state.read_connection() as connection:
            handle = connection.execute(
                "SELECT handle,verifier_id,verifier_revision FROM external_handles "
                "WHERE run_id=? AND node_id=?",
                (run_id, qualified.node_id),
            ).fetchone()
            attempt = connection.execute(
                "SELECT attempt_id FROM parallel_branch_attempts WHERE run_id=? "
                "AND container_node_id=? AND branch_id=? AND node_id=? "
                "ORDER BY attempt_number DESC LIMIT 1",
                (run_id, container.node_id, branch_id, nested.node_id),
            ).fetchone()
        if handle is None or handle["handle"] is None or attempt is None:
            self._block_branch(
                run_id,
                container.node_id,
                branch_id,
                "external trigger outcome is uncertain",
                error_status=True,
            )
            return
        query_for = getattr(self.runtime.verifier, "query_for", None)
        if callable(query_for) and handle["verifier_id"] is not None:
            result = query_for(
                str(handle["verifier_id"]),
                int(handle["verifier_revision"]),
                str(handle["handle"]),
            )
        else:
            result = self.runtime.verifier.query(str(handle["handle"]))
        self._persist_result(
            run_id,
            container,
            branch_id,
            nested,
            qualified,
            str(attempt["attempt_id"]),
            result,
        )

    def _block_branch(
        self,
        run_id: str,
        container_node_id: str,
        branch_id: str,
        reason: str,
        *,
        error_status: bool = False,
    ) -> None:
        status = BranchStatus.ERROR if error_status else BranchStatus.BLOCKED
        error = Error(
            schema_version="1.0",
            kind=ErrorKind.INFRASTRUCTURE,
            code="parallel.external_uncertain" if error_status else "parallel.budget_exhausted",
            message=reason,
            retryable=False,
        )
        result = BranchResult(
            schema_version="1.0",
            branch_id=branch_id,
            status=status,
            summary=reason,
            error=error,
        )
        with self.runtime.state.transaction() as connection:
            connection.execute(
                "UPDATE parallel_branches SET status=?,current_node_id=NULL,result_json=?,"
                "finished_at=? WHERE run_id=? AND container_node_id=? AND branch_id=?",
                (
                    status.value,
                    result.canonical_json(),
                    timestamp(),
                    run_id,
                    container_node_id,
                    branch_id,
                ),
            )
            self.runtime._checkpoint(connection, run_id, "parallel_branch_blocked")

    @staticmethod
    def _branch_status(result: Result) -> BranchStatus:
        if isinstance(result, ExecutorResult):
            return BranchStatus(result.status.value)
        if not isinstance(result, VerifierResult):
            raise RuntimeInvariantError("parallel aggregate cannot finish a branch")
        mapping = {
            VerifierStatus.PASSED: BranchStatus.SUCCEEDED,
            VerifierStatus.FAILED: BranchStatus.FAILED,
            VerifierStatus.ERROR: BranchStatus.ERROR,
            VerifierStatus.CANCELLED: BranchStatus.CANCELLED,
        }
        if result.status is VerifierStatus.PENDING:
            raise RuntimeInvariantError("pending result cannot finish a branch")
        return mapping[result.status]

    @staticmethod
    def _subgraph_result(branch: BranchResult) -> ExecutorResult:
        if branch.status is BranchStatus.SUCCEEDED:
            return ExecutorResult(
                schema_version="1.0",
                status=ExecutorStatus.SUCCEEDED,
                summary=branch.summary,
                changed_files=branch.changed_files,
                artifacts=branch.artifacts,
            )
        if branch.status is BranchStatus.FAILED:
            return ExecutorResult(
                schema_version="1.0",
                status=ExecutorStatus.FAILED,
                summary=branch.summary,
                failure_reason="; ".join(branch.failure_details),
                changed_files=branch.changed_files,
                artifacts=branch.artifacts,
            )
        if branch.status is BranchStatus.CANCELLED:
            return ExecutorResult(
                schema_version="1.0",
                status=ExecutorStatus.CANCELLED,
                summary=branch.summary,
                changed_files=branch.changed_files,
                artifacts=branch.artifacts,
            )
        assert branch.error is not None
        return ExecutorResult(
            schema_version="1.0",
            status=ExecutorStatus.ERROR,
            summary=branch.summary,
            changed_files=branch.changed_files,
            artifacts=branch.artifacts,
            error=branch.error,
        )

    @staticmethod
    def _node(subgraph: Subgraph, node_id: str) -> Node:
        for node in subgraph.nodes:
            if node.node_id == node_id:
                return node
        raise RuntimeInvariantError(f"subgraph node is missing: {node_id}")

    @staticmethod
    def _subgraph(container: Node, branch_id: str) -> Subgraph:
        if container.node_type is NodeType.SUBGRAPH:
            assert container.subgraph is not None
            return container.subgraph
        assert container.parallel is not None
        for branch in container.parallel.branches:
            if branch.branch_id == branch_id:
                return branch.subgraph
        raise RuntimeInvariantError(f"parallel branch is missing: {branch_id}")

    @staticmethod
    def _result_artifacts(payload: dict[str, Any]) -> list[Any]:
        from graph_engineering.models import Artifact

        return [Artifact.model_validate(value) for value in payload.get("artifacts", [])]
