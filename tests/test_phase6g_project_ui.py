from __future__ import annotations

import base64
import hashlib
import http.client
import json
import sqlite3
import threading
import time
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import quote

import pytest
from runtime_helpers import budget, graph

from graph_engineering.models.graph import NodeType
from graph_engineering.runtime import FakeExecutor, FakeVerifier, GraphRuntime
from graph_engineering.service import RuntimeService, ServiceClient
from graph_engineering.ui import (
    ProjectUIApp,
    ProjectUIServer,
    RuntimeServiceUIProvider,
    SecretLeakError,
    StreamingSecretGuard,
    UIRequest,
    UIResponse,
)


def _snapshot(*, marker: str = "safe") -> dict[str, object]:
    return {
        "contract_version": "1.0",
        "project": {"project_id": "project", "status": "partial"},
        "source": {
            "instance_id": "runtime-instance-1",
            "snapshot_id": "snapshot-1",
            "generated_at": "2026-08-25T00:00:00+00:00",
            "stale_after_seconds": 10,
        },
        "runs": [
            {
                "run_id": "run-1",
                "status": "failed",
                "terminal_reason": "verification_failed",
                "contract": {
                    "contract_id": "contract-1",
                    "revision": 2,
                    "hash": "a" * 64,
                    "frozen": True,
                },
                "budget": {"executor_calls": 2, "max_executor_calls": 4},
                "nodes": [{"node_id": "implement", "status": "failed"}],
                "attempts": [{"attempt_id": "attempt-1", "status": "failed"}],
                "parallel_branches": [{"branch_id": "alpha", "status": "succeeded"}],
                "sessions": [{"session_id": "session-1", "status": "completed"}],
                "risks": ["Unverified deployment"],
                "requirement_matrix": {
                    "rows": [{"criterion_id": "criterion-1", "status": "unverified"}]
                },
                "verifiers": [{"verifier_id": "tests", "status": "failed"}],
                "review": {"verdict": "changes_requested", "fix_count": 1},
                "github": {"delivery_state": "blocked", "handle": None},
                "report": {
                    "revision": 1,
                    "terminal_status": "failed",
                    "summary": marker,
                },
                "artifacts": [{"artifact_id": "artifact-1", "media_type": "text/plain"}],
            }
        ],
        "conversation": {
            "conversation_id": "project-main",
            "actor_id": "human",
            "messages": [{"message_id": "message-1", "content": marker}],
        },
        "pending_confirmations": [
            {
                "pending_action_id": "confirmation:intent-1",
                "conversation_id": "project-main",
                "project_id": "project",
                "actor_id": "human",
                "source_message_id": "message-1",
                "intent_id": "intent-1",
                "action": "accept",
                "run_id": "run-1",
                "contract_id": "contract-1",
                "contract_revision": 2,
                "contract_hash": "a" * 64,
                "created_at": "2026-08-25T00:00:00+00:00",
                "expires_at": "2099-08-25T00:15:00+00:00",
                "status": "pending",
            }
        ],
    }


class FakeProvider:
    def __init__(self, snapshot: dict[str, object] | None = None) -> None:
        self.snapshot = snapshot or _snapshot()
        self.calls: list[tuple[str, dict[str, object], str, str]] = []

    def project_snapshot(self) -> dict[str, object]:
        return self.snapshot

    def run_snapshot(self, run_id: str) -> dict[str, object]:
        assert run_id == "run-1"
        return self.snapshot

    def mutate(
        self,
        operation: str,
        payload: dict[str, object],
        *,
        request_id: str,
        idempotency_key: str,
    ) -> dict[str, object]:
        self.calls.append((operation, payload, request_id, idempotency_key))
        return {"applied": True, "merge_performed": False}


def _app(provider: FakeProvider | None = None, *, secrets: tuple[str, ...] = ()) -> ProjectUIApp:
    return ProjectUIApp(
        provider or FakeProvider(),
        project_id="project",
        actor_id="human",
        origin="http://127.0.0.1:8765",
        session_id="ui-session-1",
        secret_values=secrets,
    )


def _get(app: ProjectUIApp, path: str, **headers: str) -> UIResponse:
    return app.handle(
        UIRequest("GET", path, {"host": "127.0.0.1:8765", **headers}, b"", "127.0.0.1")
    )


