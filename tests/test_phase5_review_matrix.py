from datetime import UTC, datetime
from pathlib import Path

import pytest

from graph_engineering.adapters import CodexReviewDimensionAdapter
from graph_engineering.delivery import (
    EvidenceRef,
    MatrixStatus,
    MultidimensionalReviewRunner,
    RequirementMatrixRepository,
    ReviewAttemptRepository,
    ReviewContext,
    ReviewDimension,
    ReviewDimensionResult,
    ReviewFinding,
    ReviewStatus,
    ReviewVerdict,
    aggregate_reviews,
)
from graph_engineering.executor import ExecutorRequest, SessionHandle
from graph_engineering.models import Artifact
from graph_engineering.models.common import ArtifactKind
from graph_engineering.review.models import (
    ReviewResult as CodexReviewResult,
)
from graph_engineering.review.models import (
    ReviewVerdict as CodexReviewVerdict,
)
from graph_engineering.review.models import (
    StructuredReviewOutcome,
)
from graph_engineering.runtime import StateStore


def result(dimension: ReviewDimension, verdict: ReviewVerdict) -> ReviewDimensionResult:
    finding: tuple[ReviewFinding, ...] = ()
    if verdict is ReviewVerdict.CHANGES_REQUESTED:
        finding = (
            ReviewFinding(
                severity="high",
                category="correctness",
                file="src/example.py",
                line=7,
                impact="violates frozen behavior",
                required_change="handle the boundary",
                contract_refs=("ac-1",),
            ),
        )
    return ReviewDimensionResult(
        dimension=dimension,
        status=ReviewStatus.COMPLETED,
        verdict=verdict,
        summary=verdict.value,
        findings=finding,
        evidence_refs=("sha256:" + "a" * 64,),
        session_id=f"fresh:{dimension.value}",
        sandbox="read-only",
    )


def test_review_dimensions_validate_and_aggregate_without_cancelling_blockers() -> None:
    reviews = [result(item, ReviewVerdict.APPROVED) for item in ReviewDimension]
    blocked = reviews[-1].model_copy(
        update={
            "verdict": ReviewVerdict.BLOCKED,
            "summary": "missing security evidence",
            "unverified": ("threat model",),
        }
    )
    aggregate = aggregate_reviews([*reviews[:-1], blocked])
    assert aggregate.verdict is ReviewVerdict.BLOCKED
    assert aggregate.dimension_results[-1].dimension is ReviewDimension.TEST_ADEQUACY

    errored = blocked.model_copy(
        update={"status": ReviewStatus.ERROR, "verdict": None, "error_code": "review.timeout"}
    )
    error_aggregate = aggregate_reviews([*reviews[:-1], errored])
    assert error_aggregate.verdict is ReviewVerdict.BLOCKED
    assert error_aggregate.review_errors == ("test_adequacy:review.timeout",)


def test_phase5_migration_preserves_earlier_compatibility_views(tmp_path: Path) -> None:
    state = StateStore(tmp_path / "state.db")
    state.migrate()
    assert state.schema_version == 2
    assert state.latest_migration_version == 3
    assert state.storage_migration_version == 4
    assert state.database_migration_version == 5
    assert state.delivery_migration_version == 6


def test_review_attempts_are_append_only_fresh_and_fix_budget_is_persisted(tmp_path: Path) -> None:
    repository = ReviewAttemptRepository(StateStore(tmp_path / "state.db"), max_fix_attempts=1)
    attempt1 = repository.start("run-1", 1, tuple(ReviewDimension))
    for item, session_id in zip(ReviewDimension, attempt1.session_ids, strict=True):
        repository.record(
            "run-1",
            1,
            result(item, ReviewVerdict.APPROVED).model_copy(update={"session_id": session_id}),
        )
    repository.invalidate_for_fix("run-1", 1, affected_verifiers=("tests",))
    attempt2 = repository.start("run-1", 2, tuple(ReviewDimension))
    assert set(attempt1.session_ids).isdisjoint(attempt2.session_ids)
    assert repository.fix_count("run-1") == 1
    with pytest.raises(ValueError, match="budget"):
        repository.invalidate_for_fix("run-1", 2, affected_verifiers=("tests",))


