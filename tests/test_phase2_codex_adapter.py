from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from graph_engineering.adapters.codex import (
    CodexAdapter,
    CodexJsonlParser,
    CodexPreflight,
    UnsupportedCodexCapability,
)
from graph_engineering.executor import ExecutorRequest, ExecutorRole, SandboxMode
from graph_engineering.runtime import ArtifactStore

FIXTURES = Path(__file__).parent / "fixtures" / "codex"


def completed(args: list[str], stdout: str, code: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args, code, stdout, "")


def test_preflight_records_version_login_and_required_capabilities() -> None:
    outputs = {
        ("codex", "--version"): completed([], "codex-cli 0.147.0\n"),
        ("codex", "login", "status"): completed([], "Logged in using ChatGPT\n"),
        ("codex", "--help"): completed([], "--ask-for-approval <APPROVAL_POLICY> never"),
        ("codex", "exec", "--help"): completed(
            [], "--json --output-schema <FILE> --output-last-message <FILE> --sandbox <MODE>"
        ),
        ("codex", "exec", "resume", "--help"): completed([], "resume --json --output-schema"),
        ("codex", "exec", "review", "--help"): completed([], "review --json --output-schema"),
    }

    result = CodexPreflight(run=lambda argv: outputs[tuple(argv)]).inspect()

    assert result.version == "0.147.0"
    assert result.authenticated is True
    assert result.supports_required_phase2


def test_missing_capability_rejects_before_start(tmp_path: Path) -> None:
    adapter = CodexAdapter(
        artifact_store=ArtifactStore(tmp_path / "artifacts"),
        preflight=CodexPreflight(run=lambda argv: completed(argv, "codex-cli 0.1\n")),
    )
    with pytest.raises(UnsupportedCodexCapability):
        adapter.start(_request(tmp_path))


def test_jsonl_parser_preserves_unknown_events() -> None:
    events = CodexJsonlParser().parse_lines(
        (FIXTURES / "unknown-event.jsonl").read_text(encoding="utf-8").splitlines()
    )
    assert events[0].event_type == "session_started"
    assert events[0].session_id
    assert events[1].event_type == "unknown"
    assert events[1].provider_event_type == "future.event"


def test_adapter_builds_safe_argv_and_saves_raw_events(tmp_path: Path) -> None:
    request = _request(tmp_path)
    result_json = (FIXTURES / "executor-result.json").read_text(encoding="utf-8")
    captured: list[list[str]] = []

    def invoke(argv: list[str], prompt: str, output: Path) -> tuple[int, str, str]:
        captured.append(argv)
        output.write_text(result_json, encoding="utf-8")
        return 0, (FIXTURES / "0.147.0-success.jsonl").read_text(encoding="utf-8"), ""

    adapter = CodexAdapter(
        artifact_store=ArtifactStore(tmp_path / "artifacts"),
        preflight=_supported_preflight(),
        invoke=invoke,
    )
    outcome = adapter.start(request)

    argv = captured[0]
    assert "--dangerously-bypass-approvals-and-sandbox" not in argv
    assert argv[:4] == ["codex", "--ask-for-approval", "never", "exec"]
    assert argv[argv.index("--sandbox") :][:2] == ["--sandbox", "workspace-write"]
    assert outcome.result.changed_files == ["answer.py"]
    assert outcome.session.provider_session_id.startswith("019c")
    assert adapter.artifact_store.read_bytes(outcome.raw_stdout.uri)


def test_structured_output_schema_violation_is_error(tmp_path: Path) -> None:
    def invoke(argv: list[str], prompt: str, output: Path) -> tuple[int, str, str]:
        output.write_text(json.dumps({"status": "succeeded"}), encoding="utf-8")
        return 0, (FIXTURES / "0.147.0-success.jsonl").read_text(encoding="utf-8"), ""

    adapter = CodexAdapter(
        artifact_store=ArtifactStore(tmp_path / "artifacts"),
        preflight=_supported_preflight(),
        invoke=invoke,
    )
    outcome = adapter.start(_request(tmp_path))
    assert outcome.result.status.value == "error"
    assert outcome.result.error is not None
    assert outcome.result.error.code == "codex.structured_output_invalid"


def test_codex_output_schema_requires_every_property_without_changing_public_schema() -> None:
    public: dict[str, object] = {
        "type": "object",
        "properties": {
            "required": {"type": "string"},
            "items": {"type": "array", "items": {"type": "string"}, "default": []},
        },
        "required": ["required"],
    }
    strict = CodexAdapter._strict_output_schema(public)
    assert strict["required"] == ["required", "items"]
    assert public["required"] == ["required"]
    assert "default" not in strict["properties"]["items"]  # type: ignore[index]


def _request(tmp_path: Path) -> ExecutorRequest:
    return ExecutorRequest(
        run_id="run-1",
        node_id="implement",
        attempt_id="attempt-1",
        role=ExecutorRole.IMPLEMENTER,
        objective="Implement the fixture change",
        context="bounded context",
        working_directory=tmp_path,
        sandbox=SandboxMode.WORKSPACE_WRITE,
        output_schema=json.loads(
            (Path(__file__).parents[1] / "schemas" / "ExecutorResult.schema.json").read_text(
                encoding="utf-8"
            )
        ),
        control_directory=tmp_path / "control",
    )


def _supported_preflight() -> CodexPreflight:
    text = (
        "--json --output-schema --output-last-message --sandbox "
        "--ask-for-approval never resume review"
    )
    return CodexPreflight(
        run=lambda argv: completed(
            argv,
            "codex-cli 0.147.0"
            if "--version" in argv
            else ("Logged in" if "status" in argv else text),
        )
    )