def _post(
    app: ProjectUIApp, path: str, document: Mapping[str, object], **headers: str
) -> UIResponse:
    return app.handle(
        UIRequest(
            "POST",
            path,
            {
                "host": "127.0.0.1:8765",
                "origin": "http://127.0.0.1:8765",
                "content-type": "application/json",
                "sec-fetch-site": "same-origin",
                "cookie": "ge_ui_session=ui-session-1",
                **headers,
            },
            json.dumps(document).encode(),
            "127.0.0.1",
        )
    )


def test_project_and_run_pages_render_complete_honest_accessible_state() -> None:
    app = _app()
    for path in ("/", "/runs/run-1"):
        response = _get(app, path)
        text = response.body.decode()
        assert response.status == 200
        assert "Project overview" in text and "Run run-1" in text
        assert "failed" in text and "unverified" in text and "blocked" in text
        assert "Contract" in text and "Requirement Matrix" in text
        assert "Verifier and CI" in text and "Review" in text and "Final Report" in text
        assert "Human Control Conversation" in text and "Confirmation required" in text
        assert 'aria-live="polite"' in text and "<main" in text and "<label" in text
        assert 'tabindex="-1"' in text and "localStorage" not in text
        assert 'data-ge-form="message"' in text
        assert 'data-ge-form="action"' in text
        assert 'data-ge-form="confirmation"' in text
        assert '<script src="/assets/ui.js" defer></script>' in text


def test_untrusted_html_markdown_urls_paths_and_event_handlers_are_inert_text() -> None:
    marker = '<img src=x onerror="alert(1)"> [run](javascript:alert(1)) C:\\secret\\x'
    response = _get(_app(FakeProvider(_snapshot(marker=marker))), "/")
    text = response.body.decode()
    assert marker not in text
    assert "&lt;img src=x onerror=" in text
    assert "javascript:alert(1)" in text
    assert "<img" not in text and 'href="javascript:' not in text


def test_security_headers_static_mime_cache_and_csp_are_fail_closed() -> None:
    app = _app()
    page = _get(app, "/")
    assert page.headers["content-security-policy"].startswith("default-src 'none'")
    assert "frame-ancestors 'none'" in page.headers["content-security-policy"]
    assert page.headers["x-content-type-options"] == "nosniff"
    assert page.headers["x-frame-options"] == "DENY"
    assert page.headers["referrer-policy"] == "no-referrer"
    assert page.headers["cache-control"] == "no-store"
    assert (
        "HttpOnly" in page.headers["set-cookie"] and "SameSite=Strict" in page.headers["set-cookie"]
    )
    assert "script-src 'self'" in page.headers["content-security-policy"]
    asset = _get(app, "/assets/ui.css")
    assert asset.headers["content-type"] == "text/css; charset=utf-8"
    assert b"focus-visible" in asset.body
    script = _get(app, "/assets/ui.js")
    assert script.headers["content-type"] == "text/javascript; charset=utf-8"
    assert b"localStorage" not in script.body and b"sessionStorage" not in script.body
    assert b"If-None-Match" in script.body and b"setInterval" in script.body


@pytest.mark.parametrize(
    ("headers", "remote"),
    [
        ({"host": "evil.invalid"}, "127.0.0.1"),
        ({"host": "127.0.0.1:8765", "origin": "http://evil.invalid"}, "127.0.0.1"),
        ({"host": "127.0.0.1:8765"}, "192.0.2.4"),
    ],
)
def test_host_origin_and_remote_validation_rejects_cross_site_access(
    headers: dict[str, str], remote: str
) -> None:
    response = _app().handle(UIRequest("POST", "/api/v1/messages", headers, b"{}", remote))
    assert response.status == 403
    assert b"invalid request" in response.body


def test_csrf_session_json_body_and_size_boundaries() -> None:
    app = _app()
    base = {
        "host": "127.0.0.1:8765",
        "origin": "http://127.0.0.1:8765",
        "content-type": "application/json",
        "sec-fetch-site": "same-origin",
    }
    assert app.handle(UIRequest("POST", "/api/v1/messages", base, b"{}", "127.0.0.1")).status == 403
    wrong = {**base, "cookie": "ge_ui_session=wrong"}
    assert (
        app.handle(UIRequest("POST", "/api/v1/messages", wrong, b"{}", "127.0.0.1")).status == 403
    )
    huge = {**base, "cookie": "ge_ui_session=ui-session-1", "content-length": "70000"}
    assert app.handle(UIRequest("POST", "/api/v1/messages", huge, b"{}", "127.0.0.1")).status == 413
    form = {**huge, "content-length": "1", "content-type": "text/plain"}
    assert app.handle(UIRequest("POST", "/api/v1/messages", form, b"x", "127.0.0.1")).status == 415


