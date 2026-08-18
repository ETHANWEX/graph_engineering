from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from graph_engineering.models import ExecutionGraph
from graph_engineering.models.graph import NodeType


def test_explicit_parallel_subgraphs_and_join_validate(load_fixture: Any) -> None:
    graph = ExecutionGraph.model_validate(load_fixture("phase6b/parallel-graph.yaml"))

    assert graph.nodes[0].node_type is NodeType.PARALLEL
    assert graph.nodes[0].parallel is not None
    assert [branch.branch_id for branch in graph.nodes[0].parallel.branches] == ["alpha", "beta"]
    assert graph.nodes[1].join is not None
    assert graph.nodes[1].join.parallel_node_id == "fanout"


def test_invalid_parallel_shape_fails_closed(load_fixture: Any) -> None:
    with pytest.raises(ValidationError):
        ExecutionGraph.model_validate(load_fixture("phase6b/invalid-parallel-graph.yaml"))


def test_serial_graph_canonical_bytes_remain_unchanged(load_fixture: Any) -> None:
    document = load_fixture("runtime/serial-graph.yaml")
    graph = ExecutionGraph.model_validate(document)

    assert graph.sha256() == "77b93993133ef786a481bb954db31c8ed4aca26fe54195cafbdaff36e7b3f267"
