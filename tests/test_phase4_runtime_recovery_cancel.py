from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

from runtime_helpers import budget, graph

from graph_engineering.contracts import ContractRepository
from graph_engineering.models import HumanMessage, StateChangeControlIntent
from graph_engineering.models.control import (
    ControlReason,
    ControlReasonCode,
    StateChangeAction,
    Urgency,
)
from graph_engineering.models.graph import NodeType
from graph_engineering.runtime import ArtifactStore, FakeExecutor, GraphRuntime, StateStore
from graph_engineering.verifier import (
    HttpPipelineSpec,
    HttpPipelineVerifier,
    HttpRequestSpec,
    HttpResponse,
    HttpStatusMapping,
    RuntimeVerifierAdapter,
    VerifierLifecycle,
    VerifierManifest,
    VerifierRepository,
)

CONTRACT_HASH = "a" * 64


class FixtureTransport:
    def __init__(self, responses: list[HttpResponse]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, str]] = []

    def request(
        self, method: str, url: str, headers: Mapping[str, str], body: bytes | None, timeout: float
    ) -> HttpResponse:
        self.calls.append((method, url))
        return self.responses.pop(0)


def response(value: object) -> HttpResponse:
    return HttpResponse(200, {}, json.dumps(value).encode())


def frozen_http(
    tmp_path: Path, transport: FixtureTransport
) -> tuple[VerifierRepository, HttpPipelineVerifier]:
    manifest = VerifierManifest.model_validate(
        {
            "verifier_id": "ci",
            "revision": 1,
            "verifier_type": "builtin/http-pipeline",
            "runtime": "http",
            "capabilities": {"network": {"allow": ["ci.example.test"]}},
            "external_side_effects": True,
        }
    )
    source = tmp_path / "manifest-source.json"
    tests = tmp_path / "manifest-tests.json"
    source.write_text(manifest.model_dump_json(), encoding="utf-8")
    tests.write_text("{}", encoding="utf-8")
    state = StateStore(tmp_path / "runtime" / "state.db")
    contracts = ContractRepository(state)
    draft = contracts.example_draft("contract-1", "CI acceptance", "pytest")
    requirement = draft.verifiers[0].model_copy(
        update={"verifier_id": "ci", "verifier_type": "builtin/http-pipeline"}
    )
    criterion = draft.acceptance_criteria[0].model_copy(update={"verifier_refs": ["ci"]})
    draft = draft.model_copy(
        update={"verifiers": [requirement], "acceptance_criteria": [criterion]}
    )
    draft_id = contracts.stage("conversation", draft)
    contracts.freeze(
        draft_id,
        HumanMessage(
            schema_version="1.0",
            message_id="contract-confirm",
            actor_id="human",
            project_id="project",
            content="confirm",
            created_at=datetime(2026, 8, 18, tzinfo=UTC),
        ),
    )
    repository = VerifierRepository(state)
    repository.stage(manifest, source=source, tests=tests)
    for lifecycle in (
        VerifierLifecycle.VALIDATED,
        VerifierLifecycle.TESTED,
        VerifierLifecycle.DRY_RUN,
    ):
        repository.record("ci", 1, lifecycle, {"passed": True})
    repository.freeze(
        "ci",
        1,
        contract_id="contract-1",
        contract_revision=1,
        confirmation_message_id="human-confirm",
    )
    verifier = HttpPipelineVerifier(
        manifest,
        HttpPipelineSpec(
            trigger=HttpRequestSpec(method="POST", url="https://ci.example.test/runs"),
            external_id_path="id",
            poll=HttpRequestSpec(url="https://ci.example.test/runs/${external_id}"),
            statuses=HttpStatusMapping(
                json_path="status", pending=("pending",), passed=("passed",), failed=("failed",)
            ),
            cancel=HttpRequestSpec(
                method="POST", url="https://ci.example.test/runs/${external_id}/cancel"
            ),
            backoff_seconds=0,
        ),
        ArtifactStore(tmp_path / "runtime" / "artifacts"),
        transport=transport,
        sleep=lambda _: None,
    )
    return repository, verifier


