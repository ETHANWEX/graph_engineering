"""Minimal deterministic Repository Map that is always rebuildable."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, order=True)
class RepositoryEntry:
    path: str
    size_bytes: int


@dataclass(frozen=True)
class RepositoryMap:
    root: Path
    entries: tuple[RepositoryEntry, ...]

    @classmethod
    def rebuild(cls, root: Path, *, use_git: bool = True) -> RepositoryMap:
        resolved = root.resolve()
        if use_git:
            result = subprocess.run(
                [
                    "git",
                    "-C",
                    str(resolved),
                    "ls-files",
                    "--cached",
                    "--others",
                    "--exclude-standard",
                ],
                text=True,
                capture_output=True,
                check=False,
                shell=False,
            )
            relative_paths = result.stdout.splitlines() if result.returncode == 0 else []
        else:
            relative_paths = [
                path.relative_to(resolved).as_posix()
                for path in resolved.rglob("*")
                if path.is_file() and ".git" not in path.relative_to(resolved).parts
            ]
        entries = tuple(
            RepositoryEntry(relative, (resolved / Path(relative)).stat().st_size)
            for relative in sorted(set(relative_paths))
            if (resolved / Path(relative)).is_file()
        )
        return cls(resolved, entries)
