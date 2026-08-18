import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar

from graph_engineering.delivery import (
    GitHubChecksProvider,
    GitHubRepository,
    PullRequestManager,
    PullRequestSpec,
)
from graph_engineering.runtime import StateStore


class GitHubFixtureHandler(BaseHTTPRequestHandler):
    sha: ClassVar[str] = "a" * 40
    create_count: ClassVar[int] = 0

    def do_GET(self) -> None:
        if self.path.endswith("/check-runs"):
            self._json(
                200,
                {
                    "check_runs": [
                        {
                            "id": 11,
                            "head_sha": self.sha,
                            "status": "completed",
                            "conclusion": "success",
                        }
                    ]
                },
            )
            return
        if "/pulls?" in self.path:
            self._json(200, [])
            return
        self._json(404, {})

    def do_POST(self) -> None:
        type(self).create_count += 1
        size = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(size))
        self._json(
            201,
            {
                "number": 22,
                "html_url": "https://github.invalid/acme/service/pull/22",
                "node_id": "PR_fixture_22",
                "head": {"ref": payload["head"]},
                "base": {"ref": payload["base"]},
            },
        )

    def log_message(self, format: str, *args: object) -> None:
        return

    def _json(self, status: int, payload: object) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def test_isolated_github_provider_http_e2e_and_restart_no_duplicate_pr(tmp_path: Path) -> None:
    GitHubFixtureHandler.create_count = 0
    server = ThreadingHTTPServer(("127.0.0.1", 0), GitHubFixtureHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        repository = GitHubRepository(
            owner="acme",
            name="service",
            api_base_url=f"http://127.0.0.1:{server.server_address[1]}",
        )
        checks = GitHubChecksProvider(repository, allowed_hosts=("127.0.0.1",))
        assert checks.status(GitHubFixtureHandler.sha).successful is True
        state = StateStore(tmp_path / "state.db")
        spec = PullRequestSpec(
            run_id="run-fixture",
            base="main",
            head="phase/fixture",
            title="Fixture delivery",
            body="Deterministic isolated provider fixture; not real GitHub E2E.",
        )
        first = PullRequestManager(
            state, repository, allowed_hosts=("127.0.0.1",), can_write=lambda: True
        ).ensure(spec)
        recovered = PullRequestManager(
            state, repository, allowed_hosts=("127.0.0.1",), can_write=lambda: True
        ).ensure(spec)
        assert recovered == first
        assert GitHubFixtureHandler.create_count == 1
    finally:
        server.shutdown()
        thread.join(timeout=5)
