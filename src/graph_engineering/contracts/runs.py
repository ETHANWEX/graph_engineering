"""Prepared Run creation from frozen Contract revisions."""

from __future__ import annotations

from dataclasses import dataclass

from graph_engineering.compiler import ExecutionGraphCompiler
from graph_engineering.models import ExecutionGraph, RestartFrom, RunRelationship
from graph_engineering.runtime.store import StateStore, timestamp

from .models import FrozenContract


@dataclass(frozen=True)
class PlannedRun:
    run_id: str
    project_id: str
    graph: ExecutionGraph
    relationship: RunRelationship
    restart_from: RestartFrom | None
    status: str


class RunPlanner:
    def __init__(self, state: StateStore, compiler: ExecutionGraphCompiler | None = None) -> None:
        self.state = state
        self.state.migrate()
        self.compiler = compiler or ExecutionGraphCompiler()

    def create(
        self,
        project_id: str,
        frozen: FrozenContract,
        *,
        source_run_id: str | None = None,
        restart_from: RestartFrom | None = None,
        run_id: str | None = None,
    ) -> PlannedRun:
        contract = frozen.contract
        lock = frozen.acceptance_lock
        if (
            lock.contract_id != contract.contract_id
            or lock.contract_revision != contract.revision
            or lock.contract_hash != contract.sha256()
        ):
            raise ValueError("acceptance lock does not match the frozen Contract")
        graph = self.compiler.compile(contract)
        planned_run_id = run_id or f"run:{contract.contract_id}:r{contract.revision}"
        relationship = RunRelationship(
            schema_version="1.0",
            run_id=planned_run_id,
            parent_run_id=source_run_id,
            supersedes_run_id=source_run_id,
        )
        with self.state.transaction() as connection:
            if source_run_id is not None:
                planned_source = connection.execute(
                    "SELECT 1 FROM planned_runs WHERE run_id = ?", (source_run_id,)
                ).fetchone()
                runtime_source = connection.execute(
                    "SELECT 1 FROM runs WHERE run_id = ?", (source_run_id,)
                ).fetchone()
                if planned_source is None and runtime_source is None:
                    raise ValueError("source Run does not exist")
            existing = connection.execute(
                "SELECT graph_hash FROM planned_runs WHERE run_id = ?", (planned_run_id,)
            ).fetchone()
            if existing is None:
                connection.execute(
                    """
                    INSERT INTO planned_runs(
                        run_id, project_id, contract_id, contract_revision, graph_json,
                        graph_hash, parent_run_id, supersedes_run_id, restart_from_json,
                        status, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'prepared', ?)
                    """,
                    (
                        planned_run_id,
                        project_id,
                        contract.contract_id,
                        contract.revision,
                        graph.canonical_json(),
                        graph.sha256(),
                        source_run_id,
                        source_run_id,
                        restart_from.canonical_json() if restart_from is not None else None,
                        timestamp(),
                    ),
                )
                self.state.enqueue_event(
                    connection,
                    "run.prepared",
                    planned_run_id,
                    payload={
                        "contract_id": contract.contract_id,
                        "contract_revision": contract.revision,
                        "parent_run_id": source_run_id,
                        "supersedes_run_id": source_run_id,
                    },
                )
            elif str(existing["graph_hash"]) != graph.sha256():
                raise ValueError("prepared Run ID collision")
        return PlannedRun(
            run_id=planned_run_id,
            project_id=project_id,
            graph=graph,
            relationship=relationship,
            restart_from=restart_from,
            status="prepared",
        )

    def get(self, run_id: str) -> PlannedRun:
        with self.state.read_connection() as connection:
            row = connection.execute(
                "SELECT * FROM planned_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        if row is None:
            raise KeyError(run_id)
        return PlannedRun(
            run_id=str(row["run_id"]),
            project_id=str(row["project_id"]),
            graph=ExecutionGraph.model_validate_json(str(row["graph_json"])),
            relationship=RunRelationship(
                schema_version="1.0",
                run_id=str(row["run_id"]),
                parent_run_id=(
                    str(row["parent_run_id"]) if row["parent_run_id"] is not None else None
                ),
                supersedes_run_id=(
                    str(row["supersedes_run_id"]) if row["supersedes_run_id"] is not None else None
                ),
            ),
            restart_from=(
                RestartFrom.model_validate_json(str(row["restart_from_json"]))
                if row["restart_from_json"] is not None
                else None
            ),
            status=str(row["status"]),
        )
