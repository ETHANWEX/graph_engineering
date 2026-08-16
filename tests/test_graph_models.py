from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from graph_engineering.models import ExecutionGraph, RouteCondition


def test_valid_graph(load_fixture: Any) -> None:
    graph = ExecutionGraph.model_validate(load_fixture("valid/graph.yaml"))
    assert graph.entry_node_id == "implement"
    assert graph.edges[1].condition is not None


def test_invalid_graph_rejects_executable_route_text(load_fixture: Any) -> None:
    with pytest.raises(ValidationError) as error:
        ExecutionGraph.model_validate(load_fixture("invalid/graph.yaml"))

    locations = {tuple(item["loc"]) for item in error.value.errors()}
    assert ("nodes", 0, "node_type") in locations
    assert ("edges", 0, "condition") in locations


def test_route_operator_requires_matching_value_shape() -> None:
    with pytest.raises(ValidationError, match="requires a list value"):
        RouteCondition.model_validate(
            {
                "schema_version": "1.0",
                "field": "result.status",
                "operator": "in",
                "value": "passed",
            }
        )


def test_static_topology_rejects_unknown_nodes(load_fixture: Any) -> None:
    document = load_fixture("valid/graph.yaml")
    document["edges"][0]["to_node"] = "unknown"
    with pytest.raises(ValidationError, match="references unknown node"):
        ExecutionGraph.model_validate(document)