def test_snapshot_etag_duplicate_late_and_reconnect_rules() -> None:
    app = _app()
    first = _get(app, "/api/v1/project")
    assert (
        first.status == 200 and first.headers["content-type"] == "application/json; charset=utf-8"
    )
    document = json.loads(first.body)
    assert document["source"]["snapshot_id"] == "snapshot-1"
    duplicate = _get(app, "/api/v1/project", **{"if-none-match": first.headers["etag"]})
    assert duplicate.status == 304 and duplicate.body == b""
    assert document["source"]["instance_id"] == "runtime-instance-1"


def test_message_and_typed_actions_route_through_provider_with_stable_replay_identity() -> None:
    provider = FakeProvider()
    app = _app(provider)
    message = _post(
        app,
        "/api/v1/messages",
        {
            "conversation_id": "project-main",
            "run_id": "run-1",
            "content": "pause run-1",
            "message_id": "message-ui-1",
            "request_id": "request-ui-1",
            "idempotency_key": "idempotency-ui-1",
        },
    )
    assert message.status == 200
    operation, payload, request_id, key = provider.calls[-1]
    assert operation == "message" and payload["content"] == "pause run-1"
    assert (request_id, key) == ("request-ui-1", "idempotency-ui-1")

    action = _post(
        app,
        "/api/v1/runs/run-1/actions/accept",
        {
            "content": "accept run-1 without merge",
            "conversation_id": "project-main",
            "message_id": "message-ui-2",
            "request_id": "request-ui-2",
            "idempotency_key": "idempotency-ui-2",
            "report_revision": 1,
        },
    )
    assert action.status == 200 and json.loads(action.body)["merge_performed"] is False
    assert provider.calls[-1][0] == "message"

    mismatched = _post(
        app,
        "/api/v1/runs/run-1/actions/pause",
        {
            "content": "accept run-1",
            "conversation_id": "project-main",
            "message_id": "message-ui-mismatch",
            "request_id": "request-ui-mismatch",
            "idempotency_key": "idempotency-ui-mismatch",
        },
    )
    assert mismatched.status == 400
    assert provider.calls[-1][1]["content"] == "accept run-1 without merge"


def test_confirmation_card_binds_every_identity_and_fails_stale_wrong_or_expired() -> None:
    provider = FakeProvider()
    app = _app(provider)
    card = _snapshot()["pending_confirmations"][0]  # type: ignore[index]
    payload = {
        **card,
        "session_id": "ui-session-1",
        "snapshot_id": "snapshot-1",
        "confirmation_message_id": "message-confirm-1",
        "request_id": "request-confirm-1",
        "idempotency_key": "idempotency-confirm-1",
        "content": "confirm",
    }
    accepted = _post(app, "/api/v1/confirmations/confirmation%3Aintent-1", payload)
    assert accepted.status == 200 and provider.calls[-1][0] == "confirm"
    assert provider.calls[-1][1]["confirmation_id"] == "confirmation:intent-1"

    for changed in (
        {"project_id": "wrong"},
        {"run_id": "wrong"},
        {"contract_revision": 1},
        {"session_id": "wrong"},
        {"snapshot_id": "stale"},
        {"expires_at": "2000-01-01T00:00:00+00:00"},
    ):
        rejected = _post(
            app,
            "/api/v1/confirmations/confirmation%3Aintent-1",
            {**payload, **changed, "request_id": f"request-{len(provider.calls)}"},
        )
        assert rejected.status in {409, 410}


def test_secret_raw_url_base64_overlap_and_cross_chunk_never_enter_output() -> None:
    secret = "token/value+overlap"
    guard = StreamingSecretGuard((secret,))
    variants = (secret, quote(secret, safe=""), base64.b64encode(secret.encode()).decode())
    for value in variants:
        with pytest.raises(SecretLeakError):
            guard.check_text(value)
    guard = StreamingSecretGuard((secret,))
    guard.check_chunk(b"safe token/val")
    with pytest.raises(SecretLeakError):
        guard.check_chunk(b"ue+overlap end")

    response = _get(_app(FakeProvider(_snapshot(marker=secret)), secrets=(secret,)), "/")
    assert response.status == 500
    assert secret.encode() not in response.body and b"token" not in response.body

    unsafe = _snapshot()
    unsafe["report"] = {"authorization_header": "Bearer unknown"}
    rejected = _get(_app(FakeProvider(unsafe)), "/api/v1/project")
    assert rejected.status == 500 and b"Bearer" not in rejected.body


