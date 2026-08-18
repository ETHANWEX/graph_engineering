"""GitHub REST adapter boundary for read-only Checks and checkpointed Pull Requests."""

# ruff: noqa: E501

from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from enum import StrEnum
from typing import Any

from graph_engineering.runtime.store import StateStore, timestamp
from graph_engineering.verifier.http_pipeline import HttpResponse, HttpTransport

from .models import (
    CheckConclusion,
    CheckStatus,
    GitHubCheck,
    GitHubChecksStatus,
    GitHubRepository,
    PullRequestContent,
    PullRequestHandle,
    PullRequestSpec,
)


class GitHubProviderErrorKind(StrEnum):
    AUTH = "auth"
    RATE_LIMIT = "rate_limit"
    NETWORK = "network"
    API = "api"
    IDENTITY = "identity"
    UNKNOWN_STATUS = "unknown_status"
    UNCERTAIN_EFFECT = "uncertain_effect"
    BARRIER = "barrier"


class GitHubProviderError(RuntimeError):
    def __init__(
        self, kind: GitHubProviderErrorKind, message: str, *, retry_after: float | None = None
    ) -> None:
        super().__init__(message)
        self.kind = kind
        self.retry_after = retry_after


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> None:
        return None


class GitHubUrllibTransport:
    def request(
        self, method: str, url: str, headers: Mapping[str, str], body: bytes | None, timeout: float
    ) -> HttpResponse:
        request = urllib.request.Request(url, data=body, headers=dict(headers), method=method)
        try:
            with urllib.request.build_opener(_NoRedirect).open(
                request, timeout=timeout
            ) as response:
                return HttpResponse(response.status, dict(response.headers), response.read())
        except urllib.error.HTTPError as exc:
            return HttpResponse(exc.code, dict(exc.headers), exc.read())


class _GitHubClient:
    def __init__(
        self,
        repository: GitHubRepository,
        *,
        transport: HttpTransport | None,
        token: str | None,
        allowed_hosts: tuple[str, ...],
        timeout_seconds: float = 20,
        max_response_bytes: int = 2 * 1024 * 1024,
    ) -> None:
        self.repository = repository
        self.transport = transport or GitHubUrllibTransport()
        self.token = token
        self.allowed_hosts = {value.lower().rstrip(".") for value in allowed_hosts}
        parsed_base = urllib.parse.urlparse(repository.api_base_url)
        host = parsed_base.hostname
        if host is None or host.lower().rstrip(".") not in self.allowed_hosts:
            raise GitHubProviderError(
                GitHubProviderErrorKind.IDENTITY, "GitHub API host is not allowlisted"
            )
        if parsed_base.scheme != "https" and host.lower() not in {
            "127.0.0.1",
            "localhost",
            "::1",
        }:
            raise GitHubProviderError(
                GitHubProviderErrorKind.IDENTITY,
                "GitHub API requires HTTPS except for an isolated loopback fixture",
            )
        self.timeout_seconds = timeout_seconds
        self.max_response_bytes = max_response_bytes

    def request(
        self, method: str, path: str, payload: object | None = None
    ) -> tuple[HttpResponse, object]:
        url = self.repository.api_base_url + path
        self._validate_url(url)
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "graph-engineering",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        body = json.dumps(payload, separators=(",", ":")).encode() if payload is not None else None
        if body is not None:
            headers["Content-Type"] = "application/json"
        try:
            response = self.transport.request(method, url, headers, body, self.timeout_seconds)
        except Exception as exc:
            raise GitHubProviderError(
                GitHubProviderErrorKind.NETWORK, "GitHub network request failed"
            ) from exc
        if len(response.body) > self.max_response_bytes:
            raise GitHubProviderError(
                GitHubProviderErrorKind.API, "GitHub response exceeded byte limit"
            )
        if 300 <= response.status_code < 400:
            location = response.headers.get("Location") or response.headers.get("location")
            if location:
                self._validate_url(location)
            raise GitHubProviderError(
                GitHubProviderErrorKind.API, "GitHub redirect was not followed"
            )
        self._classify_http(response)
        try:
            parsed: object = json.loads(response.body.decode()) if response.body else {}
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GitHubProviderError(
                GitHubProviderErrorKind.API, "GitHub returned invalid JSON"
            ) from exc
        return response, parsed

    def _validate_url(self, url: str) -> None:
        parsed = urllib.parse.urlparse(url)
        host = parsed.hostname.lower().rstrip(".") if parsed.hostname else ""
        if host not in self.allowed_hosts or parsed.username or parsed.password:
            raise GitHubProviderError(
                GitHubProviderErrorKind.IDENTITY, "GitHub URL identity is not allowed"
            )

    @staticmethod
    def _classify_http(response: HttpResponse) -> None:
        if response.status_code == 401:
            raise GitHubProviderError(GitHubProviderErrorKind.AUTH, "GitHub authentication failed")
        remaining = response.headers.get("x-ratelimit-remaining") or response.headers.get(
            "X-RateLimit-Remaining"
        )
        if response.status_code in {403, 429} and (remaining == "0" or response.status_code == 429):
            retry = response.headers.get("retry-after") or response.headers.get("Retry-After")
            raise GitHubProviderError(
                GitHubProviderErrorKind.RATE_LIMIT,
                "GitHub rate limit exceeded",
                retry_after=float(retry) if retry else None,
            )
        if response.status_code >= 400:
            raise GitHubProviderError(
                GitHubProviderErrorKind.API, f"GitHub API returned HTTP {response.status_code}"
            )


