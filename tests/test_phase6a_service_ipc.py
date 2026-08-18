from __future__ import annotations

import json
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
from pydantic import ValidationError
from runtime_helpers import budget, graph

from graph_engineering.models.graph import NodeType
from graph_engineering.runtime import FakeExecutor, FakeVerifier, GraphRuntime, StateStore
from graph_engineering.service import RuntimeService, ServiceClient, ServiceError
from graph_engineering.service.protocol import IPCRequest


def _start_service(project: Path) -> tuple[RuntimeService, threading.Thread]:
    service = RuntimeService(project, "project")
    thread = threading.Thread(target=service.serve, daemon=True)
    thread.start()
    for _ in range(100):
        if service.endpoint_path.is_file():
            return service, thread
        time.sleep(0.01)
    raise AssertionError("Runtime Service did not publish its endpoint")


def test_migration_7_is_repeatable_and_preserves_phase5_compatibility(tmp_path: Path) -> None:
    state = StateStore(tmp_path / "state.db")
    state.migrate()
    state.migrate()

    assert state.service_migration_version == 7
    assert state.delivery_migration_version == 6
    with state.read_connection() as connection:
        versions = [row[0] for row in connection.execute("SELECT version FROM schema_migrations")]
        columns = {row[1] for row in connection.execute("PRAGMA table_info(pending_confirmations)")}
    assert versions == list(range(1, 8))
    assert {"actor_id", "project_id", "protocol_major", "expires_at"} <= columns


def test_versioned_ipc_fixtures_are_strict(load_fixture: object) -> None:
    assert callable(load_fixture)
    valid = load_fixture("phase6a/ipc-health-request.json")
    assert IPCRequest.model_validate(valid).protocol_version == "1.0"
    with pytest.raises(ValidationError):
        IPCRequest.model_validate(load_fixture("phase6a/ipc-incompatible-request.json"))


def test_service_health_idempotent_replay_conflict_and_controlled_cleanup(
    tmp_path: Path,
) -> None:
    service, thread = _start_service(tmp_path)
    client = ServiceClient(tmp_path)
    health = client.call("health")
    assert health["healthy"] is True
    assert health["versions"] == {"ipc": "1.0", "package": "0.7.0", "runtime_api": "1.0"}

    request_id = "request:start-1"
    key = "idempotency:start-1"
    payload = {"project_id": "project", "actor_id": "human"}
    first = client.call("start", payload, request_id=request_id, idempotency_key=key)
    second = client.call("start", payload, request_id="request:start-replay", idempotency_key=key)
    assert first == second
    with pytest.raises(ServiceError, match="different request"):
        client.call(
            "start",
            {"project_id": "project", "actor_id": "other"},
            request_id=request_id,
            idempotency_key=key,
        )
    with service.gateway.state.read_connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM ipc_mutation_replays").fetchone()[0] == 1

    assert client.call("shutdown")["stopping"] is True
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert not service.endpoint_path.exists()


def test_unauthorized_client_fails_closed_without_echoing_capability(tmp_path: Path) -> None:
    service, thread = _start_service(tmp_path)
    descriptor = json.loads(service.endpoint_path.read_text(encoding="utf-8"))
    real = descriptor["authorization"]
    descriptor["authorization"] = "x" * 48
    service.endpoint_path.write_text(json.dumps(descriptor), encoding="utf-8")
    try:
        with pytest.raises(ServiceError) as caught:
            ServiceClient(tmp_path).call("health")
        assert caught.value.code == "unauthorized"
        assert real not in str(caught.value)
        assert descriptor["authorization"] not in str(caught.value)
    finally:
        descriptor["authorization"] = real
        service.endpoint_path.write_text(json.dumps(descriptor), encoding="utf-8")
        descriptor["versions"]["runtime_api"] = "2.0"
        service.endpoint_path.write_text(json.dumps(descriptor), encoding="utf-8")
        with pytest.raises(RuntimeError, match="API version is incompatible"):
            ServiceClient(tmp_path).call("health")
        descriptor["versions"]["runtime_api"] = "1.0"
        service.endpoint_path.write_text(json.dumps(descriptor), encoding="utf-8")
        ServiceClient(tmp_path).call("shutdown")
        thread.join(timeout=5)