def test_requirement_matrix_has_every_row_and_requires_immutable_evidence(tmp_path: Path) -> None:
    repository = RequirementMatrixRepository(StateStore(tmp_path / "state.db"))
    matrix = repository.create(
        contract_id="contract-1",
        contract_revision=1,
        criterion_ids=("ac-1", "ac-2"),
        evidence={
            "ac-1": {"test": (EvidenceRef(ref="sha256:" + "b" * 64),)},
            "ac-2": {"implementation": (EvidenceRef(ref="working-tree:file.py"),)},
        },
    )
    assert [row.criterion_id for row in matrix.rows] == ["ac-1", "ac-2"]
    assert matrix.rows[0].status is MatrixStatus.VERIFIED
    assert matrix.rows[1].status is MatrixStatus.UNVERIFIED
    before = repository.fingerprint()
    assert repository.get("contract-1", 1, 1) == matrix
    assert repository.fingerprint() == before
    second = repository.create(
        contract_id="contract-1", contract_revision=2, criterion_ids=("ac-1",), evidence={}
    )
    assert second.contract_revision == 2
    assert repository.get("contract-1", 1, 1) == matrix


def test_multidimensional_runner_passes_only_frozen_objective_context(tmp_path: Path) -> None:
    repository = ReviewAttemptRepository(StateStore(tmp_path / "state.db"))
    seen: list[tuple[ReviewDimension, str]] = []

    def reviewer(
        dimension: ReviewDimension, context: ReviewContext, session_id: str
    ) -> ReviewDimensionResult:
        seen.append((dimension, session_id))
        assert "conversation" not in context.model_fields_set
        return result(dimension, ReviewVerdict.APPROVED).model_copy(
            update={"session_id": session_id}
        )

    context = ReviewContext(
        contract_id="contract-1",
        contract_revision=1,
        contract_hash="a" * 64,
        acceptance_criteria=("ac-1: implementation matches the frozen behavior",),
        baseline_commit="b" * 40,
        target_commit="c" * 40,
        diff_artifact_ref="sha256:" + "d" * 64,
        verifier_evidence_refs=("sha256:" + "e" * 64,),
        repository_map_ref="sha256:" + "f" * 64,
        permission_summary="read-only",
        risk_summary="network denied",
    )
    aggregate = MultidimensionalReviewRunner(repository, reviewer).run("run-1", 1, context)
    assert aggregate.verdict is ReviewVerdict.APPROVED
    assert [item[0] for item in seen] == list(ReviewDimension)
    assert len({item[1] for item in seen}) == 4


def test_codex_dimension_adapter_always_builds_fresh_readonly_structured_request(
    tmp_path: Path,
) -> None:
    requests: list[ExecutorRequest] = []

    class Reviewer:
        def review_structured(self, request: ExecutorRequest) -> StructuredReviewOutcome:
            requests.append(request)
            artifact = Artifact(
                schema_version="1.0",
                artifact_id="sha256:" + "a" * 64,
                kind=ArtifactKind.LOG,
                uri="sha256/aa/value",
                sha256_digest="a" * 64,
                size_bytes=0,
                created_at=datetime.now(UTC),
            )
            return StructuredReviewOutcome(
                session=SessionHandle("codex", f"provider-{len(requests)}", "0.147.0"),
                result=CodexReviewResult(
                    verdict=CodexReviewVerdict.APPROVED,
                    summary="independently approved",
                ),
                events=(),
                raw_stdout=artifact,
                raw_stderr=None,
                exit_code=0,
            )

    context = ReviewContext(
        contract_id="contract-1",
        contract_revision=1,
        contract_hash="a" * 64,
        acceptance_criteria=("ac-1: answer returns 42",),
        baseline_commit="b" * 40,
        target_commit="c" * 40,
        diff_artifact_ref="sha256:" + "d" * 64,
        verifier_evidence_refs=("sha256:" + "e" * 64,),
        repository_map_ref="sha256:" + "f" * 64,
        permission_summary="read-only",
        risk_summary="no secrets",
    )
    adapter = CodexReviewDimensionAdapter(
        Reviewer(), working_directory=tmp_path, control_directory=tmp_path / "control"
    )
    first = adapter(ReviewDimension.SECURITY, context, "review-one")
    adapter(ReviewDimension.SECURITY, context, "review-two")
    assert first.verdict is ReviewVerdict.APPROVED
    assert requests[0].sandbox.value == "read-only"
    assert requests[0].role.value == "reviewer"
    assert requests[0].attempt_id != requests[1].attempt_id
    assert "conversation" not in requests[0].context
