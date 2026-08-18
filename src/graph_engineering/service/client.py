"""Bounded reconnecting client for the project Runtime Service."""

from __future__ import annotations

import json
import socket
import uuid
from pathlib import Path
from typing import Any

from .gateway import workspace_identity
from .protocol import IPC_VERSION, MAX_FRAME_BYTES, IPCRequest, IPCResponse, ServiceError


class ServiceClient:
    def __init__(self, project_root: Path, *, timeout: float = 5, max_attempts: int = 2) -> None:
        self.project_root = project_root.resolve()
        self.timeout = timeout
        self.max_attempts = max_attempts

    @property
    def endpoint_path(self) -> Path:
        return self.project_root / ".ge" / "service" / "endpoint.json"

    def call(
        self,
        operation: str,
        payload: dict[str, Any] | None = None,
        *,
        idempotency_key: str | None = None,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        descriptor = self._descriptor()
        versions = descriptor.get("versions")
        if not isinstance(versions, dict):
            raise RuntimeError("Runtime Service version metadata is unavailable")
        if not str(versions.get("package", "")).startswith("0.7."):
            raise RuntimeError("graph-engineering package version is incompatible")
        if str(versions.get("runtime_api", "")).split(".")[0] != "1":
            raise RuntimeError("Runtime Service API version is incompatible")
        if str(versions.get("ipc", "")).split(".")[0] != "1":
            raise RuntimeError("Runtime Service IPC version is incompatible")
        request = IPCRequest(
            protocol_version=IPC_VERSION,
            request_id=request_id or f"request:{uuid.uuid4()}",
            idempotency_key=idempotency_key or f"idempotency:{uuid.uuid4()}",
            project_id=str(descriptor["project_id"]),
            workspace_id=workspace_identity(self.project_root),
            operation=operation,  # type: ignore[arg-type]
            authorization=str(descriptor["authorization"]),
            payload=payload or {},
        )
        encoded = request.model_dump_json().encode("utf-8") + b"\n"
        last: OSError | None = None
        for _attempt in range(self.max_attempts):
            try:
                with socket.create_connection(
                    (str(descriptor["host"]), int(descriptor["port"])), timeout=self.timeout
                ) as connection:
                    connection.settimeout(self.timeout)
                    connection.sendall(encoded)
                    raw = self._read_frame(connection)
                response = IPCResponse.model_validate_json(raw)
                if response.request_id != request.request_id:
                    raise RuntimeError("Runtime Service response identity mismatch")
                if not response.ok:
                    assert response.error is not None
                    raise ServiceError(response.error.code, response.error.message)
                return response.result or {}
            except OSError as exc:
                last = exc
        raise ConnectionError("Runtime Service is unavailable") from last

    def _descriptor(self) -> dict[str, Any]:
        try:
            value = json.loads(self.endpoint_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ConnectionError("Runtime Service endpoint is unavailable") from exc
        if not isinstance(value, dict):
            raise ConnectionError("Runtime Service endpoint is invalid")
        if Path(str(value.get("project_root", ""))).resolve() != self.project_root:
            raise ConnectionError("Runtime Service endpoint belongs to another project")
        return value

    @staticmethod
    def _read_frame(connection: socket.socket) -> bytes:
        data = bytearray()
        while True:
            chunk = connection.recv(min(65536, MAX_FRAME_BYTES + 1 - len(data)))
            if not chunk:
                break
            newline = chunk.find(b"\n")
            if newline >= 0:
                data.extend(chunk[:newline])
                break
            data.extend(chunk)
            if len(data) > MAX_FRAME_BYTES:
                raise RuntimeError("Runtime Service response exceeded the byte limit")
        if not data:
            raise RuntimeError("Runtime Service disconnected without a response")
        return bytes(data)
