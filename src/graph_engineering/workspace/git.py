"""Windows-safe Git worktree materialization using argv only."""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


class WorkspaceError(RuntimeError):
    pass


@dataclass(frozen=True)
class GitWorkspace:
    run_id: str
    branch: str
    path: Path
    base_commit: str


class GitWorkspaceManager:
    def __init__(
        self,
        repository: Path,
        control_root: Path,
        *,
        can_start: Callable[[], bool] | None = None,
    ) -> None:
        self.repository = repository.resolve()
        self.control_root = control_root.resolve()
        self.control_root.mkdir(parents=True, exist_ok=True)
        self.worktrees_root = self.control_root.parent / "worktrees"
        self.worktrees_root.mkdir(parents=True, exist_ok=True)
        self.can_start = can_start or (lambda: True)
        self._git("rev-parse", "--git-dir")

    def create(self, run_id: str, *, accepted_commit: str | None = None) -> GitWorkspace:
        if not self.can_start():
            raise WorkspaceError("persisted Run barrier forbids a worktree write")
        slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", run_id).strip("-.")
        if not slug or slug != run_id:
            raise WorkspaceError("run_id is not safe for a branch/worktree path")
        target = (self.worktrees_root / slug).resolve()
        if target.exists():
            raise WorkspaceError(f"worktree target already exists: {target}")
        if target.parent != self.worktrees_root.resolve():
            raise WorkspaceError("worktree target escapes the configured root")
        commit = accepted_commit or self._git("rev-parse", "HEAD")
        verified = self._git("rev-parse", "--verify", f"{commit}^{{commit}}")
        branch = f"ge/run-{slug}"
        result = self._run("worktree", "add", "-b", branch, str(target), verified)
        if result.returncode != 0:
            raise WorkspaceError(result.stderr.strip() or "git worktree add failed")
        return GitWorkspace(run_id, branch, target, verified)

    def _git(self, *args: str) -> str:
        result = self._run(*args)
        if result.returncode != 0:
            raise WorkspaceError(result.stderr.strip() or f"git {' '.join(args)} failed")
        return result.stdout.strip()

    def _run(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(self.repository), *args],
            text=True,
            capture_output=True,
            check=False,
            shell=False,
        )
