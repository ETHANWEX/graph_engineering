from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from graph_engineering.models import ExecutorResult, VerifierResult


def test_failed_executor_result_is_not_an_error(load_fixture: Any) -> None:
    result = ExecutorResult.model_validate(load_fixture("valid/result.json"))
    assert result.status.value == "failed"
    assert result.error is None
    assert result.failure_reason


def test_error_executor_result_requires_classified_error(load_fixture: Any) -> None:
    with pytest.raises(ValidationError, match="error is required"):
        ExecutorResult.model_validate(load_fixture("invalid/result.json"))


def test_failed_verifier_requires_failure_details() -> None:
    with pytest.raises(ValidationError, match="failure_details is required"):
        VerifierResult.model_validate(
            {
                "schema_version": "1.0",
                "status": "failed",
                "summary": "Acceptance failed",
            }
        )


def test_verifier_error_is_distinct_from_failed() -> None:
    result = VerifierResult.model_validate(
        {
            "schema_version": "1.0",
            "status": "error",
            "summary": "Test runner unavailable",
            "retryable": True,
            "error": {
                "schema_version": "1.0",
                "kind": "infrastructure",
                "code": "runner.unavailable",
                "message": "No runner was available",
                "retryable": True,
            },
        }
    )
    assert result.status.value == "error"
    assert result.error is not None
