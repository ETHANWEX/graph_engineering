"""Provider-neutral structured review findings."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from graph_engineering.executor.types import ExecutorEvent, SessionHandle
from graph_engineering.models import Artifact


class ReviewVerdict(StrEnum):
    APPROVED = "approved"
    CHANGES_REQUESTED = "changes_requested"
    BLOCKED = "blocked"


class ReviewFinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    severity: str = Field(min_length=1)
    category: str = Field(min_length=1)
    file: str = Field(min_length=1)
    line: int | None = Field(default=None, ge=1)
    description: str = Field(min_length=1)
    required_change: str = Field(min_length=1)
    contract_refs: list[str] = Field(default_factory=list)


class ReviewResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    verdict: ReviewVerdict
    summary: str = Field(min_length=1)
    findings: list[ReviewFinding] = Field(default_factory=list)
    unverified: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def findings_match_verdict(self) -> ReviewResult:
        if self.verdict is ReviewVerdict.CHANGES_REQUESTED and not self.findings:
            raise ValueError("changes_requested requires at least one finding")
        if self.verdict is ReviewVerdict.APPROVED and self.findings:
            raise ValueError("approved review cannot contain required findings")
        return self


@dataclass(frozen=True)
class StructuredReviewOutcome:
    session: SessionHandle
    result: ReviewResult
    events: tuple[ExecutorEvent, ...]
    raw_stdout: Artifact
    raw_stderr: Artifact | None
    exit_code: int