class GitHubChecksProvider:
    def __init__(
        self,
        repository: GitHubRepository,
        *,
        transport: HttpTransport | None = None,
        token: str | None = None,
        allowed_hosts: tuple[str, ...] = ("api.github.com",),
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.repository = repository
        self.client = _GitHubClient(
            repository, transport=transport, token=token, allowed_hosts=allowed_hosts
        )
        self.sleep = sleep

    def status(self, commit_sha: str) -> GitHubChecksStatus:
        encoded = urllib.parse.quote(commit_sha, safe="")
        _, payload = self.client.request(
            "GET",
            f"/repos/{self.repository.owner}/{self.repository.name}/commits/{encoded}/check-runs",
        )
        if not isinstance(payload, dict) or not isinstance(payload.get("check_runs"), list):
            raise GitHubProviderError(
                GitHubProviderErrorKind.API, "GitHub Checks response shape is invalid"
            )
        checks: list[GitHubCheck] = []
        for raw in payload["check_runs"]:
            if (
                not isinstance(raw, dict)
                or str(raw.get("head_sha", "")).lower() != commit_sha.lower()
            ):
                raise GitHubProviderError(
                    GitHubProviderErrorKind.IDENTITY, "GitHub Check belongs to a different commit"
                )
            try:
                status = CheckStatus(str(raw["status"]))
                conclusion = (
                    CheckConclusion(str(raw["conclusion"]))
                    if raw.get("conclusion") is not None
                    else None
                )
            except (KeyError, ValueError) as exc:
                raise GitHubProviderError(
                    GitHubProviderErrorKind.UNKNOWN_STATUS, "GitHub returned an unknown Check state"
                ) from exc
            checks.append(
                GitHubCheck(
                    check_id=int(raw["id"]),
                    head_sha=str(raw["head_sha"]),
                    status=status,
                    conclusion=conclusion,
                    url=str(raw["html_url"]) if raw.get("html_url") else None,
                )
            )
        return GitHubChecksStatus(
            repository=self.repository.full_name, commit_sha=commit_sha, checks=tuple(checks)
        )

    def poll(
        self, commit_sha: str, *, max_attempts: int = 10, backoff_seconds: float = 1
    ) -> GitHubChecksStatus:
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        last: GitHubChecksStatus | None = None
        for attempt in range(max_attempts):
            last = self.status(commit_sha)
            if last.complete:
                return last
            if attempt + 1 < max_attempts:
                self.sleep(backoff_seconds * (2**attempt))
        assert last is not None
        return last


class GitHubChecksMonitor:
    """Persist a read-only Check query so a new Runtime process can continue polling."""

    def __init__(self, state: StateStore, provider: GitHubChecksProvider) -> None:
        self.state = state
        state.migrate()
        self.provider = provider

    def start(self, run_id: str, commit_sha: str) -> str:
        raw = "\0".join((run_id, self.provider.repository.full_name, commit_sha)).encode()
        query_id = "github-checks:" + hashlib.sha256(raw).hexdigest()
        with self.state.transaction() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO github_check_queries("
                "query_id,run_id,repository,commit_sha,status_json,created_at) "
                "VALUES (?,?,?,?,?,?)",
                (
                    query_id,
                    run_id,
                    self.provider.repository.full_name,
                    commit_sha,
                    json.dumps({"state": "pending"}),
                    timestamp(),
                ),
            )
            self.state.enqueue_event(
                connection,
                "github.checks.query.started",
                run_id,
                payload={"query_id": query_id, "commit_sha": commit_sha},
            )
        return query_id

    def poll(self, query_id: str) -> GitHubChecksStatus:
        with self.state.read_connection() as connection:
            row = connection.execute(
                "SELECT * FROM github_check_queries WHERE query_id=?", (query_id,)
            ).fetchone()
        if row is None:
            raise KeyError(query_id)
        if str(row["repository"]) != self.provider.repository.full_name:
            raise GitHubProviderError(
                GitHubProviderErrorKind.IDENTITY,
                "persisted Check query belongs to a different repository",
            )
        status = self.provider.status(str(row["commit_sha"]))
        with self.state.transaction() as connection:
            connection.execute(
                "UPDATE github_check_queries SET status_json=? WHERE query_id=?",
                (status.model_dump_json(), query_id),
            )
            self.state.enqueue_event(
                connection,
                "github.checks.query.polled",
                str(row["run_id"]),
                payload={"query_id": query_id, "complete": status.complete},
            )
        return status

    def get(self, query_id: str) -> dict[str, object]:
        with self.state.read_connection() as connection:
            row = connection.execute(
                "SELECT status_json FROM github_check_queries WHERE query_id=?", (query_id,)
            ).fetchone()
        if row is None:
            raise KeyError(query_id)
        value = json.loads(str(row["status_json"]))
        if not isinstance(value, dict):
            raise GitHubProviderError(GitHubProviderErrorKind.API, "invalid persisted Check status")
        return value


def render_pull_request_body(content: PullRequestContent) -> str:
    """Render the complete delivery body from already-redacted persisted summaries."""

    def bullets(values: tuple[str, ...]) -> str:
        return "\n".join(f"- {value}" for value in values) if values else "- None"

    return (
        f"## Contract and Run\n\nContract revision: {content.contract_revision}\n"
        f"Run ID: `{content.run_id}`\n\n"
        f"## Requirement Matrix\n\n{content.requirement_matrix_summary}\n\n"
        f"## Verifier and CI\n\n{content.verifier_ci_summary}\n\n"
        f"## Review\n\nVerdict: `{content.review_verdict.value}`\n\n"
        f"{content.review_summary}\n\n## Unverified\n\n{bullets(content.unverified)}\n\n"
        f"## External Effects\n\n{bullets(content.external_effects)}\n\n"
        f"## Risks\n\n{bullets(content.risks)}\n\n"
        f"## Final Report and Artifacts\n\n{bullets(content.final_report_refs)}\n\n"
        f"## Reproduction\n\n{bullets(content.reproduction_commands)}\n"
    )


class PullRequestManager:
    def __init__(
        self,
        state: StateStore,
        repository: GitHubRepository,
        *,
        transport: HttpTransport | None = None,
        token: str | None = None,
        allowed_hosts: tuple[str, ...] = ("api.github.com",),
        can_write: Callable[[], bool],
    ) -> None:
        self.state = state
        state.migrate()
        self.repository = repository
        self.client = _GitHubClient(
            repository, transport=transport, token=token, allowed_hosts=allowed_hosts
        )
        self.can_write = can_write

    def ensure(self, spec: PullRequestSpec) -> PullRequestHandle:
        key = self._key(spec)
        existing = self._handle(key)
        if existing is not None:
            return existing
        if not self.can_write():
            raise GitHubProviderError(
                GitHubProviderErrorKind.BARRIER, "persisted barrier forbids GitHub PR write"
            )
        with self.state.transaction() as connection:
            row = connection.execute(
                "SELECT state FROM pull_request_intents WHERE idempotency_key=?", (key,)
            ).fetchone()
            is_new = row is None
            if is_new:
                now = timestamp()
                connection.execute(
                    "INSERT INTO pull_request_intents(idempotency_key, run_id, repository, base_branch, head_branch, spec_json, state, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, 'creating', ?, ?)",
                    (
                        key,
                        spec.run_id,
                        self.repository.full_name,
                        spec.base,
                        spec.head,
                        spec.model_dump_json(),
                        now,
                        now,
                    ),
                )
                self.state.enqueue_event(
                    connection,
                    "github.pr.intent.checkpointed",
                    spec.run_id,
                    payload={"idempotency_key": key, "repository": self.repository.full_name},
                )
        discovered = self._discover(spec)
        if discovered is not None:
            return self._checkpoint(key, spec, discovered)
        if not is_new:
            raise GitHubProviderError(
                GitHubProviderErrorKind.UNCERTAIN_EFFECT,
                "prior PR creation outcome is uncertain; refusing duplicate create",
            )
        if not self.can_write():
            raise GitHubProviderError(
                GitHubProviderErrorKind.BARRIER, "persisted barrier forbids GitHub PR write"
            )
        payload = {
            "title": spec.title,
            "body": spec.body,
            "head": spec.head,
            "base": spec.base,
            "draft": spec.draft,
        }
        try:
            response, created = self.client.request(
                "POST", f"/repos/{self.repository.owner}/{self.repository.name}/pulls", payload
            )
        except GitHubProviderError as exc:
            with self.state.transaction() as connection:
                connection.execute(
                    "UPDATE pull_request_intents SET state=?, updated_at=? WHERE idempotency_key=?",
                    (
                        "uncertain" if exc.kind is GitHubProviderErrorKind.NETWORK else "failed",
                        timestamp(),
                        key,
                    ),
                )
            if exc.kind is GitHubProviderErrorKind.NETWORK:
                raise GitHubProviderError(
                    GitHubProviderErrorKind.UNCERTAIN_EFFECT,
                    "PR create response is uncertain; refusing blind retry",
                ) from exc
            raise
        if response.status_code != 201 or not isinstance(created, dict):
            raise GitHubProviderError(
                GitHubProviderErrorKind.API, "GitHub did not confirm PR creation"
            )
        return self._checkpoint(key, spec, created)

    def update(
        self, handle: PullRequestHandle, *, title: str, body: str, draft: bool
    ) -> PullRequestHandle:
        persisted = self._handle(
            self._key(
                PullRequestSpec(
                    run_id=handle.run_id, base=handle.base, head=handle.head, title="", body=""
                )
            )
        )
        if persisted is None or persisted != handle:
            raise GitHubProviderError(
                GitHubProviderErrorKind.IDENTITY, "PR handle is not owned by this Run"
            )
        if not self.can_write():
            raise GitHubProviderError(
                GitHubProviderErrorKind.BARRIER, "persisted barrier forbids GitHub PR update"
            )
        _, payload = self.client.request(
            "PATCH",
            f"/repos/{self.repository.owner}/{self.repository.name}/pulls/{handle.number}",
            {"title": title, "body": body, "draft": draft},
        )
        if not isinstance(payload, dict):
            raise GitHubProviderError(
                GitHubProviderErrorKind.API, "GitHub PR update response is invalid"
            )
        self._validate_pr(
            payload,
            PullRequestSpec(
                run_id=handle.run_id,
                base=handle.base,
                head=handle.head,
                title=title,
                body=body,
                draft=draft,
            ),
        )
        return handle

    def _discover(self, spec: PullRequestSpec) -> dict[str, object] | None:
        query = urllib.parse.urlencode(
            {"state": "open", "head": f"{self.repository.owner}:{spec.head}", "base": spec.base}
        )
        _, payload = self.client.request(
            "GET", f"/repos/{self.repository.owner}/{self.repository.name}/pulls?{query}"
        )
        if not isinstance(payload, list):
            raise GitHubProviderError(
                GitHubProviderErrorKind.API, "GitHub PR discovery response is invalid"
            )
        matches = [item for item in payload if isinstance(item, dict) and self._matches(item, spec)]
        if len(matches) > 1:
            raise GitHubProviderError(
                GitHubProviderErrorKind.IDENTITY, "multiple PRs match the exact Run identity"
            )
        return matches[0] if matches else None

    def _checkpoint(
        self, key: str, spec: PullRequestSpec, payload: Mapping[str, object]
    ) -> PullRequestHandle:
        self._validate_pr(payload, spec)
        handle = PullRequestHandle(
            run_id=spec.run_id,
            repository=self.repository.full_name,
            base=spec.base,
            head=spec.head,
            number=int(str(payload["number"])),
            url=str(payload["html_url"]),
            node_id=str(payload["node_id"]),
        )
        with self.state.transaction() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO pull_request_handles(idempotency_key, run_id, repository, base_branch, head_branch, pr_number, pr_url, node_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    key,
                    spec.run_id,
                    self.repository.full_name,
                    spec.base,
                    spec.head,
                    handle.number,
                    handle.url,
                    handle.node_id,
                    timestamp(),
                ),
            )
            connection.execute(
                "UPDATE pull_request_intents SET state='checkpointed', updated_at=? WHERE idempotency_key=?",
                (timestamp(), key),
            )
            self.state.enqueue_event(
                connection,
                "github.pr.handle.checkpointed",
                spec.run_id,
                payload={
                    "idempotency_key": key,
                    "number": handle.number,
                    "url": handle.url,
                    "node_id": handle.node_id,
                },
            )
        return handle

    @staticmethod
    def _matches(payload: Mapping[str, object], spec: PullRequestSpec) -> bool:
        head = payload.get("head")
        base = payload.get("base")
        return (
            isinstance(head, dict)
            and isinstance(base, dict)
            and head.get("ref") == spec.head
            and base.get("ref") == spec.base
        )

    def _validate_pr(self, payload: Mapping[str, object], spec: PullRequestSpec) -> None:
        if not self._matches(payload, spec) or not all(
            name in payload for name in ("number", "html_url", "node_id")
        ):
            raise GitHubProviderError(
                GitHubProviderErrorKind.IDENTITY,
                "GitHub PR response does not match repository/head/base identity",
            )

    def _key(self, spec: PullRequestSpec) -> str:
        # Title/body/draft are mutable; identity is stable for the Run and branch pair.
        raw = "\0".join((self.repository.full_name, spec.run_id, spec.base, spec.head)).encode()
        return hashlib.sha256(raw).hexdigest()

    def _handle(self, key: str) -> PullRequestHandle | None:
        with self.state.read_connection() as connection:
            row = connection.execute(
                "SELECT * FROM pull_request_handles WHERE idempotency_key=?", (key,)
            ).fetchone()
        if row is None:
            return None
        return PullRequestHandle(
            run_id=str(row["run_id"]),
            repository=str(row["repository"]),
            base=str(row["base_branch"]),
            head=str(row["head_branch"]),
            number=int(row["pr_number"]),
            url=str(row["pr_url"]),
            node_id=str(row["node_id"]),
        )
