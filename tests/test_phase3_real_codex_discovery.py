from __future__ import annotations

import os
import subprocess
import uuid
from pathlib import Path

import pytest

from graph_engineering.adapters import CodexDiscoveryAdapter
from graph_engineering.runtime import ArtifactStore

pytestmark = pytest.mark.real_codex


@pytest.mark.skipif(
    os.environ.get("GE_RUN_REAL_CODEX") != "1",
    reason="set GE_RUN_REAL_CODEX=1 for explicit networked Codex Discovery acceptance",
)
def test_real_codex_discovery_is_readonly_and_reports_missing_verification(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    configured = os.environ.get("GE_PHASE3_REAL_CODEX_FIXTURE_ROOT")
    root = (
        Path(configured).resolve()
        if configured
        else tmp_path_factory.mktemp("phase3-real-codex-discovery")
    )
    case_root = root / f"case-{uuid.uuid4().hex}"
    repo = case_root / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init")
    _git(repo, "config", "user.email", "fixture@example.invalid")
    _git(repo, "config", "user.name", "Fixture")
    (repo / "app.py").write_text("def greeting():\n    return 'hello'\n", encoding="utf-8")
    _git(repo, "add", "app.py")
    _git(repo, "commit", "-m", "fixture base")
    before = _git(repo, "status", "--porcelain=v1")

    outcome = CodexDiscoveryAdapter(ArtifactStore(case_root / "artifacts")).analyze(
        project_root=repo,
        control_directory=case_root / "control",
        natural_request=(
            "Add an optional name argument to greeting. No test or acceptance command has been "
            "specified. Identify missing information and do not implement anything."
        ),
        repository_summary="app.py: greeting() returns hello",
        timeout_seconds=300,
    )

    assert outcome.provider_version == "0.147.0"
    assert outcome.proposal.missing_information
    assert any(
        "test" in item.casefold() or "verif" in item.casefold()
        for item in outcome.proposal.missing_information
    )
    assert _git(repo, "status", "--porcelain=v1") == before
    assert outcome.raw_stdout.size_bytes is not None and outcome.raw_stdout.size_bytes > 0


def _git(cwd: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args], cwd=cwd, text=True, capture_output=True, check=True, shell=False
    )
    return completed.stdout.strip()
