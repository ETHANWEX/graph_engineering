"""Execution Graph protocol and deterministic static validation."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import Field, model_validator

from .common import Budget, ContractRef, ProtocolModel, SchemaVersion


class NodeType(StrEnum):
    AGENT = "agent"
    COMMAND = "command"
    VERIFIER = "verifier"
    ROUTER = "router"
    DELIVERY = "delivery"


class RouteField(StrEnum):
    RESULT_STATUS = "result.status"
    RESULT_RETRYABLE = "result.retryable"
    ATTEMPT_NUMBER = "attempt.number"


class RouteOperator(StrEnum):
    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    IN = "in"
    NOT_IN = "not_in"


RouteScalar = str | int | bool


class RouteCondition(ProtocolModel):
    """Restricted comparison; it is data, never executable source code."""

    schema_version: SchemaVersion
    field: RouteField
    operator: RouteOperator
    value: RouteScalar | list[RouteScalar]

    @model_validator(mode="after")
    def operator_matches_value(self) -> RouteCondition:
        is_collection_operator = self.operator in {RouteOperator.IN, RouteOperator.NOT_IN}
        if is_collection_operator and not isinstance(self.value, list):
            raise ValueError(f"operator {self.operator.value} requires a list value")
        if not is_collection_operator and isinstance(self.value, list):
            raise ValueError(f"operator {self.operator.value} requires a scalar value")
        if isinstance(self.value, list) and not self.value:
            raise ValueError("route condition list value must not be empty")
        return self


class Node(ProtocolModel):
    schema_version: SchemaVersion
    node_id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_.-]+$")
    node_type: NodeType
    objective: str = Field(min_length=1)
    config: dict[str, Any] = Field(default_factory=dict)
    budget: Budget | None = None


class Edge(ProtocolModel):
    schema_version: SchemaVersion
    from_node: str = Field(min_length=1)
    to_node: str = Field(min_length=1)
    condition: RouteCondition | None = None
    max_iterations: int | None = Field(default=None, ge=1)


class ExecutionGraph(ProtocolModel):
    schema_version: SchemaVersion
    graph_id: str = Field(min_length=1)
    contract: ContractRef
    entry_node_id: str = Field(min_length=1)
    nodes: list[Node] = Field(min_length=1)
    edges: list[Edge] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_static_topology(self) -> ExecutionGraph:
        node_ids = [node.node_id for node in self.nodes]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("node IDs must be unique")
        known = set(node_ids)
        if self.entry_node_id not in known:
            raise ValueError("entry_node_id must reference an existing node")
        for index, edge in enumerate(self.edges):
            if edge.from_node not in known:
                raise ValueError(f"edges[{index}].from_node references unknown node")
            if edge.to_node not in known:
                raise ValueError(f"edges[{index}].to_node references unknown node")
            if edge.from_node == edge.to_node:
                raise ValueError(f"edges[{index}] must not be a self-loop")
        return self
