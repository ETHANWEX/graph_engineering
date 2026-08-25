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


class BranchStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    BLOCKED = "blocked"
    ERROR = "error"
    CANCELLED = "cancelled"


class BranchResult(ProtocolModel):
    schema_version: SchemaVersion
    branch_id: str = Field(min_length=1)
    status: BranchStatus
    summary: str = Field(min_length=1)
    completed_node_ids: list[str] = Field(default_factory=list)
    changed_files: list[str] = Field(default_factory=list)
    artifacts: list[Artifact] = Field(default_factory=list)
    failure_details: list[str] = Field(default_factory=list)
    error: Error | None = None

    @model_validator(mode="after")
    def failure_semantics_are_explicit(self) -> BranchResult:
        if self.status is BranchStatus.FAILED and not self.failure_details:
            raise ValueError("failure_details is required for a failed branch")
        if self.status in {BranchStatus.ERROR, BranchStatus.BLOCKED} and self.error is None:
            raise ValueError("error is required for an error or blocked branch")
        if self.status not in {BranchStatus.ERROR, BranchStatus.BLOCKED} and self.error is not None:
            raise ValueError("error is only allowed for error or blocked branches")
        return self


class ParallelResult(ProtocolModel):
    schema_version: SchemaVersion
    parallel_node_id: str = Field(min_length=1)
    status: BranchStatus
    summary: str = Field(min_length=1)
    branches: list[BranchResult] = Field(min_length=1)
    changed_files: list[str] = Field(default_factory=list)
    artifacts: list[Artifact] = Field(default_factory=list)
    failure_details: list[str] = Field(default_factory=list)
    error: Error | None = None

    @model_validator(mode="after")
    def canonical_aggregate_is_consistent(self) -> ParallelResult:
        branch_ids = [branch.branch_id for branch in self.branches]
        if branch_ids != sorted(branch_ids) or len(branch_ids) != len(set(branch_ids)):
            raise ValueError("parallel branches must be unique and sorted by branch_id")
        precedence = {
            BranchStatus.SUCCEEDED: 0,
            BranchStatus.CANCELLED: 1,
            BranchStatus.FAILED: 2,
            BranchStatus.BLOCKED: 3,
            BranchStatus.ERROR: 4,
        }
        expected = max((branch.status for branch in self.branches), key=precedence.__getitem__)
        if self.status is not expected:
            raise ValueError("parallel status must match deterministic branch precedence")
        if self.status is BranchStatus.FAILED and not self.failure_details:
            raise ValueError("failure_details is required for failed parallel results")
        if self.status in {BranchStatus.ERROR, BranchStatus.BLOCKED} and self.error is None:
            raise ValueError("error is required for error or blocked parallel results")
        if self.status not in {BranchStatus.ERROR, BranchStatus.BLOCKED} and self.error is not None:
            raise ValueError("error is only allowed for error or blocked parallel results")
        return self
