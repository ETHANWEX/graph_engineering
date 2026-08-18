from __future__ import annotations

import json
import subprocess
from pathlib import Path

from graph_engineering.adapters import CodexDiscoveryAdapter, CodexPreflight
from graph_engineering.runtime import ArtifactStore


def supported_preflight() -> CodexPreflight:
    text = (
        "--json --output-schema --output-last-message --sandbox "
        "--ask-for-approval never resume review"
    )

    def run(argv: list[str]) -> subprocess.CompletedProcess[str]:
        output = (
            "codex-cli 0.147.0"
            if "--version" in argv
            else ("Logged in" if "status" in argv else text)
        )
        return subprocess.CompletedProcess(argv, 0, output, "")

    return CodexPreflight(run=run)


def test_codex_discovery_is_readonly_structured_and_preserves_raw_jsonl(tmp_path: Path) -> None:
    captured: list[list[str]] = []

    def invoke(
        argv: list[str], prompt: str, output: Path, project_root: Path
    ) -> tuple[int, str, str]:
        captured.append(argv)
        output.write_text(
            json.dumps(
                {
                    "task_title": "Greeting",
                    "task_description": "Add greeting endpoint",
                    "acceptance_criteria": ["returns hello"],
                    "missing_information": ["test command"],
                    "suggested_test_command": None,
                    "risks": [],
                }
            ),
            encoding="utf-8",
        )
        return 0, '{"type":"thread.started","thread_id":"thread-1"}\n', ""

    adapter = CodexDiscoveryAdapter(
        ArtifactStore(tmp_path / "artifacts"),
        preflight=supported_preflight(),
        invoke=invoke,
    )
    outcome = adapter.analyze(
        project_root=tmp_path,
        control_directory=tmp_path / "control",
        natural_request="Add greeting",
        repository_summary="app.py",
    )

    assert captured[0][captured[0].index("--sandbox") + 1] == "read-only"
    assert "--dangerously-bypass-approvals-and-sandbox" not in captured[0]
    assert outcome.proposal.missing_information == ["test command"]
    assert outcome.events[0].session_id == "thread-1"
    assert adapter.artifact_store.read_bytes(outcome.raw_stdout.uri)
