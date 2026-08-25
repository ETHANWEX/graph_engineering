"""Deterministic review -> fix -> affected verifier -> fresh review loop."""

from __future__ import annotations

from collections.abc import Callable

from graph_engineering.observability import (
    NoOpTelemetryProvider,
    TelemetryIdentity,
    TelemetryProvider,
)

from .models import ReviewFinding, ReviewResult, ReviewVerdict


class ReviewFixCoordinator:
    def __init__(
        self,
        *,
        review: Callable[[int], ReviewResult],
        implement_fix: Callable[[list[ReviewFinding]], object],
        run_affected_verifiers: Callable[[list[ReviewFinding]], object],
        max_fix_attempts: int = 2,
        telemetry: TelemetryProvider | None = None,
        run_id: str | None = None,
    ) -> None:
        if max_fix_attempts < 0:
            raise ValueError("max_fix_attempts must be non-negative")
        self.review = review
        self.implement_fix = implement_fix
        self.run_affected_verifiers = run_affected_verifiers
        self.max_fix_attempts = max_fix_attempts
        self.telemetry = telemetry or NoOpTelemetryProvider()
        self.run_id = run_id

    def run(self) -> ReviewResult:
        for attempt in range(1, self.max_fix_attempts + 2):
            with self.telemetry.span(
                "ge.review.attempt",
                TelemetryIdentity(
                    run_id=self.run_id,
                    review_id=f"review-{attempt}",
                    attempt_id=f"review-attempt-{attempt}",
                ),
                {
                    "ge.component": "review",
                    "ge.operation": "review",
                    "ge.attempt.number": attempt,
                },
            ) as review_span:
                result = self.review(attempt)
                review_span.set_result(result.verdict.value)
            if result.verdict is not ReviewVerdict.CHANGES_REQUESTED:
                return result
            if attempt > self.max_fix_attempts:
                return ReviewResult(
                    verdict=ReviewVerdict.BLOCKED,
                    summary="review-fix attempt budget exhausted",
                    unverified=["outstanding review findings remain"],
                )
            with self.telemetry.span(
                "ge.review.fix",
                TelemetryIdentity(run_id=self.run_id, attempt_id=f"review-fix-{attempt}"),
                {"ge.component": "review", "ge.operation": "fix"},
            ) as fix_span:
                self.implement_fix(result.findings)
                self.run_affected_verifiers(result.findings)
                fix_span.set_result("succeeded")
        raise AssertionError("unreachable")
