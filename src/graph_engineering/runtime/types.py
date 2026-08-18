"""Strongly typed internal read models for the Phase 1 Runtime."""

from __future__ import annotations

from dataclasses import dataclass

from graph_engineering.models.common import Budget, RestartFrom, RunRelationship
from graph_engineering.models.reports import BudgetUsage, RunStatus


@dataclass(frozen=True)
class RunSnapshot:
    run_id: str
    run_status: RunStatus
    barrier: str | None
    current_node_id: str | None
    node_states: tuple[tuple[str, str, int], ...]
    started_node_ids: tuple[str, ...]
    edge_traversals: tuple[tuple[str, str, int], ...]
    branch_states: tuple[tuple[str, str, str, str | None], ...]
    budget: Budget
    budget_usage: BudgetUsage
    relationship: RunRelationship
    restart_from: RestartFrom | None

    def execution_fingerprint(self) -> tuple[object, ...]:
        """State that read-only queries are forbidden to mutate."""

        return (
            self.run_status,
            self.barrier,
            self.current_node_id,
            self.node_states,
            self.started_node_ids,
            self.edge_traversals,
            self.branch_states,
            self.budget_usage.executor_calls,
            self.budget_usage.repair_iterations,
            self.budget_usage.cost_units,
            self.relationship.canonical_json(),
            self.restart_from.canonical_json() if self.restart_from is not None else None,
        )