def test_message_is_persisted_once_across_ipc_replay(tmp_path: Path) -> None:
    service, thread = _start_service(tmp_path)
    client = ServiceClient(tmp_path)
    started = client.call("start", {"project_id": "project", "actor_id": "human"})
    payload = {
        "conversation_id": started["conversation_id"],
        "message_id": "message:stable",
        "content": "please do something unclear",
    }
    first = client.call(
        "message", payload, request_id="request:message", idempotency_key="idempotency:message"
    )
    second = client.call(
        "message", payload, request_id="request:message", idempotency_key="idempotency:message"
    )
    assert first == second
    with service.gateway.state.read_connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM human_messages").fetchone()[0] == 1
    client.call("shutdown")
    thread.join(timeout=5)


def test_query_is_read_only_and_pause_establishes_barrier_before_work(tmp_path: Path) -> None:
    run_id = "run-1"
    run_root = tmp_path / ".ge" / "runs" / run_id
    executor = FakeExecutor()
    runtime = GraphRuntime(run_root, executor=executor, verifier=FakeVerifier())
    runtime.create_run(
        run_id,
        "project",
        graph([("one", NodeType.AGENT, None)], []),
        "b" * 64,
        budget(),
    )
    service, thread = _start_service(tmp_path)
    client = ServiceClient(tmp_path)
    started = client.call("start", {"project_id": "project", "actor_id": "human"})
    service.gateway.conversations.set_active_run(started["conversation_id"], run_id)

    before = runtime.snapshot(run_id).execution_fingerprint()
    with runtime.state.read_connection() as connection:
        outbox_before = connection.execute("SELECT COUNT(*) FROM event_outbox").fetchone()[0]
    queried = client.call(
        "message",
        {"conversation_id": started["conversation_id"], "content": "status"},
    )
    assert queried["applied"] is True
    assert runtime.snapshot(run_id).execution_fingerprint() == before
    with runtime.state.read_connection() as connection:
        outbox_after = connection.execute("SELECT COUNT(*) FROM event_outbox").fetchone()[0]
    assert outbox_after == outbox_before

    paused = client.call(
        "message",
        {"conversation_id": started["conversation_id"], "content": "pause"},
    )
    assert paused["applied"] is True
    assert runtime.snapshot(run_id).barrier == "pause"
    assert runtime.run(run_id) == "paused"
    assert executor.calls == []
    client.call("shutdown")
    thread.join(timeout=5)


def test_expired_confirmation_fails_closed(tmp_path: Path) -> None:
    run_id = "run-1"
    runtime = GraphRuntime(
        tmp_path / ".ge" / "runs" / run_id,
        executor=FakeExecutor(),
        verifier=FakeVerifier(),
    )
    runtime.create_run(
        run_id,
        "project",
        graph([("one", NodeType.AGENT, None)], []),
        "b" * 64,
        budget(),
    )
    service, thread = _start_service(tmp_path)
    client = ServiceClient(tmp_path)
    started = client.call("start", {"project_id": "project", "actor_id": "human"})
    service.gateway.conversations.set_active_run(started["conversation_id"], run_id)
    pending = client.call(
        "message",
        {"conversation_id": started["conversation_id"], "content": "accept"},
    )
    confirmation_id = pending["pending_confirmation_id"]
    with service.gateway.state.transaction() as connection:
        connection.execute(
            "UPDATE pending_confirmations SET expires_at='2000-01-01T00:00:00+00:00' "
            "WHERE confirmation_id=?",
            (confirmation_id,),
        )
    before = runtime.snapshot(run_id).execution_fingerprint()
    with pytest.raises(ServiceError) as caught:
        client.call(
            "confirm",
            {
                "conversation_id": started["conversation_id"],
                "confirmation_id": confirmation_id,
                "content": "confirm",
            },
        )
    assert caught.value.code == "expired"
    assert runtime.snapshot(run_id).execution_fingerprint() == before
    client.call("shutdown")
    thread.join(timeout=5)


