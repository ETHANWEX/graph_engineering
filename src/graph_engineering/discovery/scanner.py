"""Deterministic size-limited repository pre-scan."""

from __future__ import annotations

from pathlib import Path

from graph_engineering.context import RepositoryMap

from .models import ProjectEntry, ProjectScan


class ProjectScanner:
    def __init__(self, *, max_files: int = 500, max_total_bytes: int = 2 * 1024 * 1024) -> None:
        if max_files <= 0 or max_total_bytes <= 0:
            raise ValueError("scan limits must be positive")
        self.max_files = max_files
        self.max_total_bytes = max_total_bytes

    def scan(self, root: Path, *, use_git: bool = True) -> ProjectScan:
        repository = RepositoryMap.rebuild(root, use_git=use_git)
        included: list[ProjectEntry] = []
        total = 0
        truncated = False
        for entry in repository.entries:
            if len(included) >= self.max_files or total + entry.size_bytes > self.max_total_bytes:
                truncated = True
                continue
            included.append(ProjectEntry(path=entry.path, size_bytes=entry.size_bytes))
            total += entry.size_bytes
        return ProjectScan(
            project_root=str(repository.root),
            entries=tuple(included),
            included_bytes=total,
            truncated=truncated,
        )
