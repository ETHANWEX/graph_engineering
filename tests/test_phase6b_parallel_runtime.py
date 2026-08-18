from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from runtime_helpers import budget

from graph_engineering.models import (
    ContractRef,
    ControlReason,
    Edge,
    ExecutionGraph,
    ExecutorResult,
    Node,
    RestartFrom,
    RunRelationship,
    StateChangeControlIntent,
    VerifierResult,
)
from graph_engineering.models.common import RestartStrategy
from graph_engineering.models.control import ControlReasonCode, StateChangeAction, Urgency
from graph_engineering.models.graph import NodeType
from graph_engineering.models.results import ExecutorStatus, VerifierStatus
from graph_engineering.runtime import FakeExecutor, FakeVerifier, GraphRuntime

CONTRACT_HASH = "6" * 64


def succeeded(summary: str = "done") -> ExecutorResult:
    return ExecutorResult(schema_version="1.0", status=ExecutorStatus.SUCCEEDED, summary=summary)


def failed(summary: str = "failed") -> ExecutorResult:
    return ExecutorResult(
        schema_version="1.0",
        status=ExecutorStatus.FAILED,
        summary=summary,
        failure_reason=summary,
    )


class ConcurrencyExecutor(FakeExecutor):
    def __init__(self, scripts: dict[str, list[ExecutorResult]], delays: dict[str, float]) -> None:
        super().__init__(scripts)
        self.delays = delays
        self.active = 0
        self.maximum = 0
        self.lock = threading.Lock()

    def execute(self, run_id: str, node: Any, attempt_id: str) -> ExecutorResult:
        with self.lock:
            self.active += 1
            self.maximum = max(self.maximum, self.active)
        try:
            time.sleep(self.delays.get(node.node_id, 0))
            return super().execute(run_id, node, attempt_id)
        finally:
            with self.lock:
                self.active -= 1


def definition(load_fixture: Any) -> ExecutionGraph:
    return ExecutionGraph.model_validate(load_fixture("phase6b/parallel-graph.yaml"))


def intent(run_id: str, action: StateChangeAction) -> StateChangeControlIntent:
    return StateChangeControlIntent(
        schema_version="1.0",
        intent_kind="state_change",
        intent_id=f"intent:{run_id}:{action.value}",
        source_message_id=f"message:{run_id}:{action.value}",
        actor_id="human",
        project_id="project",
        run_id=run_id,
        action=action,
        reason=ControlReason(schema_version="1.0", code=ControlReasonCode.HUMAN_REQUEST),
        urgency=Urgency.IMMEDIATE,
        confidence=1,
        requires_confirmation=False,
    )


def test_bounded_concurrency_and_deterministic_join(tmp_path: Path, load_fixture: Any) -> None:
    aggregates: list[str] = []
    for name, delays in (
        ("alpha-first", {"fanout.alpha.work": 0.10, "fanout.beta.work": 0.20}),
        ("beta-first", {"fanout.alpha.work": 0.20, "fanout.beta.work": 0.10}),
    ):
        executor = ConcurrencyExecutor(
            {
                "fanout.alpha.work": [succeeded("alpha")],
                "fanout.beta.work": [succeeded("beta")],
            },
            delays,
        )
        runtime = GraphRuntime(tmp_path / name, executor=executor, verifier=FakeVerifier())
        runtime.create_run("run-1", "project", definition(load_fixture), CONTRACT_HASH, budget())
        assert runtime.run("run-1").value == "succeeded"
        aggregates.append(runtime.node_result("run-1", "join").canonical_json())
        assert executor.maximum == 2

    assert aggregates[0] == aggregates[1]


def test_failure_and_atomic_shared_budget_cannot_be_offset(
    tmp_path: Path, load_fixture: Any
) -> None:
    executor = ConcurrencyExecutor(
        {
            "fanout.alpha.work": [failed("alpha failed")],
            "fanout.beta.work": [succeeded("beta")],
        },
        {},
    )
    runtime = GraphRuntime(tmp_path / "failure", executor=executor, verifier=FakeVerifier())
    runtime.create_run("run-f", "project", definition(load_fixture), CONTRACT_HASH, budget(calls=1))

    assert runtime.run("run-f").value == "failed"
    aggregate = runtime.node_result("run-f", "join")
    assert aggregate.status.value != "succeeded"
    assert runtime.snapshot("run-f").budget_usage.executor_calls == 1


