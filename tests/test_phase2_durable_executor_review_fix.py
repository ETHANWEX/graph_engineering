from __future__ import annotations

import json
from pathlib import Path

from graph_engineering.executor import (
    DurableExecutorRuntime,
    ExecutorCapabilities,
    ExecutorEvent,
    ExecutorOutcome,
    ExecutorRequest,
    ExecutorRole,
    SandboxMode,
    SessionHandle,
    SessionPolicy,
)
from graph_engineering.models import ExecutorResult
from graph_engineering.models.common import ArtifactKind
from graph_engineering.models.results import ExecutorStatus
from graph_engineering.review import (
    ReviewFinding,
    ReviewFixCoordinator,
    ReviewResult,
    ReviewVerdict,
)
from graph_engineering.runtime import ArtifactStore
from graph_engineering.runtime.sessions import SessionRepository
from graph_engineering.runtime.store import StateStore


class FakeAdapter:
    def __init__(self, artifacts: ArtifactStore) -> None:
        self.artifacts = artifacts
        self.starts = 0
        self.resumes = 0

    def capabilities(self) -> ExecutorCapabilities:
        return ExecutorCapabilities(
            "fake", "1.0.0", True, True, True, True, True, True, True, True, True
        )

    def start(self, request: ExecutorRequest) -> ExecutorOutcome:
        self.starts += 1
        return self._outcome(request, f"fresh-{self.starts}")

    def resume(self, session: SessionHandle, request: ExecutorRequest) -> ExecutorOutcome:
        self.resumes += 1
        return self._outcome(request, session.provider_session_id)

    def review(self, request: ExecutorRequest) -> ExecutorOutcome:
        return self.start(request)

    def cancel(self, session: SessionHandle, *, grace_seconds: float = 5) -> bool:
        return True

    def _outcome(self, request: ExecutorRequest, provider_id: str) -> ExecutorOutcome:
        raw = self.artifacts.put_bytes(b"{}\n", kind=ArtifactKind.LOG)
        return ExecutorOutcome(
            SessionHandle("fake", provider_id, "1.0.0"),
            ExecutorResult(schema_version="1.0", status=ExecutorStatus.SUCCEEDED, summary="done"),
            (ExecutorEvent("session_started", "session", provider_id, {}),),
            raw,
            None,
            0,
        )


def request(tmp_path: Path, attempt: str = "attempt-1") -> ExecutorRequest:
    return ExecutorRequest(
        "run-1",
        "node",
        attempt,
        ExecutorRole.IMPLEMENTER,
        "do work",
        "context",
        tmp_path,
        SandboxMode.WORKSPACE_WRITE,
        json.loads(
            (Path(__file__).parents[1] / "schemas" / "ExecutorResult.schema.json").read_text()
        ),
        tmp_path / "control",
    )


def test_completed_attempt_is_recovered_without_duplicate_execution(tmp_path: Path) -> None:
    state = StateStore(tmp_path / "state.db")
    state.migrate()
    artifacts = ArtifactStore(tmp_path / "artifacts")
    adapter = FakeAdapter(artifacts)
    first = DurableExecutorRuntime(adapter, SessionRepository(state), SessionPolicy())
    outcome = first.execute(request(tmp_path))
    assert outcome.result.status is ExecutorStatus.SUCCEEDED
    assert adapter.starts == 1

    recovered = DurableExecutorRuntime(
        adapter, SessionRepository(StateStore(tmp_path / "state.db")), SessionPolicy()
    )
    repeated = recovered.execute(request(tmp_path))
    assert repeated.result.summary == "done"
    assert adapter.starts == 1


def test_same_node_resumes_then_rotates_at_threshold(tmp_path: Path) -> None:
    state = StateStore(tmp_path / "state.db")
    state.migrate()
    artifacts = ArtifactStore(tmp_path / "artifacts")
    adapter = FakeAdapter(artifacts)
    runtime = DurableExecutorRuntime(
        adapter, SessionRepository(state), SessionPolicy(max_continuations=1)
    )
    runtime.execute(request(tmp_path, "attempt-1"))
    runtime.execute(request(tmp_path, "attempt-2"))
    runtime.execute(request(tmp_path, "attempt-3"))
    assert adapter.resumes == 1
    assert adapter.starts == 2


def test_review_fix_reruns_verifier_and_uses_fresh_review_attempt() -> None:
    calls: list[str] = []
    finding = ReviewFinding(
        severity="high",
        category="correctness",
        file="answer.py",
        line=1,
        description="wrong",
        required_change="fix it",
    )
    reviews = iter(
        [
            ReviewResult(
                verdict=ReviewVerdict.CHANGES_REQUESTED,
                summary="fix",
                findings=[finding],
            ),
            ReviewResult(verdict=ReviewVerdict.APPROVED, summary="approved"),
        ]
    )

    def review(attempt: int) -> ReviewResult:
        calls.append(f"review:{attempt}")
        return next(reviews)

    coordinator = ReviewFixCoordinator(
        review=review,
        implement_fix=lambda findings: calls.append("fix"),
        run_affected_verifiers=lambda findings: calls.append("verify"),
        max_fix_attempts=2,
    )
    result = coordinator.run()
    assert result.verdict is ReviewVerdict.APPROVED
    assert calls == ["review:1", "fix", "verify", "review:2"]
