from __future__ import annotations

import sys
from pathlib import Path

import pytest

from graph_engineering.executor import (
    ExecutorRequest,
    ExecutorRole,
    ProcessSupervisor,
    SandboxMode,
    SessionPolicy,
)
from graph_engineering.review import (
    ObserverFailure,
    ReadOnlyRoleRunner,
    ReviewFinding,
    ReviewResult,
    ReviewVerdict,
)
from graph_engineering.runtime.frozen import FrozenInputMismatch, FrozenInputs


def test_frozen_input_hashes_reject_recovery_drift(tmp_path: Path) -> None:
    contract = tmp_path / "contract.json"
    graph = tmp_path / "graph.json"
    verifier = tmp_path / "verifier.json"
    lock = tmp_path / "acceptance.lock"
    for path in (contract, graph, verifier, lock):
        path.write_text(path.name, encoding="utf-8")
    frozen = FrozenInputs.capture(contract, graph, (verifier,), lock)
    frozen.verify()
    verifier.write_text("drift", encoding="utf-8")
    with pytest.raises(FrozenInputMismatch, match="verifier"):
        frozen.verify()


def test_process_supervisor_can_query_and_terminate(tmp_path: Path) -> None:
    supervisor = ProcessSupervisor()
    handle = supervisor.start([sys.executable, "-c", "import time; time.sleep(30)"], cwd=tmp_path)
    assert supervisor.query(handle).running
    settled = supervisor.cancel(handle, grace_seconds=2)
    assert settled.terminated
    assert supervisor.query(handle).running is False


def test_process_supervisor_reports_quiescing_when_termination_does_not_settle(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    supervisor = ProcessSupervisor()
    handle = supervisor.start([sys.executable, "-c", "import time; time.sleep(30)"], cwd=tmp_path)
    monkeypatch.setattr(supervisor, "_wait", lambda process, timeout: False)
    result = supervisor.cancel(handle, grace_seconds=0.01)
    assert result.terminated is False
    assert result.quiescing is True
    handle.process.kill()
    handle.process.wait()


def test_review_models_are_strict_and_findings_are_structured() -> None:
    review = ReviewResult(
        verdict=ReviewVerdict.CHANGES_REQUESTED,
        summary="fix required",
        findings=[
            ReviewFinding(
                severity="high",
                category="correctness",
                file="answer.py",
                line=1,
                description="wrong value",
                required_change="set value to 42",
                contract_refs=["criterion-1"],
            )
        ],
    )
    assert review.verdict is ReviewVerdict.CHANGES_REQUESTED
    with pytest.raises(ValueError):
        ReviewResult.model_validate({"verdict": "approved", "summary": "ok", "extra": True})


class RecordingExecutor:
    def __init__(self, *, fail_observer: bool = False) -> None:
        self.requests: list[object] = []
        self.fail_observer = fail_observer

    def review(self, request: object) -> str:
        self.requests.append(request)
        return "reviewed"

    def start(self, request: object) -> str:
        self.requests.append(request)
        if self.fail_observer:
            raise RuntimeError("observer unavailable")
        return "observed"


def test_reviewer_and_observer_are_fresh_readonly_and_observer_is_noninterfering(
    tmp_path: Path,
) -> None:
    fingerprint = ["unchanged"]
    executor = RecordingExecutor()
    runner = ReadOnlyRoleRunner(executor, fingerprint=lambda: tuple(fingerprint))
    review = runner.review(_readonly_request(tmp_path, ExecutorRole.REVIEWER, "review-1"))
    observation = runner.observe(_readonly_request(tmp_path, ExecutorRole.OBSERVER, "observe-1"))
    assert review == "reviewed"
    assert observation == "observed"
    assert len(executor.requests) == 2
    assert SessionPolicy().allows_resume(ExecutorRole.REVIEWER, same_node=True) is False

    failing = ReadOnlyRoleRunner(
        RecordingExecutor(fail_observer=True), fingerprint=lambda: tuple(fingerprint)
    )
    with pytest.raises(ObserverFailure):
        failing.observe(_readonly_request(tmp_path, ExecutorRole.OBSERVER, "observe-2"))
    assert fingerprint == ["unchanged"]


def _readonly_request(tmp_path: Path, role: ExecutorRole, attempt: str) -> ExecutorRequest:

    return ExecutorRequest(
        run_id="run-1",
        node_id=role.value,
        attempt_id=attempt,
        role=role,
        objective="inspect independently",
        context="independent package",
        working_directory=tmp_path,
        sandbox=SandboxMode.READ_ONLY,
        output_schema={},
        control_directory=tmp_path / "control",
    )
