"""Codex boundary for one fresh structured read-only Phase 5 review dimension."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from graph_engineering.delivery import (
    ReviewContext,
    ReviewDimension,
    ReviewDimensionResult,
    ReviewFinding,
    ReviewStatus,
    ReviewVerdict,
)
from graph_engineering.executor import ExecutorRequest, ExecutorRole, SandboxMode
from graph_engineering.review.models import ReviewResult, StructuredReviewOutcome


class StructuredReviewer(Protocol):
    def review_structured(self, request: ExecutorRequest) -> StructuredReviewOutcome: ...


class CodexReviewDimensionAdapter:
    def __init__(
        self,
        reviewer: StructuredReviewer,
        *,
        working_directory: Path,
        control_directory: Path,
        timeout_seconds: float = 1800,
    ) -> None:
        self.reviewer = reviewer
        self.working_directory = working_directory
        self.control_directory = control_directory
        self.timeout_seconds = timeout_seconds

    def __call__(
        self, dimension: ReviewDimension, context: ReviewContext, session_id: str
    ) -> ReviewDimensionResult:
        request = ExecutorRequest(
            run_id=f"review:{context.contract_id}:r{context.contract_revision}",
            node_id=f"review-{dimension.value}",
            attempt_id=session_id,
            role=ExecutorRole.REVIEWER,
            objective=(
                f"Perform only the {dimension.value} review dimension. Independently inspect the "
                "frozen Contract, exact Git diff, and objective evidence. Do not modify files. "
                "Do not infer approval for anything unverified."
            ),
            context=context.model_dump_json(indent=2),
            working_directory=self.working_directory,
            sandbox=SandboxMode.READ_ONLY,
            output_schema=ReviewResult.model_json_schema(),
            control_directory=self.control_directory,
            timeout_seconds=self.timeout_seconds,
        )
        outcome = self.reviewer.review_structured(request)
        result = outcome.result
        return ReviewDimensionResult(
            dimension=dimension,
            status=ReviewStatus.COMPLETED,
            verdict=ReviewVerdict(result.verdict.value),
            summary=result.summary,
            findings=tuple(
                ReviewFinding(
                    severity=finding.severity,
                    category=finding.category,
                    file=finding.file,
                    line=finding.line,
                    impact=finding.description,
                    required_change=finding.required_change,
                    contract_refs=tuple(finding.contract_refs),
                    blocking=finding.severity.casefold() in {"blocker", "critical"},
                )
                for finding in result.findings
            ),
            unverified=tuple(result.unverified),
            evidence_refs=tuple(result.evidence_refs),
            session_id=session_id,
            sandbox="read-only",
        )