def test_incompatible_ipc_version_has_typed_redacted_error(tmp_path: Path) -> None:
    service, thread = _start_service(tmp_path)
    descriptor = json.loads(service.endpoint_path.read_text(encoding="utf-8"))
    request = {
        "protocol_version": "2.0",
        "request_id": "request:version",
        "idempotency_key": "idempotency:version",
        "project_id": "project",
        "workspace_id": descriptor["workspace_id"],
        "operation": "health",
        "authorization": descriptor["authorization"],
        "payload": {},
    }
    with socket.create_connection((descriptor["host"], descriptor["port"]), timeout=2) as conn:
        conn.sendall(json.dumps(request).encode() + b"\n")
        response = json.loads(conn.makefile("rb").readline())
    assert response["error"]["code"] == "incompatible_version"
    assert descriptor["authorization"] not in json.dumps(response)
    ServiceClient(tmp_path).call("shutdown")
    thread.join(timeout=5)


def test_windows_subprocess_service_lifecycle_and_restart_recovery(tmp_path: Path) -> None:
    command = [
        sys.executable,
        "-m",
        "graph_engineering.cli",
        "service",
        "start",
        "--project-root",
        str(tmp_path),
        "--project-id",
        "project",
    ]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    endpoint = tmp_path / ".ge" / "service" / "endpoint.json"
    try:
        for _ in range(200):
            if endpoint.is_file():
                break
            if process.poll() is not None:
                raise AssertionError(process.stderr.read() if process.stderr else "service exited")
            time.sleep(0.01)
        first = ServiceClient(tmp_path).call(
            "start", {"project_id": "project", "actor_id": "human"}
        )
        ServiceClient(tmp_path).call("shutdown")
        assert process.wait(timeout=5) == 0
        assert not endpoint.exists()

        process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        for _ in range(200):
            if endpoint.is_file():
                break
            time.sleep(0.01)
        recovered = ServiceClient(tmp_path).call(
            "start", {"project_id": "project", "actor_id": "human"}
        )
        assert recovered["conversation_id"] == first["conversation_id"]
        ServiceClient(tmp_path).call("shutdown")
        assert process.wait(timeout=5) == 0
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)


def test_runtime_service_restart_recovers_persisted_run_status(tmp_path: Path) -> None:
    run_id = "run-recovery"
    runtime = GraphRuntime(
        tmp_path / ".ge" / "runs" / run_id,
        executor=FakeExecutor(),
        verifier=FakeVerifier(),
    )
    runtime.create_run(
        run_id,
        "project",
        graph([("one", NodeType.AGENT, None)], []),
        "b" * 64,
        budget(),
    )
    _first_service, first_thread = _start_service(tmp_path)
    first_status = ServiceClient(tmp_path).call("status", {"run_id": run_id})
    ServiceClient(tmp_path).call("shutdown")
    first_thread.join(timeout=5)

    _restarted_service, restarted_thread = _start_service(tmp_path)
    assert ServiceClient(tmp_path).call("status", {"run_id": run_id}) == first_status
    assert runtime.latest_checkpoint(run_id).startswith("checkpoint:")
    ServiceClient(tmp_path).call("shutdown")
    restarted_thread.join(timeout=5)


def test_isolated_mcp_stdio_to_runtime_service_e2e(tmp_path: Path) -> None:
    _service, thread = _start_service(tmp_path)
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "graph_engineering.cli",
            "mcp-server",
            "--project-root",
            str(tmp_path),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert process.stdin is not None
    assert process.stdout is not None
    try:
        calls = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "start",
                    "arguments": {"project_id": "project", "actor_id": "human"},
                },
            },
        ]
        responses = []
        for call in calls:
            process.stdin.write(json.dumps(call) + "\n")
            process.stdin.flush()
            responses.append(json.loads(process.stdout.readline()))
        assert responses[0]["result"]["serverInfo"]["version"] == "1.0"
        assert len(responses[1]["result"]["tools"]) == 5
        assert responses[2]["result"]["isError"] is False
    finally:
        process.stdin.close()
        assert process.wait(timeout=5) == 0
        ServiceClient(tmp_path).call("shutdown")
        thread.join(timeout=5)
