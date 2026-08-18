from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar

from graph_engineering.discovery import plan_http_pipeline
from graph_engineering.runtime import ArtifactStore
from graph_engineering.verifier import (
    HttpPipelineSpec,
    HttpPipelineVerifier,
    HttpRequestSpec,
    HttpStatusMapping,
    VerifierManifest,
    VerifierRequest,
)


class PipelineHandler(BaseHTTPRequestHandler):
    polls: ClassVar[int] = 0
    triggers: ClassVar[int] = 0

    def do_POST(self) -> None:
        if self.path == "/runs":
            type(self).triggers += 1
            self._json({"run": {"id": "fixture-1"}})
            return
        if self.path == "/runs/fixture-1/cancel":
            self._json({"cancelled": True})
            return
        self.send_error(404)

    def do_GET(self) -> None:
        if self.path == "/runs/fixture-1":
            type(self).polls += 1
            status = "queued" if type(self).polls == 1 else "passed"
            self._json({"run": {"status": status}})
            return
        if self.path == "/runs/fixture-1/report":
            content = b"fixture-secret report"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return
        self.send_error(404)

    def log_message(self, format: str, *args: object) -> None:
        return

    def _json(self, value: object) -> None:
        content = json.dumps(value).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)


def test_discovery_prefers_declarative_http_when_complete() -> None:
    decision = plan_http_pipeline(
        trigger_url="http://127.0.0.1/runs",
        poll_url="http://127.0.0.1/runs/${external_id}",
        external_id_path="run.id",
        status_path="run.status",
    )
    assert decision.declarative is True and decision.http_pipeline is not None
    incomplete = plan_http_pipeline(
        trigger_url=None, poll_url=None, external_id_path=None, status_path=None
    )
    assert incomplete.declarative is False and incomplete.http_pipeline is None


def test_local_isolated_http_pipeline_trigger_poll_report_e2e(tmp_path: Path) -> None:
    PipelineHandler.polls = 0
    PipelineHandler.triggers = 0
    server = ThreadingHTTPServer(("127.0.0.1", 0), PipelineHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        manifest = VerifierManifest.model_validate(
            {
                "verifier_id": "local-ci",
                "revision": 1,
                "verifier_type": "builtin/http-pipeline",
                "runtime": "http",
                "capabilities": {
                    "network": {"allow": ["127.0.0.1"]},
                    "secrets": ["FIXTURE_TOKEN"],
                },
                "external_side_effects": True,
            }
        )
        verifier = HttpPipelineVerifier(
            manifest,
            HttpPipelineSpec(
                trigger=HttpRequestSpec(method="POST", url=f"{base}/runs"),
                external_id_path="run.id",
                poll=HttpRequestSpec(url=f"{base}/runs/${{external_id}}"),
                statuses=HttpStatusMapping(
                    json_path="run.status",
                    pending=("queued",),
                    passed=("passed",),
                    failed=("failed",),
                ),
                report=HttpRequestSpec(url=f"{base}/runs/${{external_id}}/report"),
                cancel=HttpRequestSpec(method="POST", url=f"{base}/runs/${{external_id}}/cancel"),
                backoff_seconds=0,
            ),
            ArtifactStore(tmp_path / "artifacts"),
            secrets={"FIXTURE_TOKEN": "fixture-secret"},
        )
        triggered = verifier.execute(
            VerifierRequest(
                "run-1",
                "ci",
                "attempt-1",
                tmp_path,
                tmp_path / "artifacts",
                "run-1:ci",
            )
        )
        assert triggered.result.status.value == "pending"
        assert verifier.poll("fixture-1").result.status.value == "pending"
        passed = verifier.poll("fixture-1")
        assert passed.result.status.value == "passed"
        assert PipelineHandler.triggers == 1 and PipelineHandler.polls == 2
        artifact = passed.artifacts[0]
        assert b"fixture-secret" not in (tmp_path / "artifacts" / artifact.uri).read_bytes()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
