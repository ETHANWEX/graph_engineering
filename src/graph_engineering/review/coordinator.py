"""Deterministic review -> fix -> affected verifier -> fresh review loop."""

from __future__ import annotations

from collections.abc import Callable

from .models import ReviewFinding, ReviewResult, ReviewVerdict


class ReviewFixCoordinator:
    def __init__(
        self,
        *,
        review: Callable[[int], ReviewResult],
        implement_fix: Callable[[list[ReviewFinding]], object],
        run_affected_verifiers: Callable[[list[ReviewFinding]], object],
        max_fix_attempts: int = 2,
    ) -> None:
        if max_fix_attempts < 0:
            raise ValueError("max_fix_attempts must be non-negative")
        self.review = review
        self.implement_fix = implement_fix
        self.run_affected_verifiers = run_affected_verifiers
        self.max_fix_attempts = max_fix_attempts

    def run(self) -> ReviewResult:
        for attempt in range(1, self.max_fix_attempts + 2):
            result = self.review(attempt)
            if result.verdict is not ReviewVerdict.CHANGES_REQUESTED:
                return result
            if attempt > self.max_fix_attempts:
                return ReviewResult(
                    verdict=ReviewVerdict.BLOCKED,
                    summary="review-fix attempt budget exhausted",
                    unverified=["outstanding review findings remain"],
                )
            self.implement_fix(result.findings)
            self.run_affected_verifiers(result.findings)
        raise AssertionError("unreachable")