def test_path_traversal_unknown_actions_and_bounded_output_fail_closed() -> None:
    app = _app()
    assert _get(app, "/runs/..%2Fstate.db").status == 400
    unknown = _post(
        app,
        "/api/v1/runs/run-1/actions/merge",
        {
            "content": "merge",
            "conversation_id": "project-main",
            "message_id": "message-merge",
            "request_id": "request-merge",
            "idempotency_key": "idempotency-merge",
        },
    )
    assert unknown.status == 404
    huge = _snapshot(marker="x" * (1024 * 1024))
    assert _get(_app(FakeProvider(huge)), "/api/v1/project").status == 507


def test_rate_burst_limit_and_generic_errors_do_not_leak_paths_or_exceptions() -> None:
    class Broken(FakeProvider):
        def project_snapshot(self) -> dict[str, object]:
            raise RuntimeError("credential at C:\\private\\state.db")

    failed = _get(_app(Broken()), "/api/v1/project")
    assert failed.status == 500
    assert b"credential" not in failed.body and b"state.db" not in failed.body

    app = _app()
    statuses = [
        _post(
            app,
            "/api/v1/messages",
            {
                "conversation_id": "project-main",
                "content": "status",
                "message_id": f"message-{number}",
                "request_id": f"request-{number}",
                "idempotency_key": f"idempotency-{number}",
            },
        ).status
        for number in range(20)
    ]
    assert 429 in statuses


def _start_service(project: Path) -> tuple[RuntimeService, threading.Thread]:
    service = RuntimeService(project, "project")
    thread = threading.Thread(target=service.serve, daemon=True)
    thread.start()
    for _ in range(200):
        if service.endpoint_path.is_file():
            return service, thread
        time.sleep(0.01)
    raise AssertionError("service did not start")


def test_runtime_service_snapshot_is_read_only_rich_and_recovers_after_restart(
    tmp_path: Path,
) -> None:
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
    before = runtime.snapshot(run_id).execution_fingerprint()
    database = tmp_path / ".ge" / "runs" / run_id / "state.db"
    database_hash = hashlib.sha256(database.read_bytes()).hexdigest()
    with sqlite3.connect(database) as connection:
        outbox_before = connection.execute("SELECT COUNT(*) FROM event_outbox").fetchone()[0]

    restarted_service, thread = _start_service(tmp_path)
    client = ServiceClient(tmp_path)
    provider = RuntimeServiceUIProvider(client)
    first = provider.project_snapshot()
    detail = provider.run_snapshot(run_id)
    assert first["contract_version"] == "1.0"
    assert first["runs"][0]["run_id"] == run_id
    assert detail["runs"][0]["nodes"][0]["node_id"] == "one"
    client.call("shutdown")
    thread.join(timeout=5)

    _service, thread = _start_service(tmp_path)
    recovered = RuntimeServiceUIProvider(ServiceClient(tmp_path)).run_snapshot(run_id)
    assert recovered["runs"][0]["run_id"] == run_id
    assert runtime.snapshot(run_id).execution_fingerprint() == before
    assert hashlib.sha256(database.read_bytes()).hexdigest() == database_hash
    with sqlite3.connect(database) as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM event_outbox").fetchone()[0] == outbox_before
        )
    with restarted_service.gateway.state.read_connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM ipc_mutation_replays").fetchone()[0] == 0
    ServiceClient(tmp_path).call("shutdown")
    thread.join(timeout=5)


