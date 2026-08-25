"""Loopback-only bounded HTTP server for :mod:`graph_engineering.ui`."""

from __future__ import annotations

import secrets
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar

from graph_engineering.service import ServiceClient

from .app import MAX_BODY_BYTES, ProjectUIApp, UIRequest
from .provider import RuntimeServiceUIProvider


class ProjectUIServer:
    def __init__(
        self,
        project_root: Path,
        *,
        project_id: str,
        actor_id: str,
        host: str = "127.0.0.1",
        port: int = 0,
        max_active_requests: int = 16,
        secret_values: tuple[str, ...] = (),
    ) -> None:
        if host != "127.0.0.1":
            raise ValueError("Project UI may bind only IPv4 loopback")
        if not 0 <= port <= 65535 or not 1 <= max_active_requests <= 64:
            raise ValueError("invalid UI server bounds")
        self.project_root = project_root.resolve()
        self.project_id = project_id
        self.actor_id = actor_id
        self._semaphore = threading.BoundedSemaphore(max_active_requests)
        server = _BoundedHTTPServer(
            (host, port),
            _Handler,
            self._semaphore,
            request_queue_size=min(max_active_requests, 32),
        )
        server.daemon_threads = True
        bound_port = int(server.server_address[1])
        self.origin = f"http://127.0.0.1:{bound_port}"
        self.app = ProjectUIApp(
            RuntimeServiceUIProvider(ServiceClient(self.project_root)),
            project_id=project_id,
            actor_id=actor_id,
            origin=self.origin,
            session_id=f"ui-{secrets.token_hex(16)}",
            secret_values=secret_values,
        )
        server.app = self.app  # type: ignore[attr-defined]
        self._server = server

    def serve(self) -> None:
        self._server.serve_forever(poll_interval=0.25)

    def shutdown(self) -> None:
        self._server.shutdown()
        self._server.server_close()


class _Handler(BaseHTTPRequestHandler):
    server_version = "GraphEngineeringUI/1.0"
    sys_version = ""
    protocol_version = "HTTP/1.1"
    max_header_count: ClassVar[int] = 64

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(10)

    def do_GET(self) -> None:
        self._dispatch()

    def do_POST(self) -> None:
        self._dispatch()

    def do_HEAD(self) -> None:
        self._dispatch()

    def do_OPTIONS(self) -> None:
        self._dispatch()

    def do_PUT(self) -> None:
        self._dispatch()

    def do_PATCH(self) -> None:
        self._dispatch()

    def do_DELETE(self) -> None:
        self._dispatch()

    def do_TRACE(self) -> None:
        self._dispatch()

    def do_CONNECT(self) -> None:
        self._dispatch()

    def _dispatch(self) -> None:
        try:
            if len(self.headers) > self.max_header_count:
                self._simple_error(431)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                self._simple_error(400)
                return
            if length < 0 or length > MAX_BODY_BYTES:
                self._simple_error(413)
                return
            body = self.rfile.read(length) if length else b""
            app: ProjectUIApp = self.server.app  # type: ignore[attr-defined]
            response = app.handle(
                UIRequest(
                    self.command,
                    self.path,
                    {key.casefold(): value for key, value in self.headers.items()},
                    body,
                    self.client_address[0],
                )
            )
            self.send_response(response.status)
            for key, value in response.headers.items():
                self.send_header(key, value)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(response.body)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            return

    def _simple_error(self, status: int) -> None:
        body = b"invalid request"
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        del format, args


class _BoundedHTTPServer(ThreadingHTTPServer):
    def __init__(
        self,
        address: tuple[str, int],
        handler: type[BaseHTTPRequestHandler],
        semaphore: threading.BoundedSemaphore,
        *,
        request_queue_size: int,
    ) -> None:
        self._semaphore = semaphore
        self.request_queue_size = request_queue_size
        super().__init__(address, handler)

    def process_request(
        self,
        request: socket.socket | tuple[bytes, socket.socket],
        client_address: tuple[str, int],
    ) -> None:
        if not self._semaphore.acquire(blocking=False):
            raw_socket = request[1] if isinstance(request, tuple) else request
            raw_socket.close()
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self._semaphore.release()
            raise

    def process_request_thread(
        self,
        request: socket.socket | tuple[bytes, socket.socket],
        client_address: tuple[str, int],
    ) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._semaphore.release()
