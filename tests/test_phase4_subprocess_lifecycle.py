from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from graph_engineering.contracts import ContractRepository
from graph_engineering.models import HumanMessage, TaskContract
from graph_engineering.runtime import ArtifactStore, StateStore
from graph_engineering.verifier import (
    SubprocessVerifier,
    VerifierLifecycle,
    VerifierLifecycleError,
    VerifierManifest,
    VerifierRepository,
    VerifierRequest,
)


def project_manifest(script: Path, *, revision: int = 1) -> VerifierManifest:
    return VerifierManifest.model_validate(
        {
            "verifier_id": "project-check",
            "revision": revision,
            "verifier_type": "project/subprocess",
            "runtime": "python",
            "entrypoint": [sys.executable, str(script)],
            "capabilities": {
                "filesystem": {"read": ["."], "write": ["artifacts"]},
                "secrets": ["CHECK_TOKEN"],
            },
        }
    )


def request(tmp_path: Path) -> VerifierRequest:
    return VerifierRequest(
        run_id="run-1",
        node_id="verify",
        attempt_id="attempt-1",
        working_directory=tmp_path,
        artifact_directory=tmp_path / "artifacts",
    )


def write_script(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")


def freeze_contract(
    state: StateStore, contract_id: str, verifier_id: str, verifier_type: str
) -> TaskContract:
    repository = ContractRepository(state)
    draft = repository.example_draft(contract_id, "Verifier acceptance", "pytest")
    requirement = draft.verifiers[0].model_copy(
        update={"verifier_id": verifier_id, "verifier_type": verifier_type}
    )
    criterion = draft.acceptance_criteria[0].model_copy(update={"verifier_refs": [verifier_id]})
    draft = draft.model_copy(
        update={"verifiers": [requirement], "acceptance_criteria": [criterion]}
    )
    draft_id = repository.stage("conversation", draft)
    return repository.freeze(
        draft_id,
        HumanMessage(
            schema_version="1.0",
            message_id=f"confirm-{contract_id}",
            actor_id="human",
            project_id="project",
            content="confirm",
            created_at=datetime(2026, 8, 18, tzinfo=UTC),
        ),
    ).contract


@pytest.mark.parametrize(("status", "expected"), [("passed", "passed"), ("failed", "failed")])
def test_subprocess_protocol_preserves_business_result(
    tmp_path: Path, status: str, expected: str
) -> None:
    script = tmp_path / "verifier.py"
    details = ", 'failure_details': ['acceptance mismatch']" if status == "failed" else ""
    write_script(
        script,
        "import json, sys\n"
        "request=json.load(sys.stdin)\n"
        f"print(json.dumps({{'schema_version':'1.0','status':'{status}',"
        f"'summary':'done'{details}}}))\n",
    )
    verifier = SubprocessVerifier(
        project_manifest(script),
        ArtifactStore(tmp_path / "artifacts"),
        secrets={"CHECK_TOKEN": "super-secret"},
        timeout_seconds=5,
    )
    outcome = verifier.execute(request(tmp_path))
    assert outcome.result.status.value == expected


@pytest.mark.parametrize(
    ("body", "code"),
    [
        ("print('not-json')\n", "subprocess.protocol"),
        ("raise SystemExit(9)\n", "subprocess.exit"),
        ("print('x' * 10000)\n", "subprocess.output_limit"),
    ],
)
def test_subprocess_invalid_json_exit_and_oversize_are_errors(
    tmp_path: Path, body: str, code: str
) -> None:
    script = tmp_path / "bad.py"
    write_script(script, "import sys\njson_request=sys.stdin.read()\n" + body)
    verifier = SubprocessVerifier(
        project_manifest(script),
        ArtifactStore(tmp_path / "artifacts"),
        secrets={"CHECK_TOKEN": "super-secret"},
        timeout_seconds=5,
        max_output_bytes=100,
    )
    outcome = verifier.execute(request(tmp_path))
    assert outcome.result.status.value == "error"
    assert outcome.result.error is not None and outcome.result.error.code == code


def test_subprocess_timeout_and_secret_artifacts_are_safe(tmp_path: Path) -> None:
    script = tmp_path / "slow.py"
    write_script(
        script,
        "import os, sys, time\n"
        "sys.stderr.write(os.environ['CHECK_TOKEN'])\n"
        "sys.stderr.flush()\n"
        "time.sleep(2)\n",
    )
    store = ArtifactStore(tmp_path / "artifacts")
    verifier = SubprocessVerifier(
        project_manifest(script),
        store,
        secrets={"CHECK_TOKEN": "super-secret"},
        timeout_seconds=0.05,
    )
    outcome = verifier.execute(request(tmp_path))
    assert outcome.result.status.value == "error"
    assert outcome.result.error is not None and outcome.result.error.code == "subprocess.timeout"
    assert all(b"super-secret" not in store.read_bytes(item.uri) for item in outcome.artifacts)


def test_lifecycle_requires_evidence_confirmation_and_rejects_hash_drift(tmp_path: Path) -> None:
    script = tmp_path / "verifier.py"
    tests = tmp_path / "tests.py"
    fixtures = tmp_path / "fixtures.json"
    write_script(script, "print('implementation')\n")
    write_script(tests, "print('tests')\n")
    fixtures.write_text("{}\n", encoding="utf-8")
    state = StateStore(tmp_path / "state.db")
    freeze_contract(state, "contract-1", "project-check", "project/subprocess")
    repository = VerifierRepository(state)
    manifest = project_manifest(script)
    hashes = repository.stage(manifest, source=script, tests=tests, fixtures=fixtures)
    assert hashes.fixtures_sha256 is not None
    with pytest.raises(VerifierLifecycleError):
        repository.freeze(
            manifest.verifier_id,
            1,
            contract_id="contract-1",
            contract_revision=1,
            confirmation_message_id="",
        )
    for lifecycle in (
        VerifierLifecycle.VALIDATED,
        VerifierLifecycle.TESTED,
        VerifierLifecycle.DRY_RUN,
    ):
        repository.record(manifest.verifier_id, 1, lifecycle, {"passed": True})
    frozen = repository.freeze(
        manifest.verifier_id,
        1,
        contract_id="contract-1",
        contract_revision=1,
        confirmation_message_id="human-confirm-1",
    )
    assert repository.verify_frozen(manifest.verifier_id, 1) == frozen
    script.write_text("print('drift')\n", encoding="utf-8")
    with pytest.raises(VerifierLifecycleError, match="hash drift"):
        repository.verify_frozen(manifest.verifier_id, 1)


def test_new_verifier_revision_requires_new_contract_revision(tmp_path: Path) -> None:
    state = StateStore(tmp_path / "state.db")
    freeze_contract(state, "contract-1", "project-check", "project/subprocess")
    repository = VerifierRepository(state)
    for revision in (1, 2):
        source = tmp_path / f"source-{revision}.py"
        tests = tmp_path / f"tests-{revision}.py"
        write_script(source, f"print({revision})\n")
        write_script(tests, "print('ok')\n")
        manifest = project_manifest(source, revision=revision)
        repository.stage(manifest, source=source, tests=tests)
        for lifecycle in (
            VerifierLifecycle.VALIDATED,
            VerifierLifecycle.TESTED,
            VerifierLifecycle.DRY_RUN,
        ):
            repository.record(manifest.verifier_id, revision, lifecycle, {"passed": True})
        if revision == 1:
            repository.freeze(
                manifest.verifier_id,
                revision,
                contract_id="contract-1",
                contract_revision=1,
                confirmation_message_id="human-1",
            )
        else:
            with pytest.raises(VerifierLifecycleError, match="new Contract revision"):
                repository.freeze(
                    manifest.verifier_id,
                    revision,
                    contract_id="contract-1",
                    contract_revision=1,
                    confirmation_message_id="human-2",
                )


def test_freeze_rejects_missing_or_undeclared_contract_revision(tmp_path: Path) -> None:
    source = tmp_path / "source.py"
    tests = tmp_path / "tests.py"
    write_script(source, "print('source')\n")
    write_script(tests, "print('tests')\n")
    repository = VerifierRepository(StateStore(tmp_path / "state.db"))
    manifest = project_manifest(source)
    repository.stage(manifest, source=source, tests=tests)
    for lifecycle in (
        VerifierLifecycle.VALIDATED,
        VerifierLifecycle.TESTED,
        VerifierLifecycle.DRY_RUN,
    ):
        repository.record(manifest.verifier_id, 1, lifecycle, {"passed": True})
    with pytest.raises(VerifierLifecycleError, match="existing frozen Contract"):
        repository.freeze(
            manifest.verifier_id,
            1,
            contract_id="missing",
            contract_revision=1,
            confirmation_message_id="human-confirm",
        )


def test_querying_lifecycle_tables_does_not_mutate_them(tmp_path: Path) -> None:
    state = StateStore(tmp_path / "state.db")
    state.migrate()
    before = state.database_migration_version
    with state.read_connection() as connection:
        list(connection.execute("SELECT * FROM verifier_revisions"))
        list(connection.execute("SELECT * FROM contract_verifier_bindings"))
    assert state.database_migration_version == before == 5
