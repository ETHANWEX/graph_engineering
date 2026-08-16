from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from graph_engineering.runtime import ArtifactStore
from graph_engineering.verifier import (
    CommandVerifier,
    CommandVerifierSpec,
    VerificationBarrierError,
)
from graph_engineering.workspace import GitWorkspaceManager, WorkspaceError


def git(cwd: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True, check=True)
    return result.stdout.strip()


def fixture_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init")
    git(repo, "config", "user.email", "fixture@example.invalid")
    git(repo, "config", "user.name", "Fixture")
    (repo / "answer.py").write_text("VALUE = 1\n", encoding="utf-8")
    git(repo, "add", "answer.py")
    git(repo, "commit", "-m", "base")
    return repo


def test_each_run_gets_distinct_branch_and_worktree(tmp_path: Path) -> None:
    repo = fixture_repo(tmp_path)
    manager = GitWorkspaceManager(repo, tmp_path / "control-root")
    one = manager.create("run-1")
    two = manager.create("run-2")
    assert one.path != two.path
    assert one.branch != two.branch
    assert not one.path.is_relative_to(manager.control_root)
    assert not (one.path / ".ge" / "control").exists()


def test_accepted_commit_restart_materializes_without_changing_source(tmp_path: Path) -> None:
    repo = fixture_repo(tmp_path)
    commit = git(repo, "rev-parse", "HEAD")
    manager = GitWorkspaceManager(repo, tmp_path / "control-root")
    source = manager.create("source")
    source_head = git(source.path, "rev-parse", "HEAD")
    restarted = manager.create("restart", accepted_commit=commit)
    assert git(restarted.path, "rev-parse", "HEAD") == commit
    assert git(source.path, "rev-parse", "HEAD") == source_head


def test_workspace_refuses_unexpected_existing_target(tmp_path: Path) -> None:
    repo = fixture_repo(tmp_path)
    manager = GitWorkspaceManager(repo, tmp_path / "control-root")
    target = manager.worktrees_root / "run-1"
    target.mkdir(parents=True)
    with pytest.raises(WorkspaceError):
        manager.create("run-1")


@pytest.mark.parametrize(("code", "status"), [(0, "passed"), (3, "failed")])
def test_command_verifier_maps_exit_status_and_saves_evidence(
    tmp_path: Path, code: int, status: str
) -> None:
    verifier = CommandVerifier(ArtifactStore(tmp_path / "artifacts"))
    result = verifier.run(
        CommandVerifierSpec(
            argv=(sys.executable, "-c", f"print('evidence'); raise SystemExit({code})"),
            cwd=tmp_path,
            timeout_seconds=5,
            max_output_bytes=1024,
        )
    )
    assert result.result.status.value == status
    assert result.stdout_artifact is not None


def test_command_verifier_timeout_and_oversize_are_errors(tmp_path: Path) -> None:
    verifier = CommandVerifier(ArtifactStore(tmp_path / "artifacts"))
    timeout = verifier.run(
        CommandVerifierSpec(
            argv=(sys.executable, "-c", "import time; time.sleep(2)"),
            cwd=tmp_path,
            timeout_seconds=0.05,
            max_output_bytes=100,
        )
    )
    oversized = verifier.run(
        CommandVerifierSpec(
            argv=(sys.executable, "-c", "print('x' * 1000)"),
            cwd=tmp_path,
            timeout_seconds=5,
            max_output_bytes=100,
        )
    )
    assert timeout.result.status.value == "error"
    assert timeout.result.error is not None and timeout.result.error.code == "command.timeout"
    assert oversized.result.status.value == "error"
    assert (
        oversized.result.error is not None and oversized.result.error.code == "command.output_limit"
    )


def test_command_verifier_rejects_shell_source(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        CommandVerifierSpec(argv=("echo ok && whoami",), cwd=tmp_path)


def test_persisted_barrier_prevents_command_process_start(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    verifier = CommandVerifier(ArtifactStore(tmp_path / "artifacts"), can_start=lambda: False)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: pytest.fail("subprocess must not start after barrier"),
    )
    with pytest.raises(VerificationBarrierError):
        verifier.run(CommandVerifierSpec(argv=(sys.executable, "--version"), cwd=tmp_path))
