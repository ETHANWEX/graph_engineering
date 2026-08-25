"""Pure bounded HTTP application for the optional Project UI."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.resources import files
from typing import Any
from urllib.parse import unquote, urlsplit

from .provider import UIProvider
from .render import render_page
from .security import SecretLeakError, StreamingSecretGuard

UI_CONTRACT_VERSION = "1.0"
MAX_BODY_BYTES = 64 * 1024
MAX_RESPONSE_BYTES = 1024 * 1024
MAX_REQUESTS_PER_MINUTE = 12
_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,256}$")
_ACTIONS = {"pause", "resume", "interrupt", "cancel", "accept", "reject", "revise"}
_SECRET_KEY_PARTS = ("authorization", "credential", "password", "secret", "token", "cookie")


@dataclass(frozen=True)
class UIRequest:
    method: str
    path: str
    headers: dict[str, str]
    body: bytes
    remote_addr: str


@dataclass(frozen=True)
class UIResponse:
    status: int
    headers: dict[str, str]
    body: bytes


class ProjectUIApp:
    def __init__(
        self,
        provider: UIProvider,
        *,
        project_id: str,
        actor_id: str,
        origin: str,
        session_id: str,
        secret_values: tuple[str, ...] = (),
    ) -> None:
        split = urlsplit(origin)
        if split.scheme != "http" or split.hostname not in {"127.0.0.1", "localhost"}:
            raise ValueError("UI origin must use local HTTP loopback")
        if not split.netloc or split.path not in {"", "/"} or split.query or split.fragment:
            raise ValueError("UI origin must not contain a path, query, or fragment")
        if not all(_ID.fullmatch(item) for item in (project_id, actor_id, session_id)):
            raise ValueError("UI identities are invalid")
        self.provider = provider
        self.project_id = project_id
        self.actor_id = actor_id
        self.origin = origin.rstrip("/")
        self.host = split.netloc
        self.session_id = session_id
        self.guard = StreamingSecretGuard(secret_values)
        self._requests: deque[float] = deque(maxlen=MAX_REQUESTS_PER_MINUTE + 1)
        self._rate_lock = threading.Lock()

    def handle(self, request: UIRequest) -> UIResponse:
        try:
            self._validate_common(request)
            if request.method == "GET":
                return self._get(request)
            if request.method == "POST":
                self._validate_mutation(request)
                return self._post(request)
            return self._response(405, b"method not allowed", "text/plain; charset=utf-8")
        except _HTTPFailure as exc:
            return self._response(exc.status, exc.body, "text/plain; charset=utf-8")
        except SecretLeakError:
            return self._response(500, b"request failed", "text/plain; charset=utf-8", scan=False)
        except Exception:
            return self._response(500, b"request failed", "text/plain; charset=utf-8", scan=False)

    def _validate_common(self, request: UIRequest) -> None:
        if request.remote_addr not in {"127.0.0.1", "::1"}:
            raise _HTTPFailure(403, b"invalid request")
        headers = {key.casefold(): value for key, value in request.headers.items()}
        if not hmac.compare_digest(headers.get("host", ""), self.host):
            raise _HTTPFailure(403, b"invalid request")
        origin = headers.get("origin")
        if origin is not None and not hmac.compare_digest(origin, self.origin):
            raise _HTTPFailure(403, b"invalid request")
        if len(request.path) > 2048 or "\x00" in request.path:
            raise _HTTPFailure(400, b"invalid request")
        if len(request.body) > MAX_BODY_BYTES:
            raise _HTTPFailure(413, b"request too large")

    def _validate_mutation(self, request: UIRequest) -> None:
        headers = {key.casefold(): value for key, value in request.headers.items()}
        if not hmac.compare_digest(headers.get("origin", ""), self.origin):
            raise _HTTPFailure(403, b"invalid request")
        if headers.get("sec-fetch-site") != "same-origin":
            raise _HTTPFailure(403, b"invalid request")
        if headers.get("content-type", "").split(";", 1)[0].strip() != "application/json":
            raise _HTTPFailure(415, b"JSON required")
        try:
            declared = int(headers.get("content-length", str(len(request.body))))
        except ValueError as exc:
            raise _HTTPFailure(400, b"invalid request") from exc
        if declared > MAX_BODY_BYTES or declared != len(request.body):
            raise _HTTPFailure(413, b"request too large")
        cookies = _cookies(headers.get("cookie", ""))
        if not hmac.compare_digest(cookies.get("ge_ui_session", ""), self.session_id):
            raise _HTTPFailure(403, b"invalid request")
        now = time.monotonic()
        with self._rate_lock:
            while self._requests and self._requests[0] <= now - 60:
                self._requests.popleft()
            if len(self._requests) >= MAX_REQUESTS_PER_MINUTE:
                raise _HTTPFailure(429, b"rate limit exceeded")
            self._requests.append(now)

    def _get(self, request: UIRequest) -> UIResponse:
        path = urlsplit(request.path).path
        if path in {"/assets/ui.css", "/assets/ui.js"}:
            asset = path.rsplit("/", 1)[-1]
            body = files("graph_engineering.ui.assets").joinpath(asset).read_bytes()
            mime = "text/css" if asset.endswith(".css") else "text/javascript"
            return self._response(200, body, f"{mime}; charset=utf-8", immutable=True)
        if path in {"/", "/api/v1/project"}:
            snapshot = self.provider.project_snapshot()
            run_id = None
        elif path.startswith("/runs/") or path.startswith("/api/v1/runs/"):
            run_id = unquote(path.rsplit("/", 1)[-1])
            self._identity(run_id)
            snapshot = self.provider.run_snapshot(run_id)
        else:
            raise _HTTPFailure(404, b"not found")
        self._validate_snapshot(snapshot, run_id=run_id)
        if path.startswith("/api/"):
            body = json.dumps(
                snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode()
            etag = '"' + hashlib.sha256(body).hexdigest() + '"'
            headers = {key.casefold(): value for key, value in request.headers.items()}
            if hmac.compare_digest(headers.get("if-none-match", ""), etag):
                return self._response(304, b"", "application/json; charset=utf-8", etag=etag)
            return self._response(200, body, "application/json; charset=utf-8", etag=etag)
        return self._response(
            200,
            render_page(
                snapshot,
                selected_run_id=run_id,
                actor_id=self.actor_id,
                session_id=self.session_id,
            ),
            "text/html; charset=utf-8",
            cookie=True,
        )

    def _post(self, request: UIRequest) -> UIResponse:
        try:
            document = json.loads(request.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise _HTTPFailure(400, b"invalid JSON") from exc
        if not isinstance(document, dict):
            raise _HTTPFailure(400, b"invalid request")
        path = urlsplit(request.path).path
        if path == "/api/v1/messages":
            required = ("conversation_id", "content", "message_id", "request_id", "idempotency_key")
            self._require_strings(document, required)
            payload = {
                "conversation_id": document["conversation_id"],
                "content": document["content"],
                "message_id": document["message_id"],
                "actor_id": self.actor_id,
                "project_id": self.project_id,
            }
            if document.get("run_id") is not None:
                self._identity(document["run_id"])
                payload["run_id"] = document["run_id"]
            result = self._mutate("message", payload, document)
        elif path.startswith("/api/v1/confirmations/"):
            pending_id = unquote(path.rsplit("/", 1)[-1])
            self._identity(pending_id)
            result = self._confirm(pending_id, document)
        else:
            match = re.fullmatch(r"/api/v1/runs/([^/]+)/actions/([^/]+)", path)
            if match is None:
                raise _HTTPFailure(404, b"not found")
            run_id, action = (unquote(value) for value in match.groups())
            self._identity(run_id)
            if action not in _ACTIONS:
                raise _HTTPFailure(404, b"not found")
            action_required = ["content", "message_id", "request_id", "idempotency_key"]
            if action != "cancel":
                action_required.append("conversation_id")
            self._require_strings(document, tuple(action_required))
            if action != "cancel" and action not in re.findall(
                r"[a-z]+", str(document["content"]).casefold()
            ):
                raise _HTTPFailure(400, b"action and message do not match")
            action_payload: dict[str, object] = {
                "run_id": run_id,
                "content": document["content"],
                "message_id": document["message_id"],
                "actor_id": self.actor_id,
                "project_id": self.project_id,
                "request_id": document["request_id"],
                "idempotency_key": document["idempotency_key"],
            }
            for optional in ("reason", "report_revision", "conversation_id"):
                if optional in document:
                    action_payload[optional] = document[optional]
            # Natural-language capable actions deliberately re-enter the Human Gateway's
            # persist-first Intent Compiler and confirmation policy. Cancel has no natural-language
            # intent in protocol 1.0 and therefore uses its existing typed Gateway route.
            operation = action if action == "cancel" else "message"
            result = self._mutate(operation, action_payload, document)
        body = json.dumps(
            result, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
        return self._response(200, body, "application/json; charset=utf-8")

    def _confirm(self, pending_id: str, document: dict[str, Any]) -> dict[str, Any]:
        required = (
            "pending_action_id",
            "conversation_id",
            "actor_id",
            "source_message_id",
            "intent_id",
            "action",
            "run_id",
            "contract_id",
            "contract_revision",
            "contract_hash",
            "created_at",
            "expires_at",
            "session_id",
            "snapshot_id",
            "confirmation_message_id",
            "request_id",
            "idempotency_key",
            "content",
        )
        self._require_strings(
            document, tuple(item for item in required if item != "contract_revision")
        )
        if document.get("contract_revision") is None:
            raise _HTTPFailure(400, b"invalid request")
        snapshot = self.provider.project_snapshot()
        self._validate_snapshot(snapshot)
        source = snapshot.get("source")
        project = snapshot.get("project")
        cards = snapshot.get("pending_confirmations")
        card = (
            next(
                (
                    item
                    for item in cards
                    if isinstance(item, dict) and item.get("pending_action_id") == pending_id
                ),
                None,
            )
            if isinstance(cards, list)
            else None
        )
        if card is None or card.get("status") != "pending":
            raise _HTTPFailure(409, b"stale confirmation")
        expected = {
            "pending_action_id": pending_id,
            "project_id": self.project_id,
            "conversation_id": card.get("conversation_id"),
            "actor_id": card.get("actor_id"),
            "source_message_id": card.get("source_message_id"),
            "intent_id": card.get("intent_id"),
            "action": card.get("action"),
            "run_id": card.get("run_id"),
            "contract_id": card.get("contract_id"),
            "contract_revision": card.get("contract_revision"),
            "contract_hash": card.get("contract_hash"),
            "created_at": card.get("created_at"),
            "expires_at": card.get("expires_at"),
            "session_id": self.session_id,
            "snapshot_id": source.get("snapshot_id") if isinstance(source, dict) else None,
        }
        if not isinstance(project, dict) or project.get("project_id") != self.project_id:
            raise _HTTPFailure(409, b"stale confirmation")
        if any(document.get(key) != value for key, value in expected.items()):
            raise _HTTPFailure(409, b"stale confirmation")
        try:
            expiry = datetime.fromisoformat(str(card["expires_at"]).replace("Z", "+00:00"))
        except (KeyError, ValueError) as exc:
            raise _HTTPFailure(409, b"stale confirmation") from exc
        if expiry <= datetime.now(UTC):
            raise _HTTPFailure(410, b"confirmation expired")
        payload = {
            "conversation_id": document["conversation_id"],
            "confirmation_id": pending_id,
            "content": document["content"],
            "message_id": document["confirmation_message_id"],
            "actor_id": self.actor_id,
            "project_id": self.project_id,
            "run_id": document["run_id"],
        }
        return self._mutate("confirm", payload, document)

    def _mutate(
        self, operation: str, payload: dict[str, object], identity: dict[str, Any]
    ) -> dict[str, Any]:
        return self.provider.mutate(
            operation,
            payload,
            request_id=str(identity["request_id"]),
            idempotency_key=str(identity["idempotency_key"]),
        )

    def _validate_snapshot(self, snapshot: dict[str, Any], *, run_id: str | None = None) -> None:
        if snapshot.get("contract_version") != UI_CONTRACT_VERSION:
            raise _HTTPFailure(409, b"incompatible snapshot")
        _reject_secret_keys(snapshot)
        project = snapshot.get("project")
        if not isinstance(project, dict) or project.get("project_id") != self.project_id:
            raise _HTTPFailure(409, b"identity mismatch")
        if run_id is not None:
            runs = snapshot.get("runs")
            if not isinstance(runs, list) or not any(
                isinstance(item, dict) and item.get("run_id") == run_id for item in runs
            ):
                raise _HTTPFailure(404, b"not found")

    def _response(
        self,
        status: int,
        body: bytes,
        content_type: str,
        *,
        cookie: bool = False,
        immutable: bool = False,
        etag: str | None = None,
        scan: bool = True,
    ) -> UIResponse:
        if len(body) > MAX_RESPONSE_BYTES:
            raise _HTTPFailure(507, b"response too large")
        if scan:
            self.guard.reset()
            self.guard.check_chunk(body)
        headers = {
            "content-type": content_type,
            "content-length": str(len(body)),
            "content-security-policy": (
                "default-src 'none'; style-src 'self'; script-src 'self'; connect-src 'self'; "
                "img-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'"
            ),
            "x-content-type-options": "nosniff",
            "x-frame-options": "DENY",
            "referrer-policy": "no-referrer",
            "permissions-policy": "camera=(), microphone=(), geolocation=()",
            "cache-control": "public, max-age=31536000, immutable" if immutable else "no-store",
        }
        if cookie:
            headers["set-cookie"] = (
                f"ge_ui_session={self.session_id}; Path=/; HttpOnly; SameSite=Strict"
            )
        if etag is not None:
            headers["etag"] = etag
        return UIResponse(status, headers, body)

    @staticmethod
    def _require_strings(document: dict[str, Any], names: tuple[str, ...]) -> None:
        for name in names:
            value = document.get(name)
            if not isinstance(value, str) or not value or len(value) > 65536:
                raise _HTTPFailure(400, b"invalid request")

    @staticmethod
    def _identity(value: object) -> str:
        if not isinstance(value, str) or _ID.fullmatch(value) is None:
            raise _HTTPFailure(400, b"invalid identity")
        return value


class _HTTPFailure(Exception):
    def __init__(self, status: int, body: bytes) -> None:
        super().__init__(status)
        self.status = status
        self.body = body


def _cookies(value: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in value.split(";"):
        name, separator, content = item.strip().partition("=")
        if separator and name:
            result[name] = content
    return result


def _reject_secret_keys(value: object) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key).casefold().replace("-", "_")
            if any(part in normalized for part in _SECRET_KEY_PARTS):
                raise SecretLeakError("UI snapshot contained a secret-bearing key")
            _reject_secret_keys(item)
    elif isinstance(value, list):
        for item in value:
            _reject_secret_keys(item)
