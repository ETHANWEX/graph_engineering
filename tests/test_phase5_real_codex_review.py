import hashlib
import os
import subprocess
from pathlib import Path

import pytest

from graph_engineering.adapters import CodexAdapter, CodexReviewDimensionAdapter
from graph_engineering.delivery import ReviewContext, ReviewDimension
from graph_engineering.runtime import ArtifactStore

pytestmark = pytest.mark.real_codex


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, text=True, capture_output=True
    ).stdout.strip()


@pytest.mark.skipif(
    os.environ.get("GE_RUN_REAL_CODEX") != "1",
    reason="set GE_RUN_REAL_CODEX=1 for the real Codex acceptance test",
)
def test_real_codex_runs_independent_contract_security_and_test_reviews(tmp_path: Path) -> None:
    root = tmp_path / "fixture"
    root.mkdir()
    git(root, "init")
    git(root, "config", "user.email", "fixture@example.test")
    git(root, "config", "user.name", "Fixture")
    (root / "answer.py").write_text("def answer() -> int:\n    return 41\n", encoding="utf-8")
    git(root, "add", "answer.py")
    git(root, "commit", "-m", "base")
    baseline = git(root, "rev-parse", "HEAD")
    (root / "answer.py").write_text("def answer() -> int:\n    return 42\n", encoding="utf-8")
    (root / "test_answer.py").write_text(
        "from answer import answer\n\ndef test_answer() -> None:\n    assert answer() == 42\n",
        encoding="utf-8",
    )
    git(root, "add", "answer.py", "test_answer.py")
    git(root, "commit", "-m", "implement frozen answer")
    target = git(root, "rev-parse", "HEAD")
    before = git(root, "status", "--porcelain")
    contract = b"ac-1: answer() returns integer 42; ac-2: deterministic test covers behavior"
    context = ReviewContext(
        contract_id="fixture-contract",
        contract_revision=1,
        contract_hash=hashlib.sha256(contract).hexdigest(),
        acceptance_criteria=(
            "ac-1: answer() returns integer 42",
            "ac-2: a deterministic test covers the required behavior",
        ),
        baseline_commit=baseline,
        target_commit=target,
        diff_artifact_ref="sha256:"
        + hashlib.sha256(git(root, "diff", baseline, target).encode()).hexdigest(),
        verifier_evidence_refs=("sha256:" + "a" * 64,),
        repository_map_ref="sha256:" + "b" * 64,
        permission_summary="read-only; no network; no secrets",
        risk_summary="isolated fixture repository",
    )
    adapter = CodexReviewDimensionAdapter(
        CodexAdapter(artifact_store=ArtifactStore(tmp_path / "artifacts")),
        working_directory=root,
        control_directory=tmp_path / "control",
        timeout_seconds=600,
    )
    results = [
        adapter(dimension, context, f"phase5-real-{dimension.value}")
        for dimension in (
            ReviewDimension.CONTRACT,
            ReviewDimension.SECURITY,
            ReviewDimension.TEST_ADEQUACY,
        )
    ]
    assert [item.dimension for item in results] == [
        ReviewDimension.CONTRACT,
        ReviewDimension.SECURITY,
        ReviewDimension.TEST_ADEQUACY,
    ]
    assert all(item.sandbox == "read-only" and item.verdict is not None for item in results)
    assert git(root, "status", "--porcelain") == before
