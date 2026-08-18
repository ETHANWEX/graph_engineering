"""Provider-neutral Phase 4 Verifier SDK types."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from graph_engineering.models import Artifact, VerifierResult


class VerifierModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class NetworkCapabilities(VerifierModel):
    allow: tuple[str, ...] = ()

    @field_validator("allow")
    @classmethod
    def exact_hosts(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized: list[str] = []
        for host in value:
            candidate = host.strip().lower().rstrip(".")
            if not candidate or "://" in candidate or any(c in candidate for c in "/*? "):
                raise ValueError("network allow entries must be exact host names")
            normalized.append(candidate)
        if len(normalized) != len(set(normalized)):
            raise ValueError("network allow entries must be unique")
        return tuple(normalized)


class FilesystemCapabilities(VerifierModel):
    read: tuple[str, ...] = ()
    write: tuple[str, ...] = ()

    @field_validator("read", "write")
    @classmethod
    def paths_are_explicit(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not item.strip() or "*" in item or "?" in item for item in value):
            raise ValueError("filesystem capabilities require explicit paths")
        return value


class VerifierCapabilities(VerifierModel):
    network: NetworkCapabilities = Field(default_factory=NetworkCapabilities)
    filesystem: FilesystemCapabilities = Field(default_factory=FilesystemCapabilities)
    secrets: tuple[str, ...] = ()

    @field_validator("secrets")
    @classmethod
    def secret_references_only(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("secret references must be unique")
        for reference in value:
            if not reference or not reference.replace("_", "").isalnum():
                raise ValueError("secrets must be identifier references, never values")
        return value


class VerifierManifest(VerifierModel):
    schema_version: Literal["1.0"] = "1.0"
    verifier_id: str = Field(min_length=1)
    revision: int = Field(ge=1)
    verifier_type: Literal["builtin/command", "builtin/http-pipeline", "project/subprocess"]
    runtime: str = Field(min_length=1)
    entrypoint: tuple[str, ...] = ()
    capabilities: VerifierCapabilities = Field(default_factory=VerifierCapabilities)
    external_side_effects: bool = False

    @model_validator(mode="after")
    def entrypoint_matches_runtime(self) -> VerifierManifest:
        if self.verifier_type == "project/subprocess" and not self.entrypoint:
            raise ValueError("project/subprocess requires an argv entrypoint")
        if any(not token for token in self.entrypoint):
            raise ValueError("entrypoint argv tokens must not be empty")
        return self


class VerifierLifecycle(StrEnum):
    DRAFT = "draft"
    VALIDATED = "validated"
    TESTED = "tested"
    DRY_RUN = "dry_run"
    FROZEN = "frozen"


class VerifierRevisionHashes(VerifierModel):
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    tests_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    fixtures_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class VerifierRequest:
    run_id: str
    node_id: str
    attempt_id: str
    working_directory: Path
    artifact_directory: Path
    idempotency_key: str | None = None
    payload: dict[str, Any] | None = None


@dataclass(frozen=True)
class VerifierOutcome:
    result: VerifierResult
    artifacts: tuple[Artifact, ...] = ()
    exit_code: int | None = None


class VerifierProtocol(Protocol):
    def execute(self, request: VerifierRequest) -> VerifierOutcome: ...

    def poll(self, handle: str) -> VerifierOutcome: ...

    def cancel(self, handle: str) -> VerifierOutcome: ...