def test_restart_skips_completed_branch_work(tmp_path: Path, load_fixture: Any) -> None:
    graph = definition(load_fixture)
    parallel_spec = graph.nodes[0].parallel
    assert parallel_spec is not None
    alpha = parallel_spec.branches[0]
    beta = parallel_spec.branches[1]
    beta_graph = beta.subgraph.model_copy(
        update={
            "nodes": [
                *beta.subgraph.nodes,
                beta.subgraph.nodes[0].model_copy(
                    update={"node_id": "finish", "objective": "Finish beta"}
                ),
            ],
            "edges": [
                Edge(
                    schema_version="1.0",
                    from_node="work",
                    to_node="finish",
                )
            ],
        }
    )
    graph = graph.model_copy(
        update={
            "nodes": [
                graph.nodes[0].model_copy(
                    update={
                        "parallel": parallel_spec.model_copy(
                            update={
                                "branches": [
                                    alpha,
                                    beta.model_copy(update={"subgraph": beta_graph}),
                                ]
                            }
                        )
                    }
                ),
                graph.nodes[1],
            ]
        }
    )
    first = FakeExecutor(
        {
            "fanout.alpha.work": [succeeded("alpha")],
            "fanout.beta.work": [succeeded("beta work")],
        }
    )
    runtime = GraphRuntime(tmp_path, executor=first, verifier=FakeVerifier())
    runtime.create_run("run-r", "project", graph, CONTRACT_HASH, budget())
    runtime.run("run-r", max_steps=1)

    resumed_executor = FakeExecutor({"fanout.beta.finish": [succeeded("beta finish")]})
    resumed = GraphRuntime(tmp_path, executor=resumed_executor, verifier=FakeVerifier())
    resumed.recover("run-r", graph, CONTRACT_HASH)
    assert resumed.run("run-r").value == "succeeded"
    assert [call.node_id for call in resumed_executor.calls] == ["fanout.beta.finish"]


def test_parallel_external_handle_recovery_polls_without_retrigger(
    tmp_path: Path, load_fixture: Any
) -> None:
    graph = definition(load_fixture)
    parallel = graph.nodes[0]
    parallel_spec = parallel.parallel
    assert parallel_spec is not None
    alpha = parallel_spec.branches[0]
    verifier_node = alpha.subgraph.nodes[0].model_copy(
        update={"node_type": NodeType.VERIFIER, "config": {"external": True}}
    )
    alpha = alpha.model_copy(
        update={"subgraph": alpha.subgraph.model_copy(update={"nodes": [verifier_node]})}
    )
    graph = graph.model_copy(
        update={
            "nodes": [
                parallel.model_copy(
                    update={
                        "parallel": parallel_spec.model_copy(
                            update={
                                "max_concurrency": 1,
                                "branches": [alpha, parallel_spec.branches[1]],
                            }
                        )
                    }
                ),
                graph.nodes[1],
            ]
        }
    )
    verifier = FakeVerifier(
        {
            "fanout.alpha.work": [
                VerifierResult(
                    schema_version="1.0",
                    status=VerifierStatus.PENDING,
                    summary="pending",
                    external_handle="external-alpha",
                )
            ]
        },
        query_results={
            "external-alpha": [
                VerifierResult(schema_version="1.0", status=VerifierStatus.PASSED, summary="passed")
            ]
        },
    )
    runtime = GraphRuntime(tmp_path, executor=FakeExecutor(), verifier=verifier)
    runtime.create_run("run-e", "project", graph, CONTRACT_HASH, budget())
    runtime.run("run-e", max_steps=1)
    assert verifier.trigger_count == 1

    recovered = GraphRuntime(
        tmp_path,
        executor=FakeExecutor({"fanout.beta.work": [succeeded("beta")]}),
        verifier=verifier,
    )
    recovered.recover("run-e", graph, CONTRACT_HASH)
    assert recovered.run("run-e").value == "succeeded"
    assert verifier.trigger_count == 1
    assert verifier.query_count == 1


