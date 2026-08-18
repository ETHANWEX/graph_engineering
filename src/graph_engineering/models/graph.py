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
    PARALLEL = "parallel"
    SUBGRAPH = "subgraph"
    JOIN = "join"


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
    subgraph: Subgraph | None = None
    parallel: ParallelSpec | None = None
    join: JoinSpec | None = None

    @model_validator(mode="after")
    def typed_definition_matches_node_type(self) -> Node:
        definitions = {
            NodeType.SUBGRAPH: self.subgraph,
            NodeType.PARALLEL: self.parallel,
            NodeType.JOIN: self.join,
        }
        expected = definitions.get(self.node_type)
        if self.node_type in definitions and expected is None:
            raise ValueError(f"{self.node_type.value} node requires its typed definition")
        if self.node_type not in definitions and any(
            value is not None for value in definitions.values()
        ):
            raise ValueError(
                "serial node kinds cannot carry subgraph, parallel, or join definitions"
            )
        for node_type, value in definitions.items():
            if value is not None and node_type is not self.node_type:
                raise ValueError(f"{node_type.value} definition does not match node_type")
        return self


class Edge(ProtocolModel):
    schema_version: SchemaVersion
    from_node: str = Field(min_length=1)
    to_node: str = Field(min_length=1)
    condition: RouteCondition | None = None
    max_iterations: int | None = Field(default=None, ge=1)


class Subgraph(ProtocolModel):
    schema_version: SchemaVersion
    subgraph_id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_.-]+$")
    entry_node_id: str = Field(min_length=1)
    nodes: list[Node] = Field(min_length=1)
    edges: list[Edge] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_serial_topology(self) -> Subgraph:
        node_ids = [node.node_id for node in self.nodes]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("subgraph node IDs must be unique")
        known = set(node_ids)
        if self.entry_node_id not in known:
            raise ValueError("subgraph entry_node_id must reference an existing node")
        for node in self.nodes:
            if node.node_type in {NodeType.PARALLEL, NodeType.SUBGRAPH, NodeType.JOIN}:
                raise ValueError("nested container nodes are outside Phase 6B")
        for index, edge in enumerate(self.edges):
            if edge.from_node not in known or edge.to_node not in known:
                raise ValueError(f"subgraph edges[{index}] references an unknown node")
            if edge.from_node == edge.to_node:
                raise ValueError(f"subgraph edges[{index}] must not be a self-loop")
        return self


class ParallelBranch(ProtocolModel):
    schema_version: SchemaVersion
    branch_id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_.-]+$")
    subgraph: Subgraph


class ParallelSpec(ProtocolModel):
    schema_version: SchemaVersion
    max_concurrency: int = Field(ge=1, le=64)
    branches: list[ParallelBranch] = Field(min_length=2)

    @model_validator(mode="after")
    def branch_ids_are_unique(self) -> ParallelSpec:
        branch_ids = [branch.branch_id for branch in self.branches]
        if len(branch_ids) != len(set(branch_ids)):
            raise ValueError("parallel branch IDs must be unique")
        return self


class JoinSpec(ProtocolModel):
    schema_version: SchemaVersion
    parallel_node_id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_.-]+$")


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
        by_id = {node.node_id: node for node in self.nodes}
        for node in self.nodes:
            if node.node_type is not NodeType.JOIN:
                continue
            assert node.join is not None
            source = by_id.get(node.join.parallel_node_id)
            if source is None or source.node_type is not NodeType.PARALLEL:
                raise ValueError(f"join node {node.node_id} must reference a parallel node")
            if not any(
                edge.from_node == source.node_id and edge.to_node == node.node_id
                for edge in self.edges
            ):
                raise ValueError(
                    f"join node {node.node_id} requires an edge from its parallel node"
                )
        return self


Node.model_rebuild()
Subgraph.model_rebuild()
ParallelBranch.model_rebuild()
ParallelSpec.model_rebuild()
