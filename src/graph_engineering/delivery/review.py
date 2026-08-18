"""Deterministic multidimensional review aggregation and persistence."""

# ruff: noqa: E501

from __future__ import annotations

import json
import uuid
from collections.abc import Callable

from graph_engineering.runtime.store import StateStore, timestamp

from .models import (
    ReviewAggregate,
    ReviewAttempt,
    ReviewContext,
    ReviewDimension,
    ReviewDimensionResult,
    ReviewStatus,
    ReviewVerdict,
)


def aggregate_reviews(results: list[ReviewDimensionResult]) -> ReviewAggregate:
    by_dimension = {item.dimension: item for item in results}
    if set(by_dimension) != set(ReviewDimension) or len(results) != len(ReviewDimension):
        raise ValueError("exactly one result for every review dimension is required")
    ordered = tuple(by_dimension[item] for item in ReviewDimension)
    errors = tuple(
        f"{item.dimension.value}:{item.error_code}"
        for item in ordered
        if item.status is ReviewStatus.ERROR
    )
    findings = tuple(finding for item in ordered for finding in item.findings)
    unverified = tuple(value for item in ordered for value in item.unverified)
    evidence = tuple(sorted({value for item in ordered for value in item.evidence_refs}))
    if (
        errors
        or any(item.verdict is ReviewVerdict.BLOCKED for item in ordered)
        or any(finding.blocking for finding in findings)
    ):
        verdict = ReviewVerdict.BLOCKED
    elif any(item.verdict is ReviewVerdict.CHANGES_REQUESTED for item in ordered):
        verdict = ReviewVerdict.CHANGES_REQUESTED
    else:
        verdict = ReviewVerdict.APPROVED
    return ReviewAggregate(
        verdict=verdict,
        dimension_results=ordered,
        findings=findings,
        unverified=unverified,
        evidence_refs=evidence,
        review_errors=errors,
    )


class ReviewAttemptRepository:
    def __init__(self, state: StateStore, *, max_fix_attempts: int = 2) -> None:
        if max_fix_attempts < 0:
            raise ValueError("max_fix_attempts must be non-negative")
        self.state = state
        self.max_fix_attempts = max_fix_attempts
        state.migrate()

    def start(
        self, run_id: str, attempt_number: int, dimensions: tuple[ReviewDimension, ...]
    ) -> ReviewAttempt:
        if set(dimensions) != set(ReviewDimension) or len(dimensions) != len(ReviewDimension):
            raise ValueError("all review dimensions are required")
        session_ids = tuple(f"review-{uuid.uuid4()}" for _ in dimensions)
        with self.state.transaction() as connection:
            connection.execute(
                "INSERT INTO phase5_review_attempts(run_id, attempt_number, status, created_at) VALUES (?, ?, 'running', ?)",
                (run_id, attempt_number, timestamp()),
            )
            for dimension, session_id in zip(dimensions, session_ids, strict=True):
                connection.execute(
                    "INSERT INTO phase5_review_dimensions(run_id, attempt_number, dimension, session_id, created_at) VALUES (?, ?, ?, ?, ?)",
                    (run_id, attempt_number, dimension.value, session_id, timestamp()),
                )
            self.state.enqueue_event(
                connection, "review.attempt.started", run_id, payload={"attempt": attempt_number}
            )
        return ReviewAttempt(run_id=run_id, attempt_number=attempt_number, session_ids=session_ids)

    def record(self, run_id: str, attempt_number: int, result: ReviewDimensionResult) -> None:
        with self.state.transaction() as connection:
            row = connection.execute(
                "SELECT result_json FROM phase5_review_dimensions WHERE run_id=? AND attempt_number=? AND dimension=?",
                (run_id, attempt_number, result.dimension.value),
            ).fetchone()
            if row is None or row["result_json"] is not None:
                raise ValueError("review dimension is missing or already frozen")
            expected = connection.execute(
                "SELECT session_id FROM phase5_review_dimensions WHERE run_id=? AND attempt_number=? AND dimension=?",
                (run_id, attempt_number, result.dimension.value),
            ).fetchone()
            if str(expected["session_id"]) != result.session_id:
                raise ValueError("review result does not belong to the fresh persisted Session")
            connection.execute(
                "UPDATE phase5_review_dimensions SET result_json=? WHERE run_id=? AND attempt_number=? AND dimension=?",
                (result.model_dump_json(), run_id, attempt_number, result.dimension.value),
            )
            self.state.enqueue_event(
                connection,
                "review.dimension.finished",
                run_id,
                payload={"attempt": attempt_number, "dimension": result.dimension.value},
            )

    def invalidate_for_fix(
        self, run_id: str, attempt_number: int, *, affected_verifiers: tuple[str, ...]
    ) -> None:
        with self.state.transaction() as connection:
            count = int(
                connection.execute(
                    "SELECT COUNT(*) FROM phase5_review_attempts WHERE run_id=? AND invalidated_at IS NOT NULL",
                    (run_id,),
                ).fetchone()[0]
            )
            if count >= self.max_fix_attempts:
                raise ValueError("review-fix budget exhausted")
            changed = connection.execute(
                "UPDATE phase5_review_attempts SET status='invalidated', fix_count=?, affected_verifiers_json=?, invalidated_at=? WHERE run_id=? AND attempt_number=? AND invalidated_at IS NULL",
                (
                    count + 1,
                    json.dumps(sorted(affected_verifiers)),
                    timestamp(),
                    run_id,
                    attempt_number,
                ),
            ).rowcount
            if changed != 1:
                raise ValueError("review attempt cannot be invalidated")
            self.state.enqueue_event(
                connection,
                "review.fix.required",
                run_id,
                payload={
                    "attempt": attempt_number,
                    "affected_verifiers": sorted(affected_verifiers),
                },
            )

    def fix_count(self, run_id: str) -> int:
        with self.state.read_connection() as connection:
            return int(
                connection.execute(
                    "SELECT COUNT(*) FROM phase5_review_attempts WHERE run_id=? AND invalidated_at IS NOT NULL",
                    (run_id,),
                ).fetchone()[0]
            )


class MultidimensionalReviewRunner:
    """Run four isolated dimensions without Implementer conversation context."""

    def __init__(
        self,
        repository: ReviewAttemptRepository,
        reviewer: Callable[[ReviewDimension, ReviewContext, str], ReviewDimensionResult],
    ) -> None:
        self.repository = repository
        self.reviewer = reviewer

    def run(self, run_id: str, attempt_number: int, context: ReviewContext) -> ReviewAggregate:
        attempt = self.repository.start(run_id, attempt_number, tuple(ReviewDimension))
        results: list[ReviewDimensionResult] = []
        for dimension, session_id in zip(ReviewDimension, attempt.session_ids, strict=True):
            try:
                result = self.reviewer(dimension, context, session_id)
                if result.dimension is not dimension or result.session_id != session_id:
                    raise ValueError("Reviewer returned the wrong dimension or Session")
            except Exception as exc:
                result = ReviewDimensionResult(
                    dimension=dimension,
                    status=ReviewStatus.ERROR,
                    verdict=None,
                    summary="Reviewer invocation failed",
                    session_id=session_id,
                    sandbox="read-only",
                    error_code=f"reviewer.{type(exc).__name__}",
                )
            self.repository.record(run_id, attempt_number, result)
            results.append(result)
        return aggregate_reviews(results)
