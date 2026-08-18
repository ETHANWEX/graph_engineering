"""Codex boundary for project-level Verifier bundle generation."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from graph_engineering.adapters.codex import CodexAdapter, CodexJsonlParser, CodexPreflight
from graph_engineering.executor import ExecutorEvent
from graph_engineering.models import Artifact
from graph_engineering.models.common import ArtifactKind
from graph_engineering.runtime.artifacts import ArtifactStore
from graph_engineering.verifier.policy import SecretRedactor
from graph_engineering.verifier.types import VerifierManifest

GenerationInvoke = Callable[[list[str], str, Path, Path], tuple[int, str, str]]


class GeneratedFile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str = Field(min_length=1)
    content: str = Field(min_length=1)

    @field_validator("path")
    @classmethod
    def safe_relative_path(cls, value: str) -> str:
        candidate = Path(value)
        if candidate.is_absolute() or ".." in candidate.parts or value.startswith(("/", "\\")):
            raise ValueError("generated file path must be relative and cannot traverse parents")
        return candidate.as_posix()


class GeneratedVerifierBundle(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    manifest: VerifierManifest
    implementation: list[GeneratedFile] = Field(min_length=1)
    fixtures: list[GeneratedFile] = Field(min_length=1)
    tests: list[GeneratedFile] = Field(min_length=1)

    @model_validator(mode="after")
    def paths_are_unique(self) -> GeneratedVerifierBundle:
        paths = [
            item.path
            for group in (self.implementation, self.fixtures, self.tests)
            for item in group
        ]
        if len(paths) != len(set(paths)):
            raise ValueError("generated bundle paths must be unique")
        return self


@dataclass(frozen=True)
class GeneratedVerifierOutcome:
    bundle: GeneratedVerifierBundle
    events: tuple[ExecutorEvent, ...]
    raw_stdout: Artifact
    raw_stderr: Artifact | None
    provider_version: str


class CodexVerifierGenerator:
    def __init__(
        self,
        artifacts: ArtifactStore,
        *,
        executable: str = "codex",
        preflight: CodexPreflight | None = None,
        invoke: GenerationInvoke | None = None,
    ) -> None:
        self.artifacts = artifacts
        self.executable = executable
        self.preflight = preflight or CodexPreflight(executable=executable)
        self.invoke = invoke

    def generate(
        self,
        *,
        project_root: Path,
        generation_root: Path,
        description: str,
        secret_references: tuple[str, ...] = (),
        secret_values: Mapping[str, str] | None = None,
        timeout_seconds: float = 600,
    ) -> GeneratedVerifierOutcome:
        capabilities = self.preflight.inspect()
        if not capabilities.supports_required_phase2:
            raise RuntimeError("Codex lacks required JSONL/output-schema/sandbox capabilities")
        generation_root.mkdir(parents=True, exist_ok=True)
        schema_path = generation_root / "verifier-generation.output.schema.json"
        output_path = generation_root / "verifier-generation.last-message.json"
        schema_path.write_text(
            json.dumps(
                CodexAdapter._strict_output_schema(
                    GeneratedVerifierBundle.model_json_schema(mode="validation")
                ),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        argv = [
            self.executable,
            "--ask-for-approval",
            "never",
            "exec",
            "--sandbox",
            "workspace-write",
            "--json",
            "--output-schema",
            str(schema_path),
            "--output-last-message",
            str(output_path),
            "-",
        ]
        prompt = (
            "Generate an untrusted project/subprocess Verifier bundle as structured data only. "
            "Use an argv entrypoint, JSON stdin/stdout, no shell strings, bounded behavior, and "
            "include implementation, fixtures, and tests. Stdout MUST be the public VerifierResult "
            "Schema 1.0: a pass is exactly shaped like "
            '{"schema_version":"1.0","status":"passed","summary":"..."}; '
            "an acceptance failure uses status=failed, a non-empty summary, and "
            "failure_details as a non-empty array of strings. Never invent a passed boolean or "
            "a different result protocol. Tests must assert these status semantics. "
            "A relative project entrypoint must declare filesystem.read containing '.'; declare "
            "only the minimum additional filesystem paths actually used. "
            "Do not execute or freeze it. Secret "
            "values are unavailable; only these reference names may appear: "
            f"{', '.join(secret_references) or 'none'}.\n\nRequirement:\n{description}"
        )
        redactor = SecretRedactor(secret_values or {})
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
            exit_code, stdout, stderr = completed.returncode, completed.stdout, completed.stderr
        else:
            exit_code, stdout, stderr = self.invoke(argv, prompt, output_path, project_root)
        stdout = redactor.redact(stdout)
        stderr = redactor.redact(stderr)
        stdout_artifact = self.artifacts.put_bytes(
            stdout.encode("utf-8"), media_type="application/x-ndjson", kind=ArtifactKind.LOG
        )
        stderr_artifact = (
            self.artifacts.put_bytes(
                stderr.encode("utf-8"), media_type="text/plain", kind=ArtifactKind.LOG
            )
            if stderr
            else None
        )
        if exit_code != 0:
            raise RuntimeError(f"Codex Verifier generation failed with exit code {exit_code}")
        redacted_output = redactor.redact(output_path.read_text(encoding="utf-8"))
        output_path.write_text(redacted_output, encoding="utf-8")
        bundle = GeneratedVerifierBundle.model_validate_json(redacted_output)
        return GeneratedVerifierOutcome(
            bundle=bundle,
            events=CodexJsonlParser().parse_lines(stdout.splitlines()),
            raw_stdout=stdout_artifact,
            raw_stderr=stderr_artifact,
            provider_version=capabilities.version,
        )
