"""Compile a frozen TaskContract into the standard serial Execution Graph."""

from __future__ import annotations

from graph_engineering.models import (
    ContractRef,
    Edge,
    ExecutionGraph,
    Node,
    RouteCondition,
    TaskContract,
)
from graph_engineering.models.contract import ContractStatus
from graph_engineering.models.graph import NodeType, RouteField, RouteOperator


def _status(value: str) -> RouteCondition:
    return RouteCondition(
        schema_version="1.0",
        field=RouteField.RESULT_STATUS,
        operator=RouteOperator.EQUALS,
        value=value,
    )


class ExecutionGraphCompiler:
    def compile(self, contract: TaskContract) -> ExecutionGraph:
        if contract.status is not ContractStatus.FROZEN:
            raise ValueError("only an explicitly frozen Contract can compile an Execution Graph")
        verifiers = sorted(contract.verifiers, key=lambda item: item.verifier_id)
        nodes = [
            Node(
                schema_version="1.0",
                node_id="inspect",
                node_type=NodeType.AGENT,
                objective="Inspect only the Contract-relevant repository surfaces",
            ),
            Node(
                schema_version="1.0",
                node_id="implement",
                node_type=NodeType.AGENT,
                objective=contract.task.description,
            ),
        ]
        nodes.extend(
            Node(
                schema_version="1.0",
                node_id=f"verify.{item.verifier_id}",
                node_type=NodeType.VERIFIER,
                objective=f"Run declared verifier {item.verifier_id}",
                config={
                    "verifier_id": item.verifier_id,
                    "verifier_type": item.verifier_type,
                    "timeout_seconds": item.timeout_seconds,
                },
            )
            for item in verifiers
        )
        nodes.extend(
            [
                Node(
                    schema_version="1.0",
                    node_id="repair",
                    node_type=NodeType.AGENT,
                    objective="Repair only evidence-backed acceptance failures",
                ),
                Node(
                    schema_version="1.0",
                    node_id="review",
                    node_type=NodeType.AGENT,
                    objective="Independently review the frozen Contract and evidence",
                ),
                Node(
                    schema_version="1.0",
                    node_id="deliver",
                    node_type=NodeType.DELIVERY,
                    objective=f"Prepare {contract.delivery.delivery_type.value} delivery",
                ),
            ]
        )
        first_verifier = f"verify.{verifiers[0].verifier_id}"
        edges = [
            Edge(schema_version="1.0", from_node="inspect", to_node="implement"),
            Edge(schema_version="1.0", from_node="implement", to_node=first_verifier),
        ]
        for index, verifier in enumerate(verifiers):
            node_id = f"verify.{verifier.verifier_id}"
            passed_target = (
                f"verify.{verifiers[index + 1].verifier_id}"
                if index + 1 < len(verifiers)
                else "review"
            )
            edges.extend(
                [
                    Edge(
                        schema_version="1.0",
                        from_node=node_id,
                        to_node=passed_target,
                        condition=_status("passed"),
                    ),
                    Edge(
                        schema_version="1.0",
                        from_node=node_id,
                        to_node="repair",
                        condition=_status("failed"),
                        max_iterations=contract.budget.max_repair_iterations or 1,
                    ),
                ]
            )
        edges.extend(
            [
                Edge(schema_version="1.0", from_node="repair", to_node=first_verifier),
                Edge(
                    schema_version="1.0",
                    from_node="review",
                    to_node="deliver",
                    condition=_status("succeeded"),
                ),
            ]
        )
        return ExecutionGraph(
            schema_version="1.0",
            graph_id=f"graph:{contract.contract_id}:{contract.revision}:{contract.sha256()[:16]}",
            contract=ContractRef(
                schema_version="1.0",
                contract_id=contract.contract_id,
                revision=contract.revision,
            ),
            entry_node_id="inspect",
            nodes=nodes,
            edges=edges,
        )
