from __future__ import annotations

import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from graph_engineering.adapters import CodexVerifierGenerator
from graph_engineering.contracts import ContractRepository
from graph_engineering.models import HumanMessage
from graph_engineering.runtime import ArtifactStore, StateStore
from graph_engineering.verifier import (
    SubprocessVerifier,
    VerifierLifecycle,
    VerifierRepository,
    VerifierRequest,
)

pytestmark = pytest.mark.real_codex


def test_real_codex_generates_validated_project_verifier_bundle(tmp_path: Path) -> None:
    if os.environ.get("GE_RUN_REAL_CODEX") != "1":
        pytest.skip("set GE_RUN_REAL_CODEX=1 for the real Codex Phase 4 acceptance test")
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    subprocess.run(["git", "init"], cwd=fixture, check=True, capture_output=True)
    secret = "phase4-real-secret-value"
    store = ArtifactStore(tmp_path / "artifacts")
    outcome = CodexVerifierGenerator(store).generate(
        project_root=fixture,
        generation_root=fixture / ".generated",
        description=(
            "Declarative HTTP is insufficient. Generate a Python project/subprocess verifier "
            "using only the standard library. It must read the Graph Engineering JSON request "
            "from stdin and return VerifierResult Schema 1.0 passed when payload.value equals 42, "
            "otherwise failed with failure_details. Include deterministic pytest tests and a JSON "
            "fixture. Use the current Python executable in the argv entrypoint and no network or "
            "external side effects."
        ),
        secret_references=("TEST_TOKEN",),
        secret_values={"TEST_TOKEN": secret},
        timeout_seconds=600,
    )
    assert outcome.bundle.manifest.verifier_type == "project/subprocess"
    assert secret.encode() not in store.read_bytes(outcome.raw_stdout.uri)
    if outcome.raw_stderr is not None:
        assert secret.encode() not in store.read_bytes(outcome.raw_stderr.uri)
    for group in (
        outcome.bundle.implementation,
        outcome.bundle.fixtures,
        outcome.bundle.tests,
    ):
        for generated in group:
            target = fixture / generated.path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(generated.content, encoding="utf-8")
    test_paths = [str(fixture / item.path) for item in outcome.bundle.tests]
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", *test_paths, "-q"],
        cwd=fixture,
        text=True,
        capture_output=True,
        check=False,
        timeout=120,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    entrypoint = tuple(
        sys.executable if token in {"python", "python3", "python.exe"} else token
        for token in outcome.bundle.manifest.entrypoint
    )
    manifest = outcome.bundle.manifest.model_copy(update={"entrypoint": entrypoint})
    verifier = SubprocessVerifier(manifest, store, secrets={"TEST_TOKEN": secret})
    dry_run = verifier.execute(
        VerifierRequest(
            "run-real",
            "verify",
            "attempt-1",
            fixture,
            tmp_path / "artifacts",
            payload={"value": 42},
        )
    )
    assert dry_run.result.status.value == "passed"
    state = StateStore(tmp_path / "state.db")
    contracts = ContractRepository(state)
    draft = contracts.example_draft("contract-real", "Verifier acceptance", "pytest")
    requirement = draft.verifiers[0].model_copy(
        update={
            "verifier_id": manifest.verifier_id,
            "verifier_type": manifest.verifier_type,
        }
    )
    criterion = draft.acceptance_criteria[0].model_copy(
        update={"verifier_refs": [manifest.verifier_id]}
    )
    draft = draft.model_copy(
        update={"verifiers": [requirement], "acceptance_criteria": [criterion]}
    )
    contracts.freeze(
        contracts.stage("conversation", draft),
        HumanMessage(
            schema_version="1.0",
            message_id="contract-confirm-real",
            actor_id="human",
            project_id="project",
            content="confirm",
            created_at=datetime(2026, 8, 18, tzinfo=UTC),
        ),
    )
    repository = VerifierRepository(state)
    implementation_root = fixture / outcome.bundle.implementation[0].path
    tests_root = fixture / outcome.bundle.tests[0].path
    fixtures_root = fixture / outcome.bundle.fixtures[0].path
    repository.stage(manifest, source=implementation_root, tests=tests_root, fixtures=fixtures_root)
    for lifecycle in (
        VerifierLifecycle.VALIDATED,
        VerifierLifecycle.TESTED,
        VerifierLifecycle.DRY_RUN,
    ):
        repository.record(manifest.verifier_id, manifest.revision, lifecycle, {"passed": True})
    repository.freeze(
        manifest.verifier_id,
        manifest.revision,
        contract_id="contract-real",
        contract_revision=1,
        confirmation_message_id="human-confirm-real",
    )
    repository.verify_frozen(manifest.verifier_id, manifest.revision)
