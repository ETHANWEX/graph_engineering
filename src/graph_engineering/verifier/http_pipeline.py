"""Declarative asynchronous HTTP pipeline Verifier."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import Field, model_validator

from graph_engineering.models import Error, VerifierResult
from graph_engineering.models.common import ArtifactKind, ErrorKind
from graph_engineering.models.results import VerifierStatus
from graph_engineering.runtime.artifacts import ArtifactStore

from .policy import CapabilityPolicy, SecretRedactor, SecretResolver
from .types import VerifierManifest, VerifierModel, VerifierOutcome, VerifierRequest


class HttpRequestSpec(VerifierModel):
    method: str = "GET"
    url: str = Field(min_length=1)
    headers: dict[str, str] = Field(default_factory=dict)
    body: Any | None = None


class HttpStatusMapping(VerifierModel):
    json_path: str = Field(min_length=1)
    pending: tuple[str, ...]
    passed: tuple[str, ...]
    failed: tuple[str, ...]

    @model_validator(mode="after")
    def disjoint(self) -> HttpStatusMapping:
        groups = [set(self.pending), set(self.passed), set(self.failed)]
        if any(groups[a] & groups[b] for a in range(3) for b in range(a + 1, 3)):
            raise ValueError("HTTP status mappings must be disjoint")
        return self


class HttpPipelineSpec(VerifierModel):
    trigger: HttpRequestSpec
    external_id_path: str = Field(min_length=1)
    poll: HttpRequestSpec
    statuses: HttpStatusMapping
    report: HttpRequestSpec | None = None
    cancel: HttpRequestSpec | None = None
    timeout_seconds: float = Field(default=900, gt=0)
    max_retries: int = Field(default=2, ge=0, le=10)
    backoff_seconds: float = Field(default=0.1, ge=0, le=30)
    max_response_bytes: int = Field(default=1024 * 1024, gt=0)


@dataclass(frozen=True)
class HttpResponse:
    status_code: int
    headers: Mapping[str, str]
    body: bytes


class HttpTransport(Protocol):
    def request(
        self, method: str, url: str, headers: Mapping[str, str], body: bytes | None, timeout: float
    ) -> HttpResponse: ...


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> None:
        return None


class UrllibTransport:
    def request(
        self, method: str, url: str, headers: Mapping[str, str], body: bytes | None, timeout: float
    ) -> HttpResponse:
        request = urllib.request.Request(url, data=body, headers=dict(headers), method=method)
        opener = urllib.request.build_opener(_NoRedirect)
        try:
            with opener.open(request, timeout=timeout) as response:
                return HttpResponse(response.status, dict(response.headers), response.read())
        except urllib.error.HTTPError as exc:
            return HttpResponse(exc.code, dict(exc.headers), exc.read())


class HttpPipelineVerifier:
    def __init__(
        self,
        manifest: VerifierManifest,
        spec: HttpPipelineSpec,
        artifacts: ArtifactStore,
        *,
        secrets: Mapping[str, str] | None = None,
        transport: HttpTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        can_start: Callable[[], bool] | None = None,
    ) -> None:
        if manifest.verifier_type != "builtin/http-pipeline":
            raise ValueError("HTTP pipeline requires a builtin/http-pipeline Manifest")
        self.manifest = manifest
        self.spec = spec
        self.artifacts = artifacts
        self._secrets = SecretResolver(secrets or {}).resolve(manifest)
        self._redactor = SecretRedactor(self._secrets)
        self._transport = transport or UrllibTransport()
        self._sleep = sleep
        self._can_start = can_start or (lambda: True)
        self._started: dict[str, float] = {}

    def execute(self, request: VerifierRequest) -> VerifierOutcome:
        if not self._can_start():
            return self._error("http.barrier", "persisted Run barrier forbids HTTP trigger")
        if not request.idempotency_key:
            return self._error("http.idempotency", "HTTP trigger requires an idempotency key")
        try:
            response = self._send(
                self.spec.trigger,
                external_id=None,
                idempotency_key=request.idempotency_key,
            )
            payload = self._json(response)
            external_id = str(self._extract(payload, self.spec.external_id_path))
            if not external_id:
                raise ValueError("external run ID is empty")
            self._started[external_id] = time.monotonic()
            result = VerifierResult(
                schema_version="1.0",
                status=VerifierStatus.PENDING,
                summary="HTTP pipeline triggered and awaiting completion",
                external_handle=external_id,
                retryable=True,
            )
            return VerifierOutcome(result)
        except Exception as exc:
            return self._error("http.trigger", self._redactor.redact(str(exc)), retryable=True)

    def poll(self, handle: str) -> VerifierOutcome:
        try:
            started = self._started.setdefault(handle, time.monotonic())
            if time.monotonic() - started >= self.spec.timeout_seconds:
                return self._error(
                    "http.timeout", "HTTP pipeline polling timed out", retryable=True
                )
            response = self._send(self.spec.poll, external_id=handle, idempotency_key=None)
            payload = self._json(response)
            status = str(self._extract(payload, self.spec.statuses.json_path))
            if status in self.spec.statuses.pending:
                return VerifierOutcome(
                    VerifierResult(
                        schema_version="1.0",
                        status=VerifierStatus.PENDING,
                        summary=f"HTTP pipeline is pending ({status})",
                        external_handle=handle,
                        retryable=True,
                    )
                )
            if status in self.spec.statuses.passed:
                artifacts = self._download_report(handle)
                return VerifierOutcome(
                    VerifierResult(
                        schema_version="1.0",
                        status=VerifierStatus.PASSED,
                        summary=f"HTTP pipeline passed ({status})",
                        artifacts=list(artifacts),
                    ),
                    artifacts,
                )
            if status in self.spec.statuses.failed:
                artifacts = self._download_report(handle)
                return VerifierOutcome(
                    VerifierResult(
                        schema_version="1.0",
                        status=VerifierStatus.FAILED,
                        summary=f"HTTP pipeline failed ({status})",
                        failure_details=[f"external status: {status}"],
                        artifacts=list(artifacts),
                    ),
                    artifacts,
                )
            return self._error("http.status", f"unmapped HTTP pipeline status: {status}")
        except Exception as exc:
            return self._error("http.poll", self._redactor.redact(str(exc)), retryable=True)

    def cancel(self, handle: str) -> VerifierOutcome:
        if self.spec.cancel is None:
            return self._error(
                "http.cancel_unsupported",
                "HTTP pipeline does not declare cancellation; external effect may continue",
            )
        try:
            response = self._send(self.spec.cancel, external_id=handle, idempotency_key=None)
            if response.status_code >= 300:
                return self._error(
                    "http.cancel_unknown",
                    "HTTP cancellation result is unknown; external effect may continue",
                )
            return VerifierOutcome(
                VerifierResult(
                    schema_version="1.0",
                    status=VerifierStatus.CANCELLED,
                    summary="HTTP pipeline cancellation was accepted",
                )
            )
        except Exception as exc:
            return self._error("http.cancel_unknown", self._redactor.redact(str(exc)))

    def _send(
        self, request: HttpRequestSpec, *, external_id: str | None, idempotency_key: str | None
    ) -> HttpResponse:
        url = self._render(request.url, external_id, idempotency_key)
        CapabilityPolicy.require_url(self.manifest, url)
        headers = {
            key: self._render(value, external_id, idempotency_key)
            for key, value in request.headers.items()
        }
        if idempotency_key is not None:
            headers.setdefault("Idempotency-Key", idempotency_key)
        body = None
        if request.body is not None:
            rendered = self._render(json.dumps(request.body), external_id, idempotency_key)
            body = rendered.encode("utf-8")
            headers.setdefault("Content-Type", "application/json")
        last: Exception | None = None
        for attempt in range(self.spec.max_retries + 1):
            try:
                response = self._transport.request(
                    request.method.upper(), url, headers, body, self.spec.timeout_seconds
                )
                if 300 <= response.status_code < 400:
                    location = response.headers.get("Location") or response.headers.get("location")
                    if location:
                        CapabilityPolicy.require_url(self.manifest, location)
                    raise RuntimeError("HTTP redirects are not followed")
                if len(response.body) > self.spec.max_response_bytes:
                    raise RuntimeError("HTTP response exceeded configured byte limit")
                if response.status_code >= 500:
                    raise RuntimeError(f"HTTP infrastructure status {response.status_code}")
                if response.status_code >= 400:
                    raise RuntimeError(f"HTTP request status {response.status_code}")
                return response
            except Exception as exc:
                last = exc
                if attempt < self.spec.max_retries:
                    self._sleep(self.spec.backoff_seconds * (2**attempt))
        raise RuntimeError(str(last))

    def _render(self, value: str, external_id: str | None, idempotency_key: str | None) -> str:
        result = value.replace("${external_id}", external_id or "")
        result = result.replace("${idempotency_key}", idempotency_key or "")
        for reference, secret in self._secrets.items():
            result = result.replace(f"${{secret:{reference}}}", secret)
        return result

    def _download_report(self, handle: str) -> tuple[Any, ...]:
        if self.spec.report is None:
            return ()
        response = self._send(self.spec.report, external_id=handle, idempotency_key=None)
        artifact = self.artifacts.put_bytes(
            self._redactor.redact_bytes(response.body),
            media_type=response.headers.get("Content-Type", "application/octet-stream"),
            kind=ArtifactKind.TEST_RESULT,
        )
        return (artifact,)

    @staticmethod
    def _extract(payload: Any, path: str) -> Any:
        value = payload
        for part in path.removeprefix("$.").split("."):
            if not isinstance(value, dict) or part not in value:
                raise ValueError(f"JSON path is missing: {path}")
            value = value[part]
        return value

    @staticmethod
    def _json(response: HttpResponse) -> Any:
        return json.loads(response.body.decode("utf-8"))

    @staticmethod
    def _error(code: str, message: str, *, retryable: bool = False) -> VerifierOutcome:
        error = Error(
            schema_version="1.0",
            kind=ErrorKind.INFRASTRUCTURE,
            code=code,
            message=message,
            retryable=retryable,
        )
        return VerifierOutcome(
            VerifierResult(
                schema_version="1.0",
                status=VerifierStatus.ERROR,
                summary=message,
                retryable=retryable,
                error=error,
            )
        )
