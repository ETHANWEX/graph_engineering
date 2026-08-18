from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from graph_engineering.runtime import ArtifactStore
from graph_engineering.verifier import (
    HttpPipelineSpec,
    HttpPipelineVerifier,
    HttpRequestSpec,
    HttpResponse,
    HttpStatusMapping,
    VerifierManifest,
    VerifierRequest,
)


class FixtureTransport:
    def __init__(self, responses: list[HttpResponse]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, str, dict[str, str], bytes | None]] = []

    def request(
        self, method: str, url: str, headers: Mapping[str, str], body: bytes | None, timeout: float
    ) -> HttpResponse:
        self.calls.append((method, url, dict(headers), body))
        return self.responses.pop(0)


def response(value: object, status: int = 200, **headers: str) -> HttpResponse:
    return HttpResponse(status, headers, json.dumps(value).encode())


def setup(tmp_path: Path, transport: FixtureTransport) -> HttpPipelineVerifier:
    manifest = VerifierManifest.model_validate(
        {
            "verifier_id": "ci",
            "revision": 1,
            "verifier_type": "builtin/http-pipeline",
            "runtime": "http",
            "capabilities": {
                "network": {"allow": ["ci.example.test"]},
                "secrets": ["CI_TOKEN"],
            },
            "external_side_effects": True,
        }
    )
    spec = HttpPipelineSpec(
        trigger=HttpRequestSpec(
            method="POST",
            url="https://ci.example.test/runs",
            headers={"Authorization": "Bearer ${secret:CI_TOKEN}"},
            body={"request": "${idempotency_key}"},
        ),
        external_id_path="run.id",
        poll=HttpRequestSpec(url="https://ci.example.test/runs/${external_id}"),
        statuses=HttpStatusMapping(
            json_path="run.status", pending=("queued",), passed=("passed",), failed=("failed",)
        ),
        report=HttpRequestSpec(url="https://ci.example.test/runs/${external_id}/report"),
        cancel=HttpRequestSpec(
            method="POST", url="https://ci.example.test/runs/${external_id}/cancel"
        ),
        backoff_seconds=0,
    )
    return HttpPipelineVerifier(
        manifest,
        spec,
        ArtifactStore(tmp_path / "artifacts"),
        secrets={"CI_TOKEN": "top-secret-token"},
        transport=transport,
        sleep=lambda _: None,
    )


def request(tmp_path: Path) -> VerifierRequest:
    return VerifierRequest("run-1", "ci", "attempt-1", tmp_path, tmp_path / "artifacts", "run-1:ci")


def test_http_trigger_poll_report_and_cancel_are_structured_and_redacted(tmp_path: Path) -> None:
    transport = FixtureTransport(
        [
            response({"run": {"id": "external-1"}}),
            response({"run": {"status": "queued"}}),
            response({"run": {"status": "passed"}}),
            HttpResponse(200, {"Content-Type": "text/plain"}, b"top-secret-token report"),
            response({"cancelled": True}),
        ]
    )
    verifier = setup(tmp_path, transport)
    triggered = verifier.execute(request(tmp_path))
    assert triggered.result.status.value == "pending"
    assert triggered.result.external_handle == "external-1"
    assert transport.calls[0][2]["Idempotency-Key"] == "run-1:ci"
    assert verifier.poll("external-1").result.status.value == "pending"
    passed = verifier.poll("external-1")
    assert passed.result.status.value == "passed" and passed.artifacts
    stored = (tmp_path / "artifacts" / passed.artifacts[0].uri).read_text()
    assert "top-secret-token" not in stored and "[REDACTED]" in stored
    assert verifier.cancel("external-1").result.status.value == "cancelled"


def test_http_redirect_cannot_bypass_exact_allowlist(tmp_path: Path) -> None:
    transport = FixtureTransport(
        [HttpResponse(302, {"Location": "https://evil.example.test/steal"}, b"")]
    )
    verifier = setup(tmp_path, transport)
    outcome = verifier.execute(request(tmp_path))
    assert outcome.result.status.value == "error"
    assert outcome.result.error is not None and outcome.result.error.code == "http.trigger"


def test_http_retries_are_bounded(tmp_path: Path) -> None:
    transport = FixtureTransport([response({}, 503), response({}, 503), response({}, 503)])
    verifier = setup(tmp_path, transport)
    outcome = verifier.execute(request(tmp_path))
    assert outcome.result.status.value == "error"
    assert len(transport.calls) == 3


def test_http_barrier_blocks_trigger_and_unsupported_cancel_is_disclosed(tmp_path: Path) -> None:
    transport = FixtureTransport([])
    configured = setup(tmp_path, transport)
    verifier = HttpPipelineVerifier(
        configured.manifest,
        configured.spec.model_copy(update={"cancel": None}),
        ArtifactStore(tmp_path / "blocked-artifacts"),
        secrets={"CI_TOKEN": "top-secret-token"},
        transport=transport,
        can_start=lambda: False,
    )
    blocked = verifier.execute(request(tmp_path))
    unsupported = verifier.cancel("external-1")
    assert blocked.result.status.value == "error" and transport.calls == []
    assert blocked.result.error is not None and blocked.result.error.code == "http.barrier"
    assert unsupported.result.status.value == "error"
    assert unsupported.result.error is not None
    assert unsupported.result.error.code == "http.cancel_unsupported"
    assert "may continue" in unsupported.result.summary
