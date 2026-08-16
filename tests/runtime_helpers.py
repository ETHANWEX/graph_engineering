from __future__ import annotations

from collections.abc import Sequence

from graph_engineering.models import (
    Budget,
    ContractRef,
    Edge,
    ExecutionGraph,
    Node,
    RouteCondition,
)
from graph_engineering.models.graph import NodeType, RouteField, RouteOperator


def budget(
    *,
    calls: int = 20,
    repairs: int = 5,
    duration: int = 3600,
    cost: float | None = None,
) -> Budget:
    return Budget(
        schema_version="1.0",
        max_duration_seconds=duration,
        max_executor_calls=calls,
        max_repair_iterations=repairs,
        max_cost_units=cost,
    )


def graph(
    nodes: Sequence[tuple[str, NodeType, dict[str, object] | None]],
    edges: Sequence[tuple[str, str, RouteCondition | None, int | None]],
    *,
    graph_id: str = "graph-1",
) -> ExecutionGraph:
    return ExecutionGraph(
        schema_version="1.0",
        graph_id=graph_id,
        contract=ContractRef(schema_version="1.0", contract_id="contract-1", revision=1),
        entry_node_id=nodes[0][0],
        nodes=[
            Node(
                schema_version="1.0",
                node_id=node_id,
                node_type=node_type,
                objective=node_id,
                config=config or {},
            )
            for node_id, node_type, config in nodes
        ],
        edges=[
            Edge(
                schema_version="1.0",
                from_node=source,
                to_node=target,
                condition=condition,
                max_iterations=max_iterations,
            )
            for source, target, condition, max_iterations in edges
        ],
    )


def status_is(value: str) -> RouteCondition:
    return RouteCondition(
        schema_version="1.0",
        field=RouteField.RESULT_STATUS,
        operator=RouteOperator.EQUALS,
        value=value,
    )