def test_runtime_checkpoints_handle_and_restart_polls_without_retrigger(tmp_path: Path) -> None:
    transport = FixtureTransport([response({"id": "ext-1"}), response({"status": "passed"})])
    repository, verifier = frozen_http(tmp_path, transport)
    adapter = RuntimeVerifierAdapter(
        repository,
        {("ci", 1): verifier},
        working_directory=tmp_path,
        artifact_directory=tmp_path / "runtime" / "artifacts",
    )
    definition = graph(
        [
            (
                "ci",
                NodeType.VERIFIER,
                {"external": True, "verifier_id": "ci", "verifier_revision": 1},
            )
        ],
        [],
    )
    runtime = GraphRuntime(tmp_path / "runtime", executor=FakeExecutor(), verifier=adapter)
    runtime.create_run("run-1", "project", definition, CONTRACT_HASH, budget())
    runtime.run("run-1", max_steps=1)
    with runtime.state.read_connection() as connection:
        row = connection.execute(
            "SELECT handle, trigger_state FROM external_handles WHERE run_id = 'run-1'"
        ).fetchone()
    assert row is not None and row["handle"] == "ext-1" and row["trigger_state"] == "checkpointed"

    restarted_verifier = HttpPipelineVerifier(
        verifier.manifest,
        verifier.spec,
        ArtifactStore(tmp_path / "runtime" / "artifacts"),
        transport=transport,
        sleep=lambda _: None,
    )
    restarted_adapter = RuntimeVerifierAdapter(
        repository,
        {("ci", 1): restarted_verifier},
        working_directory=tmp_path,
        artifact_directory=tmp_path / "runtime" / "artifacts",
    )
    recovered = GraphRuntime(
        tmp_path / "runtime", executor=FakeExecutor(), verifier=restarted_adapter
    )
    recovered.recover("run-1", definition, CONTRACT_HASH)
    assert recovered.run("run-1").value == "succeeded"
    assert transport.calls == [
        ("POST", "https://ci.example.test/runs"),
        ("GET", "https://ci.example.test/runs/ext-1"),
    ]


def interrupt(run_id: str) -> StateChangeControlIntent:
    return StateChangeControlIntent(
        schema_version="1.0",
        intent_kind="state_change",
        intent_id="interrupt-1",
        source_message_id="message-1",
        actor_id="human",
        project_id="project",
        run_id=run_id,
        action=StateChangeAction.INTERRUPT,
        reason=ControlReason(
            schema_version="1.0", code=ControlReasonCode.HUMAN_REQUEST, detail="stop"
        ),
        urgency=Urgency.IMMEDIATE,
        confidence=1,
        requires_confirmation=False,
    )


def test_interrupt_persists_barrier_before_cancelling_external_handle(tmp_path: Path) -> None:
    transport = FixtureTransport([response({"id": "ext-1"}), response({"cancelled": True})])
    repository, verifier = frozen_http(tmp_path, transport)
    adapter = RuntimeVerifierAdapter(
        repository,
        {("ci", 1): verifier},
        working_directory=tmp_path,
        artifact_directory=tmp_path / "runtime" / "artifacts",
    )
    definition = graph(
        [
            (
                "ci",
                NodeType.VERIFIER,
                {"external": True, "verifier_id": "ci", "verifier_revision": 1},
            )
        ],
        [],
    )
    runtime = GraphRuntime(tmp_path / "runtime", executor=FakeExecutor(), verifier=adapter)
    runtime.create_run("run-1", "project", definition, CONTRACT_HASH, budget())
    runtime.run("run-1", max_steps=1)
    runtime.control(interrupt("run-1"))
    with runtime.state.read_connection() as connection:
        run = connection.execute("SELECT barrier FROM runs WHERE run_id = 'run-1'").fetchone()
        handle = connection.execute(
            "SELECT cancel_state, residual_effect FROM external_handles WHERE run_id = 'run-1'"
        ).fetchone()
    assert run is not None and run["barrier"] == "interrupt"
    assert handle is not None and handle["cancel_state"] == "cancelled"
    assert handle["residual_effect"] is None