def test_explicit_subgraph_executes_through_durable_branch_state(
    tmp_path: Path, load_fixture: Any
) -> None:
    parallel = definition(load_fixture).nodes[0]
    parallel_spec = parallel.parallel
    assert parallel_spec is not None
    subgraph = parallel_spec.branches[0].subgraph
    graph = ExecutionGraph(
        schema_version="1.0",
        graph_id="explicit-subgraph",
        contract=ContractRef(schema_version="1.0", contract_id="contract", revision=1),
        entry_node_id="container",
        nodes=[
            Node(
                schema_version="1.0",
                node_id="container",
                node_type=NodeType.SUBGRAPH,
                objective="Run explicit subgraph",
                subgraph=subgraph,
            )
        ],
    )
    executor = FakeExecutor({"container.subgraph.work": [succeeded("subgraph done")]})
    runtime = GraphRuntime(tmp_path, executor=executor, verifier=FakeVerifier())
    runtime.create_run("run-s", "project", graph, CONTRACT_HASH, budget())

    assert runtime.run("run-s").value == "succeeded"
    assert runtime.snapshot("run-s").branch_states[0][2] == "succeeded"


def test_pause_and_interrupt_barriers_cover_active_and_pending_branches(
    tmp_path: Path, load_fixture: Any
) -> None:
    graph = definition(load_fixture)
    parallel_spec = graph.nodes[0].parallel
    assert parallel_spec is not None
    graph = graph.model_copy(
        update={
            "nodes": [
                graph.nodes[0].model_copy(
                    update={"parallel": parallel_spec.model_copy(update={"max_concurrency": 1})}
                ),
                graph.nodes[1],
            ]
        }
    )
    pause_executor = FakeExecutor(
        {
            "fanout.alpha.work": [succeeded("alpha")],
            "fanout.beta.work": [succeeded("beta")],
        }
    )
    paused = GraphRuntime(tmp_path / "pause", executor=pause_executor, verifier=FakeVerifier())
    paused.create_run("run-p", "project", graph, CONTRACT_HASH, budget())
    pause_executor.after_execute = lambda _: paused.control(
        intent("run-p", StateChangeAction.PAUSE)
    )
    assert paused.run("run-p").value == "paused"
    assert [call.node_id for call in pause_executor.calls] == ["fanout.alpha.work"]
    assert [state[2] for state in paused.snapshot("run-p").branch_states] == [
        "succeeded",
        "pending",
    ]
    pause_executor.after_execute = None
    paused.control(intent("run-p", StateChangeAction.RESUME))
    assert paused.run("run-p").value == "succeeded"

    interrupt_executor = FakeExecutor(
        {
            "fanout.alpha.work": [succeeded("alpha")],
            "fanout.beta.work": [succeeded("beta")],
        }
    )
    interrupted = GraphRuntime(
        tmp_path / "interrupt", executor=interrupt_executor, verifier=FakeVerifier()
    )
    interrupted.create_run("run-i", "project", graph, CONTRACT_HASH, budget())
    interrupt_executor.after_execute = lambda _: interrupted.control(
        intent("run-i", StateChangeAction.INTERRUPT)
    )
    assert interrupted.run("run-i").value == "interrupted"
    assert [call.node_id for call in interrupt_executor.calls] == ["fanout.alpha.work"]
    assert interrupted.snapshot("run-i").branch_states[1][2] == "cancelled"


