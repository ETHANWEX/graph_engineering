"""Shared, provider-neutral protocol primitives."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SchemaVersion = Literal["1.0"]


class ProtocolModel(BaseModel):
    """Immutable base with deterministic serialization for frozen evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True, use_enum_values=False)

    def canonical_json(self) -> str:
        return json.dumps(
            self.model_dump(mode="json", by_alias=True, exclude_none=True),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


class ArtifactKind(StrEnum):
    LOG = "log"
    REPORT = "report"
    PATCH = "patch"
    SOURCE = "source"
    TEST_RESULT = "test_result"
    EVIDENCE = "evidence"
    OTHER = "other"


class Artifact(ProtocolModel):
    schema_version: SchemaVersion
    artifact_id: str = Field(min_length=1)
    kind: ArtifactKind
    uri: str = Field(min_length=1, description="Opaque, provider-neutral artifact reference")
    sha256_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    media_type: str | None = None
    size_bytes: int | None = Field(default=None, ge=0)
    created_at: datetime


class Budget(ProtocolModel):
    schema_version: SchemaVersion
    max_duration_seconds: int = Field(gt=0)
    max_executor_calls: int = Field(gt=0)
    max_repair_iterations: int = Field(ge=0)
    max_cost_units: float | None = Field(default=None, gt=0)


class ErrorKind(StrEnum):
    EXECUTOR = "executor"
    VERIFIER = "verifier"
    INFRASTRUCTURE = "infrastructure"
    AUTHORIZATION = "authorization"
    POLICY = "policy"
    TIMEOUT = "timeout"
    INTERNAL = "internal"


class Error(ProtocolModel):
    schema_version: SchemaVersion
    kind: ErrorKind
    code: str = Field(min_length=1, pattern=r"^[a-z0-9_.-]+$")
    message: str = Field(min_length=1)
    retryable: bool
    details: dict[str, Any] = Field(default_factory=dict)


class ContractRef(ProtocolModel):
    schema_version: SchemaVersion
    contract_id: str = Field(min_length=1)
    revision: int = Field(ge=1)


class RunRelationship(ProtocolModel):
    schema_version: SchemaVersion
    run_id: str = Field(min_length=1)
    parent_run_id: str | None = None
    supersedes_run_id: str | None = None

    @model_validator(mode="after")
    def relationship_is_not_self_referential(self) -> RunRelationship:
        if self.run_id in {self.parent_run_id, self.supersedes_run_id}:
            raise ValueError("parent_run_id and supersedes_run_id must not equal run_id")
        return self


class RestartStrategy(StrEnum):
    CLEAN_BASE = "clean_base"
    ACCEPTED_COMMIT = "accepted_commit"
    CHECKPOINT = "checkpoint"


class RestartFrom(ProtocolModel):
    schema_version: SchemaVersion
    strategy: RestartStrategy
    reference: str | None = None

    @model_validator(mode="after")
    def reference_matches_strategy(self) -> RestartFrom:
        needs_reference = self.strategy in {
            RestartStrategy.ACCEPTED_COMMIT,
            RestartStrategy.CHECKPOINT,
        }
        if needs_reference and not self.reference:
            raise ValueError(f"reference is required for strategy {self.strategy.value}")
        if self.strategy is RestartStrategy.CLEAN_BASE and self.reference is not None:
            raise ValueError("reference must be omitted for strategy clean_base")
        return self
