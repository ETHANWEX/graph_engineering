from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from typer.testing import CliRunner

from graph_engineering.adapters import CodexVerifierGenerator
from graph_engineering.adapters.codex import CodexPreflight
from graph_engineering.cli import app
from graph_engineering.contracts import ContractRepository
from graph_engineering.models import HumanMessage
from graph_engineering.runtime import ArtifactStore, StateStore


def preflight() -> CodexPreflight:
    def run(argv: list[str]) -> subprocess.CompletedProcess[str]:
        command = " ".join(argv)
        if "--version" in command:
            output = "codex-cli 0.147.0"
        elif "login status" in command:
            output = "Logged in using ChatGPT"
        else:
            output = (
                "exec resume review --json --output-schema --output-last-message "
                "--sandbox --ask-for-approval never"
            )
        return subprocess.CompletedProcess(argv, 0, output, "")

    return CodexPreflight(run=run)


def test_codex_generation_validates_bundle_and_never_prompts_or_persists_secret(
    tmp_path: Path,
) -> None:
    captured: dict[str, str] = {}
    secret = "actual-generation-secret"

    def invoke(argv: list[str], prompt: str, output: Path, cwd: Path) -> tuple[int, str, str]:
        captured["argv"] = " ".join(argv)
        captured["prompt"] = prompt
        output.write_text(
            json.dumps(
                {
                    "manifest": {
                        "schema_version": "1.0",
                        "verifier_id": "generated-ci",
                        "revision": 1,
                        "verifier_type": "project/subprocess",
                        "runtime": "python",
                        "entrypoint": ["python", "verifier.py"],
                        "capabilities": {"secrets": ["CI_TOKEN"]},
                        "external_side_effects": False,
                    },
                    "implementation": [{"path": "verifier.py", "content": "print('ok')"}],
                    "fixtures": [{"path": "request.json", "content": "{}"}],
                    "tests": [
                        {"path": "test_verifier.py", "content": "def test_ok(): assert True"}
                    ],
                }
            ),
            encoding="utf-8",
        )
        return 0, '{"type":"thread.started"}\n' + secret, secret

    store = ArtifactStore(tmp_path / "artifacts")
    outcome = CodexVerifierGenerator(store, preflight=preflight(), invoke=invoke).generate(
        project_root=tmp_path,
        generation_root=tmp_path / "generation",
        description="Generate a project verifier",
        secret_references=("CI_TOKEN",),
        secret_values={"CI_TOKEN": secret},
    )
    assert outcome.bundle.manifest.verifier_type == "project/subprocess"
    assert "--json" in captured["argv"] and "--output-schema" in captured["argv"]
    assert "--sandbox workspace-write" in captured["argv"]
    assert secret not in captured["prompt"]
    assert secret.encode() not in store.read_bytes(outcome.raw_stdout.uri)
    assert outcome.raw_stderr is not None
    assert secret.encode() not in store.read_bytes(outcome.raw_stderr.uri)
    assert secret not in (
        tmp_path / "generation" / "verifier-generation.last-message.json"
    ).read_text(encoding="utf-8")


def test_verifier_manifest_cli_valid_and_invalid() -> None:
    runner = CliRunner()
    valid = runner.invoke(app, ["verifier", "validate", "tests/fixtures/verifier/valid.json"])
    invalid = runner.invoke(app, ["verifier", "validate", "tests/fixtures/verifier/invalid.json"])
    listed = runner.invoke(app, ["verifier", "list"])
    assert valid.exit_code == 0 and "Valid Verifier Manifest" in valid.stdout
    assert invalid.exit_code == 2 and "Invalid Verifier Manifest" in invalid.stderr
    assert "builtin/http-pipeline" in listed.stdout and "project/subprocess" in listed.stdout


def test_verifier_lifecycle_cli_validate_test_dry_run_and_freeze(tmp_path: Path) -> None:
    runner = CliRunner()
    state = tmp_path / "state.db"
    source = tmp_path / "source.json"
    tests = tmp_path / "tests.json"
    evidence = tmp_path / "evidence.json"
    source.write_text("{}", encoding="utf-8")
    tests.write_text("{}", encoding="utf-8")
    evidence.write_text('{"passed":true}', encoding="utf-8")
    contracts = ContractRepository(StateStore(state))
    draft = contracts.example_draft("contract-1", "CI acceptance", "pytest")
    requirement = draft.verifiers[0].model_copy(
        update={"verifier_id": "fixture-ci", "verifier_type": "builtin/http-pipeline"}
    )
    criterion = draft.acceptance_criteria[0].model_copy(update={"verifier_refs": ["fixture-ci"]})
    draft = draft.model_copy(
        update={"verifiers": [requirement], "acceptance_criteria": [criterion]}
    )
    contracts.freeze(
        contracts.stage("conversation", draft),
        HumanMessage(
            schema_version="1.0",
            message_id="contract-confirm",
            actor_id="human",
            project_id="project",
            content="confirm",
            created_at=datetime(2026, 8, 18, tzinfo=UTC),
        ),
    )
    validated = runner.invoke(
        app,
        [
            "verifier",
            "validate",
            "tests/fixtures/verifier/valid.json",
            "--state-db",
            str(state),
            "--source",
            str(source),
            "--tests",
            str(tests),
        ],
    )
    tested = runner.invoke(app, ["verifier", "test", str(state), "fixture-ci", "1", str(evidence)])
    dry_run = runner.invoke(
        app, ["verifier", "dry-run", str(state), "fixture-ci", "1", str(evidence)]
    )
    frozen = runner.invoke(
        app,
        [
            "verifier",
            "freeze",
            str(state),
            "fixture-ci",
            "1",
            "contract-1",
            "1",
            "human-confirm-1",
        ],
    )
    assert validated.exit_code == tested.exit_code == dry_run.exit_code == frozen.exit_code == 0
    assert "manifest_sha256" in frozen.stdout and "tests_sha256" in frozen.stdout
