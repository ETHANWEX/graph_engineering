"""Provider-neutral Phase 5 review, evidence, GitHub, and delivery models."""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class DeliveryModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ReviewDimension(StrEnum):
    CONTRACT = "contract"
    CORRECTNESS = "correctness"
    SECURITY = "security"
    TEST_ADEQUACY = "test_adequacy"


class ReviewVerdict(StrEnum):
    APPROVED = "approved"
    CHANGES_REQUESTED = "changes_requested"
    BLOCKED = "blocked"


class ReviewStatus(StrEnum):
    COMPLETED = "completed"
    ERROR = "error"


class ReviewFinding(DeliveryModel):
    severity: str = Field(min_length=1)
    category: str = Field(min_length=1)
    file: str = Field(min_length=1)
    line: int | None = Field(default=None, ge=1)
    impact: str = Field(min_length=1)
    required_change: str = Field(min_length=1)
    contract_refs: tuple[str, ...] = Field(min_length=1)
    blocking: bool = False

    @field_validator("file")
    @classmethod
    def safe_relative_location(cls, value: str) -> str:
        normalized = value.replace("\\", "/")
        if normalized.startswith("/") or "../" in f"/{normalized}":
            raise ValueError("review finding file must be a safe repository-relative path")
        return normalized


class ReviewDimensionResult(DeliveryModel):
    dimension: ReviewDimension
    status: ReviewStatus
    verdict: ReviewVerdict | None
    summary: str = Field(min_length=1)
    findings: tuple[ReviewFinding, ...] = ()
    unverified: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    session_id: str = Field(min_length=1)
    sandbox: Literal["read-only"]
    error_code: str | None = None

    @model_validator(mode="after")
    def consistent(self) -> ReviewDimensionResult:
        if self.status is ReviewStatus.ERROR:
            if self.verdict is not None or not self.error_code:
                raise ValueError("review error requires error_code and no verdict")
            return self
        if self.verdict is None or self.error_code is not None:
            raise ValueError("completed review requires a verdict and no error")
        if self.verdict is ReviewVerdict.APPROVED and (self.findings or self.unverified):
            raise ValueError("approved review cannot retain findings or unverified items")
        if self.verdict is ReviewVerdict.CHANGES_REQUESTED and not self.findings:
            raise ValueError("changes_requested requires findings")
        return self


class ReviewAggregate(DeliveryModel):
    verdict: ReviewVerdict
    dimension_results: tuple[ReviewDimensionResult, ...]
    findings: tuple[ReviewFinding, ...] = ()
    unverified: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    review_errors: tuple[str, ...] = ()


class ReviewAttempt(DeliveryModel):
    run_id: str
    attempt_number: int = Field(ge=1)
    session_ids: tuple[str, ...]


class ReviewContext(DeliveryModel):
    contract_id: str
    contract_revision: int = Field(ge=1)
    contract_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    acceptance_criteria: tuple[str, ...] = Field(min_length=1)
    baseline_commit: str = Field(pattern=r"^[0-9a-f]{40,64}$")
    target_commit: str = Field(pattern=r"^[0-9a-f]{40,64}$")
    diff_artifact_ref: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    verifier_evidence_refs: tuple[str, ...]
    repository_map_ref: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    permission_summary: str
    risk_summary: str


class MatrixStatus(StrEnum):
    VERIFIED = "verified"
    FAILED = "failed"
    UNVERIFIED = "unverified"


class EvidenceRef(DeliveryModel):
    ref: str = Field(min_length=1)
    immutable: bool | None = None
    outcome: Literal["passed", "failed", "informational"] = "passed"

    @property
    def trusted(self) -> bool:
        return self.immutable is True or bool(re.fullmatch(r"sha256:[0-9a-f]{64}", self.ref))


class RequirementMatrixRow(DeliveryModel):
    criterion_id: str
    implementation: tuple[EvidenceRef, ...] = ()
    test: tuple[EvidenceRef, ...] = ()
    verifier: tuple[EvidenceRef, ...] = ()
    ci: tuple[EvidenceRef, ...] = ()
    review: tuple[EvidenceRef, ...] = ()
    human: tuple[EvidenceRef, ...] = ()
    status: MatrixStatus
    unverified_reason: str | None = None
    artifact_refs: tuple[str, ...] = ()


class RequirementMatrixRevision(DeliveryModel):
    contract_id: str
    contract_revision: int = Field(ge=1)
    matrix_revision: int = Field(ge=1)
    rows: tuple[RequirementMatrixRow, ...]


class GitHubRepository(DeliveryModel):
    owner: str = Field(pattern=r"^[A-Za-z0-9_.-]+$")
    name: str = Field(pattern=r"^[A-Za-z0-9_.-]+$")
    api_base_url: str = "https://api.github.com"

    @field_validator("api_base_url")
    @classmethod
    def valid_api_base(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.query:
            raise ValueError("invalid GitHub API base URL")
        return value.rstrip("/")

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.name}"


class CheckStatus(StrEnum):
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    WAITING = "waiting"
    REQUESTED = "requested"
    PENDING = "pending"


class CheckConclusion(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"
    NEUTRAL = "neutral"
    SKIPPED = "skipped"
    ACTION_REQUIRED = "action_required"


class GitHubCheck(DeliveryModel):
    check_id: int
    head_sha: str = Field(pattern=r"^[0-9a-fA-F]{40,64}$")
    status: CheckStatus
    conclusion: CheckConclusion | None = None
    url: str | None = None


class GitHubChecksStatus(DeliveryModel):
    repository: str
    commit_sha: str
    checks: tuple[GitHubCheck, ...]

    @property
    def complete(self) -> bool:
        return bool(self.checks) and all(
            item.status is CheckStatus.COMPLETED for item in self.checks
        )

    @property
    def successful(self) -> bool:
        return self.complete and all(
            item.conclusion is CheckConclusion.SUCCESS for item in self.checks
        )


class PullRequestSpec(DeliveryModel):
    run_id: str
    base: str
    head: str
    title: str
    body: str
    draft: bool = True


class PullRequestContent(DeliveryModel):
    contract_revision: int = Field(ge=1)
    run_id: str
    requirement_matrix_summary: str
    verifier_ci_summary: str
    review_summary: str
    review_verdict: ReviewVerdict
    unverified: tuple[str, ...] = ()
    external_effects: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()
    final_report_refs: tuple[str, ...] = ()
    reproduction_commands: tuple[str, ...] = ()


class PullRequestHandle(DeliveryModel):
    run_id: str
    repository: str
    base: str
    head: str
    number: int
    url: str
    node_id: str


class DeliveryBundle(DeliveryModel):
    run_id: str
    revision: int
    terminal_status: str
    terminal_reason: str
    files: dict[str, str]


class HumanAcceptanceRecord(DeliveryModel):
    record_id: str
    source_message_id: str
    intent_id: str
    run_id: str
    actor_id: str
    action: Literal["accept", "reject", "revise"]
    reason: str | None
    contract_revision: int
    report_revision: int
    new_contract_revision: int | None = None
    new_run_id: str | None = None
    merge_performed: Literal[False] = False