def test_resume_routes_checkpointed_branch_result_without_reexecution(
    tmp_path: Path, load_fixture: Any
) -> None:
    graph = definition(load_fixture)
    parallel_spec = graph.nodes[0].parallel
    assert parallel_spec is not None
    alpha = parallel_spec.branches[0]
    alpha_graph = alpha.subgraph.model_copy(
        update={
            "nodes": [
                *alpha.subgraph.nodes,
                alpha.subgraph.nodes[0].model_copy(
                    update={"node_id": "finish", "objective": "Finish alpha"}
                ),
            ],
            "edges": [Edge(schema_version="1.0", from_node="work", to_node="finish")],
        }
    )
    graph = graph.model_copy(
        update={
            "nodes": [
                graph.nodes[0].model_copy(
                    update={
                        "parallel": parallel_spec.model_copy(
                            update={
                                "max_concurrency": 1,
                                "branches": [
                                    alpha.model_copy(update={"subgraph": alpha_graph}),
                                    parallel_spec.branches[1],
                                ],
                            }
                        )
                    }
                ),
                graph.nodes[1],
            ]
        }
    )
    executor = FakeExecutor(
        {
            "fanout.alpha.work": [succeeded("alpha work")],
            "fanout.alpha.finish": [succeeded("alpha finish")],
            "fanout.beta.work": [succeeded("beta")],
        }
    )
    runtime = GraphRuntime(tmp_path, executor=executor, verifier=FakeVerifier())
    runtime.create_run("run-route", "project", graph, CONTRACT_HASH, budget())
    executor.after_execute = lambda call: (
        runtime.control(intent("run-route", StateChangeAction.PAUSE))
        if call.node_id == "fanout.alpha.work"
        else None
    )

    assert runtime.run("run-route").value == "paused"
    executor.after_execute = None
    runtime.control(intent("run-route", StateChangeAction.RESUME))
    assert runtime.run("run-route").value == "succeeded"
    assert [call.node_id for call in executor.calls] == [
        "fanout.alpha.work",
        "fanout.alpha.finish",
        "fanout.beta.work",
    ]


def test_interrupt_settles_active_branch_with_unstarted_followup(
    tmp_path: Path, load_fixture: Any
) -> None:
    graph = definition(load_fixture)
    parallel_spec = graph.nodes[0].parallel
    assert parallel_spec is not None
    alpha = parallel_spec.branches[0]
    alpha_graph = alpha.subgraph.model_copy(
        update={
            "nodes": [
                *alpha.subgraph.nodes,
                alpha.subgraph.nodes[0].model_copy(
                    update={"node_id": "finish", "objective": "Must not start"}
                ),
            ],
            "edges": [Edge(schema_version="1.0", from_node="work", to_node="finish")],
        }
    )
    graph = graph.model_copy(
        update={
            "nodes": [
                graph.nodes[0].model_copy(
                    update={
                        "parallel": parallel_spec.model_copy(
                            update={
                                "max_concurrency": 1,
                                "branches": [
                                    alpha.model_copy(update={"subgraph": alpha_graph}),
                                    parallel_spec.branches[1],
                                ],
                            }
                        )
                    }
                ),
                graph.nodes[1],
            ]
        }
    )
    executor = FakeExecutor(
        {
            "fanout.alpha.work": [succeeded("alpha checkpointed")],
            "fanout.alpha.finish": [succeeded("must not start")],
            "fanout.beta.work": [succeeded("must not start")],
        }
    )
    runtime = GraphRuntime(tmp_path, executor=executor, verifier=FakeVerifier())
    runtime.create_run("run-active-i", "project", graph, CONTRACT_HASH, budget())
    executor.after_execute = lambda _: runtime.control(
        intent("run-active-i", StateChangeAction.INTERRUPT)
    )

    assert runtime.run("run-active-i").value == "interrupted"
    assert [call.node_id for call in executor.calls] == ["fanout.alpha.work"]
    assert [state[2] for state in runtime.snapshot("run-active-i").branch_states] == [
        "cancelled",
        "cancelled",
    ]


def test_cancel_barrier_cancels_pending_branches_before_any_effect(
    tmp_path: Path, load_fixture: Any
) -> None:
    executor = FakeExecutor(
        {
            "fanout.alpha.work": [succeeded()],
            "fanout.beta.work": [succeeded()],
        }
    )
    runtime = GraphRuntime(tmp_path, executor=executor, verifier=FakeVerifier())
    runtime.create_run("run-c", "project", definition(load_fixture), CONTRACT_HASH, budget())
    runtime.cancel("run-c")

    assert runtime.final_report("run-c").terminal_status.value == "cancelled"
    assert executor.calls == []
    assert {state[2] for state in runtime.snapshot("run-c").branch_states} == {"cancelled"}


