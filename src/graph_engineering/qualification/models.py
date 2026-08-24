"""Strict models for Phase 6E qualification evidence."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EvidenceClassification(StrEnum):
    DETERMINISTIC_FIXTURE = "deterministic_fixture"
    REAL_LOCAL_INTEGRATION = "real_local_integration"
    REAL_EXTERNAL_INTEGRATION = "real_external_integration"
    SUPPORTED_PLATFORM = "supported_platform_evidence"
    BLOCKED = "blocked"
    UNVERIFIED = "unverified"


class EvidenceResult(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    BLOCKED = "blocked"
    UNVERIFIED = "unverified"


class AuthenticationState(StrEnum):
    AUTHENTICATED = "authenticated"
    UNAUTHENTICATED = "unauthenticated"
    UNAVAILABLE = "unavailable"
    NOT_CHECKED = "not_checked"
    NOT_AUTHORIZED = "not_authorized"


class CleanupState(StrEnum):
    NOT_REQUIRED = "not_required"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    UNKNOWN = "unknown"


class EvidenceCounts(StrictModel):
    collected: int = Field(default=0, ge=0)
    passed: int = Field(default=0, ge=0)
    failed: int = Field(default=0, ge=0)
    skipped: int = Field(default=0, ge=0)
    blocked: int = Field(default=0, ge=0)
    unverified: int = Field(default=0, ge=0)


class ProductVersions(StrictModel):
    product: str
    package: str
    plugin: str
    runtime_api: str
    ipc: str
    mcp: str
    migration_head: int = Field(ge=1)
    schema_count: int = Field(ge=1)


class GitIdentity(StrictModel):
    repository: str
    commit: str
    branch: str
    dirty: bool


class HostIdentity(StrictModel):
    os: str
    os_version: str
    architecture: str
    shell: str
    filesystem: str
    python: str


class ToolIdentity(StrictModel):
    name: str
    available: bool
    version: str | None = None
    authentication: AuthenticationState = AuthenticationState.NOT_CHECKED
    endpoint_identity: str | None = None


class QualificationClaim(StrictModel):
    claim_id: str
    product_claim: str
    required_environment: str
    evidence_classification: EvidenceClassification
    operation: str
    result: EvidenceResult
    counts: EvidenceCounts = EvidenceCounts()
    artifact_refs: tuple[str, ...] = ()
    started_at: datetime | None = None
    ended_at: datetime | None = None
    duration_seconds: float | None = Field(default=None, ge=0)
    exit_code: int | None = None
    limitation: str | None = None
    cleanup: CleanupState = CleanupState.NOT_REQUIRED
    residual_effects: tuple[str, ...] = ()
    recovery_guidance: str | None = None
    conclusion: Literal["supported", "unsupported", "blocked", "unverified", "failed"]

    @model_validator(mode="after")
    def validate_result_semantics(self) -> QualificationClaim:
        if (
            self.evidence_classification
            in {
                EvidenceClassification.BLOCKED,
                EvidenceClassification.UNVERIFIED,
            }
            and self.result is EvidenceResult.PASSED
        ):
            raise ValueError("blocked or unverified evidence cannot be passed")
        if self.result is EvidenceResult.PASSED and any(
            (self.counts.failed, self.counts.blocked, self.counts.unverified)
        ):
            raise ValueError("passed evidence cannot contain non-passing counts")
        if self.result is EvidenceResult.PASSED and self.counts.skipped and not self.limitation:
            raise ValueError("passed evidence with explicit skips must disclose their limitation")
        if self.result is EvidenceResult.BLOCKED and self.conclusion != "blocked":
            raise ValueError("blocked evidence requires a blocked conclusion")
        if self.result is EvidenceResult.UNVERIFIED and self.conclusion != "unverified":
            raise ValueError("unverified evidence requires an unverified conclusion")
        return self


class QualificationEvidence(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    qualification_version: Literal["1.0"] = "1.0"
    run_id: str
    started_at: datetime
    ended_at: datetime
    duration_seconds: float = Field(ge=0)
    versions: ProductVersions
    git: GitIdentity
    host: HostIdentity
    tools: tuple[ToolIdentity, ...]
    claims: tuple[QualificationClaim, ...]
    counts: EvidenceCounts
    cleanup: CleanupState
    residual_external_effects: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    recovery_guidance: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_identity_and_counts(self) -> QualificationEvidence:
        if self.ended_at < self.started_at:
            raise ValueError("qualification end precedes start")
        expected = EvidenceCounts(
            collected=len(self.claims),
            passed=sum(item.result is EvidenceResult.PASSED for item in self.claims),
            failed=sum(item.result is EvidenceResult.FAILED for item in self.claims),
            blocked=sum(item.result is EvidenceResult.BLOCKED for item in self.claims),
            unverified=sum(item.result is EvidenceResult.UNVERIFIED for item in self.claims),
        )
        if self.counts != expected:
            raise ValueError("qualification aggregate counts do not match claims")
        if len({item.claim_id for item in self.claims}) != len(self.claims):
            raise ValueError("qualification claim IDs must be unique")
        return self
