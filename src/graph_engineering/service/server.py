"""Authenticated single-project loopback Runtime Service."""

from __future__ import annotations

import hmac
import json
import os
import secrets
import socket
import threading
from pathlib import Path

from pydantic import ValidationError

from graph_engineering.runtime.store import timestamp

from .gateway import HumanGateway, gateway_versions, workspace_identity
from .protocol import (
    MAX_FRAME_BYTES,
    IPCRequest,
    IPCResponse,
    ServiceError,
    ServiceErrorCode,
)

_MUTATIONS = {"start", "message", "confirm"}


class RuntimeService:
    def __init__(self, project_root: Path, project_id: str) -> None:
        self.project_root = project_root.resolve()
        self.project_id = project_id
        self.workspace_id = workspace_identity(self.project_root)
        self.gateway = HumanGateway(self.project_root, project_id)
        self.service_root = self.project_root / ".ge" / "service"
        self.endpoint_path = self.service_root / "endpoint.json"
        self.token = secrets.token_urlsafe(48)
        self._shutdown = threading.Event()
        self._socket: socket.socket | None = None

    def serve(self) -> None:
        self.service_root.mkdir(parents=True, exist_ok=True)
        if self.endpoint_path.exists() and self._descriptor_is_live():
            raise RuntimeError("a Runtime Service already owns this project")
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", 0))
        listener.listen(16)
        listener.settimeout(0.5)
        self._socket = listener
        descriptor = {
            "schema_version": "1.0",
            "host": "127.0.0.1",
            "port": listener.getsockname()[1],
            "pid": os.getpid(),
            "project_root": str(self.project_root),
            "project_id": self.project_id,
            "workspace_id": self.workspace_id,
            "authorization": self.token,
            "versions": gateway_versions(),
            "started_at": timestamp(),
        }
        temporary = self.endpoint_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(descriptor, sort_keys=True), encoding="utf-8")
        os.chmod(temporary, 0o600)
        temporary.replace(self.endpoint_path)
        try:
            while not self._shutdown.is_set():
                try:
                    connection, address = listener.accept()
                except TimeoutError:
                    continue
                if address[0] != "127.0.0.1":
                    connection.close()
                    continue
                with connection:
                    connection.settimeout(10)
                    self._serve_connection(connection)
        finally:
            listener.close()
            self._remove_owned_descriptor()

    def _serve_connection(self, connection: socket.socket) -> None:
        request_id = "unknown"
        try:
            raw = self._read_frame(connection)
            document = json.loads(raw.decode("utf-8"))
            if isinstance(document, dict) and isinstance(document.get("request_id"), str):
                request_id = document["request_id"]
            if not isinstance(document, dict) or document.get("protocol_version") != "1.0":
                raise ServiceError(
                    ServiceErrorCode.INCOMPATIBLE_VERSION, "IPC protocol version is incompatible"
                )
            request = IPCRequest.model_validate(document)
            response = self._dispatch(request)
        except (UnicodeDecodeError, json.JSONDecodeError, ValidationError, ValueError):
            response = IPCResponse.failure(
                request_id, ServiceErrorCode.INVALID_REQUEST, "invalid or oversized IPC request"
            )
        except ServiceError as exc:
            response = IPCResponse.failure(request_id, exc.code, str(exc))
        except (KeyError, PermissionError, TimeoutError) as exc:
            code = (
                ServiceErrorCode.NOT_FOUND
                if isinstance(exc, KeyError)
                else ServiceErrorCode.EXPIRED
                if isinstance(exc, TimeoutError)
                else ServiceErrorCode.UNAUTHORIZED
            )
            response = IPCResponse.failure(request_id, code, self._safe_message(exc))
        except Exception:
            response = IPCResponse.failure(
                request_id, ServiceErrorCode.INTERNAL, "Runtime Service request failed"
            )
        encoded = response.model_dump_json(exclude_none=True).encode("utf-8") + b"\n"
        connection.sendall(encoded)

    def _dispatch(self, request: IPCRequest) -> IPCResponse:
        if not hmac.compare_digest(request.authorization, self.token):
            raise ServiceError(ServiceErrorCode.UNAUTHORIZED, "client is not authorized")
        if request.project_id != self.project_id or request.workspace_id != self.workspace_id:
            raise ServiceError(ServiceErrorCode.IDENTITY_MISMATCH, "project identity mismatch")
        if request.operation == "health":
            return IPCResponse.success(
                request.request_id,
                {
                    "healthy": True,
                    "pid": os.getpid(),
                    "project_id": self.project_id,
                    "workspace_id": self.workspace_id,
                    "versions": gateway_versions(),
                },
            )
        if request.operation == "shutdown":
            self._shutdown.set()
            return IPCResponse.success(request.request_id, {"stopping": True})
        if request.operation in _MUTATIONS:
            replay = self._claim(request)
            if replay is not None:
                previous = IPCResponse.model_validate_json(replay)
                return previous.model_copy(update={"request_id": request.request_id})
        try:
            result = self.gateway.dispatch(request.operation, request.payload)
            response = IPCResponse.success(request.request_id, result)
        except ServiceError as exc:
            response = IPCResponse.failure(request.request_id, exc.code, str(exc))
        except KeyError:
            response = IPCResponse.failure(
                request.request_id, ServiceErrorCode.NOT_FOUND, "target was not found"
            )
        except PermissionError:
            response = IPCResponse.failure(
                request.request_id, ServiceErrorCode.UNAUTHORIZED, "request is not authorized"
            )
        except TimeoutError:
            response = IPCResponse.failure(
                request.request_id, ServiceErrorCode.EXPIRED, "pending action has expired"
            )
        except ValueError:
            response = IPCResponse.failure(
                request.request_id, ServiceErrorCode.INVALID_REQUEST, "gateway request is invalid"
            )
        if request.operation in _MUTATIONS:
            self._complete(request, response)
        return response

    def _claim(self, request: IPCRequest) -> str | None:
        fingerprint = request.fingerprint()
        with self.gateway.state.transaction() as connection:
            row = connection.execute(
                "SELECT request_fingerprint,response_json,state FROM ipc_mutation_replays "
                "WHERE idempotency_key=?",
                (request.idempotency_key,),
            ).fetchone()
            if row is not None:
                if str(row["request_fingerprint"]) != fingerprint:
                    raise ServiceError(
                        ServiceErrorCode.CONFLICT,
                        "idempotency key was reused for a different request",
                    )
                if str(row["state"]) != "completed" or row["response_json"] is None:
                    raise ServiceError(
                        ServiceErrorCode.UNCERTAIN_EFFECT,
                        "prior mutation outcome is uncertain; refusing replay",
                    )
                return str(row["response_json"])
            connection.execute(
                "INSERT INTO ipc_mutation_replays(idempotency_key,request_fingerprint,project_id,"
                "workspace_id,operation,state,created_at) VALUES (?,?,?,?,?,'executing',?)",
                (
                    request.idempotency_key,
                    fingerprint,
                    request.project_id,
                    request.workspace_id,
                    request.operation,
                    timestamp(),
                ),
            )
        return None

    def _complete(self, request: IPCRequest, response: IPCResponse) -> None:
        with self.gateway.state.transaction() as connection:
            connection.execute(
                "UPDATE ipc_mutation_replays SET response_json=?,state='completed',completed_at=? "
                "WHERE idempotency_key=? AND state='executing'",
                (response.model_dump_json(exclude_none=True), timestamp(), request.idempotency_key),
            )

    @staticmethod
    def _read_frame(connection: socket.socket) -> bytes:
        chunks = bytearray()
        while True:
            chunk = connection.recv(min(65536, MAX_FRAME_BYTES + 1 - len(chunks)))
            if not chunk:
                break
            newline = chunk.find(b"\n")
            if newline >= 0:
                chunks.extend(chunk[:newline])
                break
            chunks.extend(chunk)
            if len(chunks) > MAX_FRAME_BYTES:
                raise ValueError("request exceeded the byte limit")
        if not chunks:
            raise ValueError("empty request")
        return bytes(chunks)

    def _descriptor_is_live(self) -> bool:
        try:
            document = json.loads(self.endpoint_path.read_text(encoding="utf-8"))
            with socket.create_connection(
                (str(document["host"]), int(document["port"])), timeout=0.25
            ):
                return True
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            return False

    def _remove_owned_descriptor(self) -> None:
        try:
            document = json.loads(self.endpoint_path.read_text(encoding="utf-8"))
            if int(document.get("pid", -1)) == os.getpid():
                self.endpoint_path.unlink(missing_ok=True)
        except (OSError, ValueError, json.JSONDecodeError):
            return

    def _safe_message(self, exc: BaseException) -> str:
        message = str(exc).replace(self.token, "[REDACTED]")
        return message[:1000] or "invalid request"