def test_cancel_barrier_durably_cancels_active_and_pending_branches(
    tmp_path: Path, load_fixture: Any
) -> None:
    graph = definition(load_fixture)
    parallel_spec = graph.nodes[0].parallel
    assert parallel_spec is not None
    graph = graph.model_copy(
        update={
            "nodes": [
                graph.nodes[0].model_copy(
                    update={"parallel": parallel_spec.model_copy(update={"max_concurrency": 1})}
                ),
                graph.nodes[1],
            ]
        }
    )
    executor = FakeExecutor(
        {
            "fanout.alpha.work": [succeeded("late alpha")],
            "fanout.beta.work": [succeeded("must not start")],
        }
    )
    runtime = GraphRuntime(tmp_path, executor=executor, verifier=FakeVerifier())
    runtime.create_run("run-active-c", "project", graph, CONTRACT_HASH, budget())
    executor.after_execute = lambda _: runtime.cancel("run-active-c")

    assert runtime.run("run-active-c").value == "cancelled"
    assert [call.node_id for call in executor.calls] == ["fanout.alpha.work"]
    assert [state[2] for state in runtime.snapshot("run-active-c").branch_states] == [
        "cancelled",
        "cancelled",
    ]


def test_concurrent_cost_reservations_never_overspend(tmp_path: Path, load_fixture: Any) -> None:
    runtime = GraphRuntime(tmp_path, executor=FakeExecutor(), verifier=FakeVerifier())
    runtime.create_run(
        "run-b",
        "project",
        definition(load_fixture),
        CONTRACT_HASH,
        budget(cost=5),
    )
    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(
            pool.map(
                lambda number: runtime.reserve_cost("run-b", f"reservation:{number}", 1),
                range(40),
            )
        )

    assert sum(results) == 5
    assert runtime.snapshot("run-b").budget_usage.cost_units == 5
    accepted = results.index(True)
    assert runtime.reserve_cost("run-b", f"reservation:{accepted}", 1) is True


def test_checkpoint_child_inherits_completed_branches_without_side_effects(
    tmp_path: Path, load_fixture: Any
) -> None:
    graph = definition(load_fixture)
    parent_executor = FakeExecutor(
        {
            "fanout.alpha.work": [succeeded("alpha")],
            "fanout.beta.work": [succeeded("beta")],
        }
    )
    parent = GraphRuntime(tmp_path, executor=parent_executor, verifier=FakeVerifier())
    parent.create_run("run-parent", "project", graph, CONTRACT_HASH, budget())
    assert parent.run("run-parent").value == "succeeded"
    checkpoint = parent.latest_checkpoint("run-parent")

    child_executor = FakeExecutor()
    child = GraphRuntime(tmp_path, executor=child_executor, verifier=FakeVerifier())
    child.create_run(
        "run-child",
        "project",
        graph,
        CONTRACT_HASH,
        budget(),
        RunRelationship(schema_version="1.0", run_id="run-child", parent_run_id="run-parent"),
        RestartFrom(
            schema_version="1.0",
            strategy=RestartStrategy.CHECKPOINT,
            reference=checkpoint,
        ),
    )

    assert child.run("run-child").value == "succeeded"
    assert child_executor.calls == []
    assert {state[2] for state in child.snapshot("run-child").branch_states} == {"succeeded"}


def test_migration_8_is_repeatable_and_keeps_phase6a_compatibility(tmp_path: Path) -> None:
    runtime = GraphRuntime(tmp_path, executor=FakeExecutor(), verifier=FakeVerifier())
    runtime.state.migrate()

    assert runtime.state.parallel_migration_version == 8
    assert runtime.state.service_migration_version == 7
    with runtime.state.read_connection() as connection:
        versions = [row[0] for row in connection.execute("SELECT version FROM schema_migrations")]
    assert versions == list(range(1, 9))
