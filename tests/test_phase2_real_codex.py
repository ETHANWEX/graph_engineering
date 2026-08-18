from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from graph_engineering.adapters.codex import CodexAdapter
from graph_engineering.context import Handoff, HandoffStatus
from graph_engineering.executor import ExecutorRequest, ExecutorRole, SandboxMode
from graph_engineering.models import ExecutorResult
from graph_engineering.review import ReviewResult, ReviewVerdict
from graph_engineering.runtime import ArtifactStore, SessionRepository, StateStore
from graph_engineering.verifier import CommandVerifier, CommandVerifierSpec

pytestmark = pytest.mark.real_codex


def git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=cwd, text=True, capture_output=True, check=True, shell=False
    )
    return result.stdout.strip()


@pytest.mark.skipif(
    os.environ.get("GE_RUN_REAL_CODEX") != "1",
    reason="set GE_RUN_REAL_CODEX=1 for the explicit networked Codex acceptance",
)
def test_real_codex_review_fix_resume_observer_flow(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    configured_root = os.environ.get("GE_REAL_CODEX_FIXTURE_ROOT")
    fixture_root = (
        Path(configured_root).resolve()
        if configured_root
        else tmp_path_factory.mktemp("real-codex-fixture")
    )
    repo = fixture_root / "fixture-repo"
    control = fixture_root / "control"
    repo.mkdir(parents=True, exist_ok=True)
    git(repo, "init")
    git(repo, "config", "user.email", "fixture@example.invalid")
    git(repo, "config", "user.name", "Fixture")
    (repo / "answer.py").write_text("def answer():\n    return 1\n", encoding="utf-8")
    (repo / "test_answer.py").write_text(
        "from answer import answer\n\n\ndef test_answer():\n    assert answer() == 42\n",
        encoding="utf-8",
    )
    (repo / ".gitignore").write_text("__pycache__/\n.pytest_cache/\n", encoding="utf-8")
    git(repo, "add", "answer.py", "test_answer.py", ".gitignore")
    git(repo, "commit", "--allow-empty", "-m", "fixture base")
    artifacts = ArtifactStore(fixture_root / "artifacts")
    adapter = CodexAdapter(artifact_store=artifacts)
    state = StateStore(fixture_root / "state.db")
    state.migrate()
    sessions = SessionRepository(state)

    implementation = adapter.start(
        _request(
            repo,
            control,
            "implement-1",
            ExecutorRole.IMPLEMENTER,
            SandboxMode.WORKSPACE_WRITE,
            "As an intentional first review-fix iteration, change only answer.py so answer() "
            "returns 41. Do not change tests. Return the required structured ExecutorResult.",
            ExecutorResult.model_json_schema(),
        )
    )
    assert implementation.result.status.value == "succeeded"
    assert "return 41" in (repo / "answer.py").read_text(encoding="utf-8")
    _persist_outcome(sessions, "implement-1", ExecutorRole.IMPLEMENTER, implementation)
    first_verification = CommandVerifier(artifacts).run(
        CommandVerifierSpec(
            argv=(sys.executable, "-m", "pytest", "-q"),
            cwd=repo,
            timeout_seconds=60,
        )
    )
    assert first_verification.result.status.value == "failed"

    review_one = adapter.review_structured(
        _request(
            repo,
            control,
            "review-1",
            ExecutorRole.REVIEWER,
            SandboxMode.READ_ONLY,
            "Contract: answer() must return 42 and tests are frozen. Independently review the "
            "uncommitted diff and verifier failure. Request concrete changes when incorrect.",
            ReviewResult.model_json_schema(),
        )
    )
    assert review_one.session.provider_session_id != implementation.session.provider_session_id
    assert review_one.result.verdict is ReviewVerdict.CHANGES_REQUESTED
    _persist_role_session(
        sessions,
        "review-1",
        ExecutorRole.REVIEWER,
        review_one.session.provider_session_id,
        review_one.session.provider_version,
    )

    fixed = adapter.resume(
        implementation.session,
        _request(
            repo,
            control,
            "implement-2",
            ExecutorRole.IMPLEMENTER,
            SandboxMode.WORKSPACE_WRITE,
            "Reviewer found that answer() must return 42. "
            "Fix only answer.py; keep tests unchanged.",
            ExecutorResult.model_json_schema(),
        ),
    )
    assert fixed.result.status.value == "succeeded"
    _persist_outcome(sessions, "implement-2", ExecutorRole.IMPLEMENTER, fixed)
    second_verification = CommandVerifier(artifacts).run(
        CommandVerifierSpec(
            argv=(sys.executable, "-m", "pytest", "-q"),
            cwd=repo,
            timeout_seconds=60,
        )
    )
    assert second_verification.result.status.value == "passed"

    review_two = adapter.review_structured(
        _request(
            repo,
            control,
            "review-2",
            ExecutorRole.REVIEWER,
            SandboxMode.READ_ONLY,
            "Contract: answer() must return 42 and tests are frozen. Review the corrected "
            "uncommitted diff and passing verifier evidence.",
            ReviewResult.model_json_schema(),
        )
    )
    assert review_two.session.provider_session_id not in {
        implementation.session.provider_session_id,
        review_one.session.provider_session_id,
    }
    assert review_two.result.verdict is ReviewVerdict.APPROVED
    _persist_role_session(
        sessions,
        "review-2",
        ExecutorRole.REVIEWER,
        review_two.session.provider_session_id,
        review_two.session.provider_version,
    )

    status_before = git(repo, "status", "--porcelain=v1")
    observer = adapter.start(
        _request(
            repo,
            control,
            "observer-1",
            ExecutorRole.OBSERVER,
            SandboxMode.READ_ONLY,
            "Read the repository status and summarize current progress without modifying files.",
            ExecutorResult.model_json_schema(),
        )
    )
    assert observer.session.provider_session_id not in {
        implementation.session.provider_session_id,
        review_one.session.provider_session_id,
        review_two.session.provider_session_id,
    }
    assert git(repo, "status", "--porcelain=v1") == status_before
    assert artifacts.read_bytes(implementation.raw_stdout.uri)
    _persist_outcome(sessions, "observer-1", ExecutorRole.OBSERVER, observer)
    handoff = Handoff(
        status=HandoffStatus.COMPLETED,
        summary="real Codex fixture corrected and independently approved",
        changed_files=fixed.result.changed_files,
        decisions=fixed.result.decisions,
        remaining_risks=fixed.result.remaining_risks,
        next_actions=fixed.result.next_actions,
        evidence_refs=[
            fixed.raw_stdout.artifact_id,
            *(artifact.artifact_id for artifact in second_verification.result.artifacts),
            review_two.raw_stdout.artifact_id,
        ],
    )
    handoff_artifact = artifacts.put_bytes(
        handoff.canonical_json().encode("utf-8"), media_type="application/json"
    )
    assert artifacts.read_bytes(handoff_artifact.uri)

    recovered_sessions = SessionRepository(StateStore(fixture_root / "state.db"))
    recovered = recovered_sessions.completed_outcome("real-codex-run", "implement-2")
    assert recovered is not None
    assert recovered.session.provider_session_id == implementation.session.provider_session_id
    assert recovered.result.changed_files == fixed.result.changed_files

    interrupted: list[object] = []

    def run_interrupt_target() -> None:
        interrupted.append(
            adapter.resume(
                implementation.session,
                _request(
                    repo,
                    control,
                    "interrupt-target",
                    ExecutorRole.IMPLEMENTER,
                    SandboxMode.WORKSPACE_WRITE,
                    "Run a command that waits for 120 seconds before returning structured output.",
                    ExecutorResult.model_json_schema(),
                ),
            )
        )

    worker = threading.Thread(target=run_interrupt_target)
    worker.start()
    deadline = time.monotonic() + 30
    while not adapter.is_active(implementation.session) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert adapter.is_active(implementation.session)
    assert adapter.cancel(implementation.session, grace_seconds=5)
    worker.join(timeout=15)
    assert worker.is_alive() is False


def _persist_outcome(
    sessions: SessionRepository,
    attempt_id: str,
    role: ExecutorRole,
    outcome: object,
) -> None:
    from graph_engineering.executor import ExecutorOutcome

    assert isinstance(outcome, ExecutorOutcome)
    record = sessions.start(
        "real-codex-run",
        role.value,
        attempt_id,
        role,
        outcome.session.provider,
        outcome.session.provider_session_id,
        outcome.session.provider_version,
    )
    sessions.complete(
        record.session_id,
        stdout_artifact_id=outcome.raw_stdout.artifact_id,
        stderr_artifact_id=(
            outcome.raw_stderr.artifact_id if outcome.raw_stderr is not None else None
        ),
        outcome=outcome,
    )


def _persist_role_session(
    sessions: SessionRepository,
    attempt_id: str,
    role: ExecutorRole,
    provider_session_id: str,
    provider_version: str,
) -> None:
    record = sessions.start(
        "real-codex-run",
        role.value,
        attempt_id,
        role,
        "codex",
        provider_session_id,
        provider_version,
    )
    sessions.complete(record.session_id)


def _request(
    repo: Path,
    control: Path,
    attempt_id: str,
    role: ExecutorRole,
    sandbox: SandboxMode,
    objective: str,
    schema: dict[str, object],
) -> ExecutorRequest:
    return ExecutorRequest(
        run_id="real-codex-run",
        node_id=role.value,
        attempt_id=attempt_id,
        role=role,
        objective=objective,
        context=(
            "Contract and evidence are supplied in the objective. Do not commit or modify tests."
        ),
        working_directory=repo,
        sandbox=sandbox,
        output_schema=json.loads(json.dumps(schema)),
        control_directory=control,
        timeout_seconds=300,
    )