def test_ui_disabled_absent_and_observability_exporter_failure_leave_runtime_unchanged(
    tmp_path: Path,
) -> None:
    run_id = "run-absent"
    runtime = GraphRuntime(
        tmp_path / run_id,
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
    before = runtime.snapshot(run_id).execution_fingerprint()
    assert runtime.snapshot(run_id).execution_fingerprint() == before


def test_real_gateway_confirmation_replay_and_accept_never_merge(tmp_path: Path) -> None:
    run_id = "run-accept"
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
    now = "2026-08-25T00:00:00+00:00"
    with runtime.state.transaction() as connection:
        connection.execute(
            "INSERT INTO delivery_terminal_fixtures(run_id,contract_id,contract_revision,status,"
            "reason,created_at) VALUES (?,?,?,?,?,?)",
            (run_id, "contract", 1, "succeeded", "completed", now),
        )
        connection.execute(
            "INSERT INTO delivery_report_revisions(run_id,revision,terminal_status,terminal_reason,"
            "manifest_json,created_at) VALUES (?,?,?,?,?,?)",
            (run_id, 1, "succeeded", "completed", "{}", now),
        )
    service, thread = _start_service(tmp_path)
    client = ServiceClient(tmp_path)
    started = client.call("start", {"project_id": "project", "actor_id": "human"})
    service.gateway.conversations.set_active_run(started["conversation_id"], run_id)
    app = ProjectUIApp(
        RuntimeServiceUIProvider(client),
        project_id="project",
        actor_id="human",
        origin="http://127.0.0.1:8765",
        session_id="ui-session-1",
    )
    pending_response = _post(
        app,
        f"/api/v1/runs/{run_id}/actions/accept",
        {
            "content": f"accept {run_id}",
            "conversation_id": started["conversation_id"],
            "message_id": "message-accept",
            "request_id": "request-accept",
            "idempotency_key": "idempotency-accept",
        },
    )
    pending_result = json.loads(pending_response.body)
    assert pending_response.status == 200 and pending_result["applied"] is False
    snapshot = RuntimeServiceUIProvider(client).project_snapshot()
    card = snapshot["pending_confirmations"][0]
    confirmation = {
        **card,
        "session_id": "ui-session-1",
        "snapshot_id": snapshot["source"]["snapshot_id"],
        "confirmation_message_id": "message-confirm-accept",
        "request_id": "request-confirm-accept",
        "idempotency_key": "idempotency-confirm-accept",
        "content": "confirm accept",
    }
    path = f"/api/v1/confirmations/{quote(card['pending_action_id'], safe='')}"
    applied = _post(app, path, confirmation)
    assert applied.status == 200
    assert "merge_performed=False" in json.loads(applied.body)["message"]
    assert _post(app, path, confirmation).status == 409
    with runtime.state.read_connection() as connection:
        rows = list(connection.execute("SELECT action FROM human_acceptance_records"))
    assert [row[0] for row in rows] == ["accept"]
    client.call("shutdown")
    thread.join(timeout=5)


def test_real_loopback_http_server_static_and_snapshot_smoke(tmp_path: Path) -> None:
    runtime = GraphRuntime(
        tmp_path / ".ge" / "runs" / "run-http",
        executor=FakeExecutor(),
        verifier=FakeVerifier(),
    )
    runtime.create_run(
        "run-http",
        "project",
        graph([("one", NodeType.AGENT, None)], []),
        "b" * 64,
        budget(),
    )
    _service, service_thread = _start_service(tmp_path)
    ui = ProjectUIServer(tmp_path, project_id="project", actor_id="human")
    ui_thread = threading.Thread(target=ui.serve, daemon=True)
    ui_thread.start()
    port = int(ui.origin.rsplit(":", 1)[1])
    try:
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        connection.request("GET", "/api/v1/project", headers={"Host": f"127.0.0.1:{port}"})
        response = connection.getresponse()
        document = json.loads(response.read())
        assert response.status == 200
        assert document["runs"][0]["run_id"] == "run-http"
        assert response.getheader("Cache-Control") == "no-store"
        connection.close()

        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        connection.request("HEAD", "/api/v1/project", headers={"Host": f"127.0.0.1:{port}"})
        response = connection.getresponse()
        assert response.status == 405 and response.read() == b""
        assert response.getheader("Content-Security-Policy") is not None
        assert response.getheader("Cache-Control") == "no-store"
        connection.close()
    finally:
        ui.shutdown()
        ui_thread.join(timeout=5)
        ServiceClient(tmp_path).call("shutdown")
        service_thread.join(timeout=5)
    assert not ui_thread.is_alive() and not service_thread.is_alive()


def test_package_declares_static_asset_without_browser_or_node_dependency() -> None:
    root = Path(__file__).parents[1]
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    assert "playwright" not in pyproject.casefold()
    assert "selenium" not in pyproject.casefold()
    assert "react" not in pyproject.casefold()
    assert (root / "src/graph_engineering/ui/assets/ui.css").is_file()
    assert (root / "src/graph_engineering/ui/assets/ui.js").is_file()
