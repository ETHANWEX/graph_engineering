"""Provider-neutral Phase 4 Verifier SDK types."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath, PureWindowsPath
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


class ContainerImageIdentity(VerifierModel):
    registry: str = Field(min_length=1)
    repository: str = Field(min_length=1)
    digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    platform: str = Field(pattern=r"^[a-z0-9]+/[a-z0-9_]+(?:/[a-z0-9._-]+)?$")
    provenance: dict[str, str]

    @model_validator(mode="after")
    def immutable_identity(self) -> ContainerImageIdentity:
        if ":" in self.repository.rsplit("/", 1)[-1]:
            raise ValueError("container repository must not contain a mutable tag")
        if not self.provenance or any(
            not key or not value for key, value in self.provenance.items()
        ):
            raise ValueError("container image provenance must be non-empty")
        if any(token in self.registry for token in ("/", " ", "@")):
            raise ValueError("container registry must be an exact registry name")
        return self

    @property
    def reference(self) -> str:
        return f"{self.registry}/{self.repository}@{self.digest}"


class ContainerImageAllowlist(VerifierModel):
    registries: tuple[str, ...] = ()
    repositories: tuple[str, ...] = ()
    digests: tuple[str, ...] = ()

    def require(self, image: ContainerImageIdentity) -> None:
        from .policy import CapabilityViolation

        checks = (
            (self.registries, image.registry, "registry"),
            (self.repositories, image.repository, "repository"),
            (self.digests, image.digest, "digest"),
        )
        for allowed, actual, label in checks:
            if allowed and actual not in allowed:
                raise CapabilityViolation(f"container image {label} is not allowlisted: {actual}")


class ContainerResourceLimits(VerifierModel):
    cpu_count: float = Field(gt=0)
    memory_bytes: int = Field(gt=0)
    pids: int = Field(gt=0)
    timeout_seconds: float = Field(gt=0)
    max_stdout_bytes: int = Field(gt=0)
    max_stderr_bytes: int = Field(gt=0)
    max_artifact_bytes: int = Field(gt=0)
    max_concurrency: int = Field(gt=0)


class ContainerMount(VerifierModel):
    source: str = Field(min_length=1)
    target: str = Field(min_length=1)
    writable: bool = False
    classification: Literal["workspace", "artifact", "frozen", "evidence"] = "workspace"

    @model_validator(mode="after")
    def explicit_and_safe_shape(self) -> ContainerMount:
        windows = PureWindowsPath(self.source)
        posix = PurePosixPath(self.source)
        if windows.is_absolute() or windows.drive or posix.is_absolute():
            raise ValueError("container mount source must be relative to an authorized root")
        if ".." in windows.parts or ".." in posix.parts:
            raise ValueError("container mount source traversal is forbidden")
        target = PurePosixPath(self.target)
        if not target.is_absolute() or ".." in target.parts:
            raise ValueError("container mount target must be an absolute normalized POSIX path")
        if self.writable and self.classification in {"frozen", "evidence"}:
            raise ValueError("frozen and evidence mounts are read-only")
        return self


class ContainerNetworkRule(VerifierModel):
    protocol: Literal["tcp", "udp"]
    host: str = Field(min_length=1)
    port: int = Field(ge=1, le=65535)

    @field_validator("host")
    @classmethod
    def exact_host(cls, value: str) -> str:
        host = value.strip().lower().rstrip(".")
        if not host or "://" in host or any(item in host for item in ("*", "?", "/", " ")):
            raise ValueError("container network rules require an exact host")
        return host


class ContainerNetworkPolicy(VerifierModel):
    enabled: bool = False
    allow: tuple[ContainerNetworkRule, ...] = ()

    @model_validator(mode="after")
    def consistent(self) -> ContainerNetworkPolicy:
        if self.enabled != bool(self.allow):
            raise ValueError("enabled container networking requires a non-empty exact allowlist")
        if len(self.allow) != len(set(self.allow)):
            raise ValueError("container network rules must be unique")
        return self


class ContainerExecutionSpec(VerifierModel):
    image: ContainerImageIdentity
    entrypoint: tuple[str, ...]
    config: dict[str, str | int | float | bool] = Field(default_factory=dict)
    resources: ContainerResourceLimits
    mounts: tuple[ContainerMount, ...] = ()
    network: ContainerNetworkPolicy = Field(default_factory=ContainerNetworkPolicy)
    secret_environment: dict[str, str] = Field(default_factory=dict)
    artifact_paths: tuple[str, ...] = ()

    @model_validator(mode="after")
    def bounded_declaration(self) -> ContainerExecutionSpec:
        if not self.entrypoint or any(not token for token in self.entrypoint):
            raise ValueError("container entrypoint must be a non-empty argv")
        if any(token in self.entrypoint[0] for token in ("&&", "||", ";", "|", "\n", "\r")):
            raise ValueError("container entrypoint must not contain shell source")
        for name, reference in self.secret_environment.items():
            if not name or not reference or not reference.replace("_", "").isalnum():
                raise ValueError("container secret environment uses reference names only")
        return self

    def fingerprint(self) -> str:
        payload = json.dumps(
            self.model_dump(mode="json"), separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


class VerifierManifest(VerifierModel):
    schema_version: Literal["1.0"] = "1.0"
    verifier_id: str = Field(min_length=1)
    revision: int = Field(ge=1)
    verifier_type: Literal[
        "builtin/command", "builtin/http-pipeline", "project/subprocess", "project/container"
    ]
    runtime: str = Field(min_length=1)
    entrypoint: tuple[str, ...] = ()
    capabilities: VerifierCapabilities = Field(default_factory=VerifierCapabilities)
    external_side_effects: bool = False
    container: ContainerExecutionSpec | None = None

    @model_validator(mode="after")
    def entrypoint_matches_runtime(self) -> VerifierManifest:
        if self.verifier_type == "project/subprocess" and not self.entrypoint:
            raise ValueError("project/subprocess requires an argv entrypoint")
        if self.verifier_type == "project/container" and self.container is None:
            raise ValueError("project/container requires a container execution specification")
        if self.verifier_type != "project/container" and self.container is not None:
            raise ValueError("container execution specification belongs only to project/container")
        if self.container is not None and self.entrypoint != self.container.entrypoint:
            raise ValueError("container Manifest and execution entrypoints must match")
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
