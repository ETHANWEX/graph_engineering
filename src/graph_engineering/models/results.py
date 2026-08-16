"""Provider-neutral executor and verifier result protocols."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import Field, model_validator

from .common import Artifact, Error, ProtocolModel, SchemaVersion


class ExecutorStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    ERROR = "error"
    CANCELLED = "cancelled"


class ExecutorResult(ProtocolModel):
    schema_version: SchemaVersion
    status: ExecutorStatus
    summary: str = Field(min_length=1)
    changed_files: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    remaining_risks: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    artifacts: list[Artifact] = Field(default_factory=list)
    failure_reason: str | None = None
    error: Error | None = None

    @model_validator(mode="after")
    def distinguish_failed_from_error(self) -> ExecutorResult:
        if self.status is ExecutorStatus.FAILED and not self.failure_reason:
            raise ValueError("failure_reason is required when status is failed")
        if self.status is ExecutorStatus.ERROR and self.error is None:
            raise ValueError("error is required when status is error")
        if self.status is not ExecutorStatus.ERROR and self.error is not None:
            raise ValueError("error is only allowed when status is error")
        return self


class VerifierStatus(StrEnum):
    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    CANCELLED = "cancelled"


class VerifierResult(ProtocolModel):
    schema_version: SchemaVersion
    status: VerifierStatus
    summary: str = Field(min_length=1)
    metrics: dict[str, Any] = Field(default_factory=dict)
    artifacts: list[Artifact] = Field(default_factory=list)
    external_handle: str | None = None
    retryable: bool = False
    failure_details: list[str] = Field(default_factory=list)
    error: Error | None = None

    @model_validator(mode="after")
    def distinguish_failed_from_error(self) -> VerifierResult:
        if self.status is VerifierStatus.FAILED and not self.failure_details:
            raise ValueError("failure_details is required when status is failed")
        if self.status is VerifierStatus.ERROR and self.error is None:
            raise ValueError("error is required when status is error")
        if self.status is not VerifierStatus.ERROR and self.error is not None:
            raise ValueError("error is only allowed when status is error")
        return self
