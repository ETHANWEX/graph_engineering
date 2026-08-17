"""Codex read-only structured Discovery Adapter."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from graph_engineering.adapters.codex import (
    CodexAdapter,
    CodexJsonlParser,
    CodexPreflight,
    UnsupportedCodexCapability,
)
from graph_engineering.executor import ExecutorEvent
from graph_engineering.models import Artifact
from graph_engineering.models.common import ArtifactKind
from graph_engineering.runtime import ArtifactStore

DiscoveryInvoke = Callable[[list[str], str, Path, Path], tuple[int, str, str]]


class CodexDiscoveryProposal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    task_title: str = Field(min_length=1)
    task_description: str = Field(min_length=1)
    acceptance_criteria: list[str]
    missing_information: list[str]
    suggested_test_command: str | None
    risks: list[str]


@dataclass(frozen=True)
class CodexDiscoveryOutcome:
    proposal: CodexDiscoveryProposal
    events: tuple[ExecutorEvent, ...]
    raw_stdout: Artifact
    raw_stderr: Artifact | None
    provider_version: str


class CodexDiscoveryAdapter:
    def __init__(
        self,
        artifact_store: ArtifactStore,
        *,
        preflight: CodexPreflight | None = None,
        executable: str = "codex",
        invoke: DiscoveryInvoke | None = None,
    ) -> None:
        self.artifact_store = artifact_store
        self.preflight = preflight or CodexPreflight(executable=executable)
        self.executable = executable
        self.invoke = invoke

    def analyze(
        self,
        *,
        project_root: Path,
        control_directory: Path,
        natural_request: str,
        repository_summary: str,
        timeout_seconds: float = 300,
    ) -> CodexDiscoveryOutcome:
        capabilities = self.preflight.inspect()
        if not capabilities.supports_required_phase2:
            raise UnsupportedCodexCapability(
                f"Codex {capabilities.version} lacks required structured read-only capabilities"
            )
        control_directory.mkdir(parents=True, exist_ok=True)
        schema_path = control_directory / "discovery.output.schema.json"
        output_path = control_directory / "discovery.last-message.json"
        schema = CodexAdapter._strict_output_schema(
            CodexDiscoveryProposal.model_json_schema(mode="validation")
        )
        schema_path.write_text(
            json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        argv = [
            self.executable,
            "--ask-for-approval",
            "never",
            "exec",
            "--sandbox",
            "read-only",
            "--json",
            "--output-schema",
            str(schema_path),
            "--output-last-message",
            str(output_path),
            "-",
        ]
        prompt = (
            "Perform read-only requirement discovery. Do not modify files or start implementation. "
            "Return only the requested structured proposal. Treat missing tests, acceptance, "
            "permissions, dependencies, or delivery details as missing_information; "
            "do not guess.\n\n"
            f"Human request:\n{natural_request}\n\nRepository summary:\n{repository_summary}"
        )
        if self.invoke is None:
            completed = subprocess.run(
                argv,
                cwd=project_root,
                input=prompt,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                check=False,
                timeout=timeout_seconds,
                shell=False,
            )
            exit_code, stdout, stderr = (
                completed.returncode,
                completed.stdout,
                completed.stderr,
            )
        else:
            exit_code, stdout, stderr = self.invoke(argv, prompt, output_path, project_root)
        stdout_artifact = self.artifact_store.put_bytes(
            stdout.encode("utf-8"), media_type="application/x-ndjson", kind=ArtifactKind.LOG
        )
        stderr_artifact = (
            self.artifact_store.put_bytes(
                stderr.encode("utf-8"), media_type="text/plain", kind=ArtifactKind.LOG
            )
            if stderr
            else None
        )
        if exit_code != 0:
            raise RuntimeError(f"Codex Discovery failed with exit code {exit_code}")
        proposal = CodexDiscoveryProposal.model_validate_json(
            output_path.read_text(encoding="utf-8")
        )
        events = CodexJsonlParser().parse_lines(stdout.splitlines())
        return CodexDiscoveryOutcome(
            proposal=proposal,
            events=events,
            raw_stdout=stdout_artifact,
            raw_stderr=stderr_artifact,
            provider_version=capabilities.version,
        )
