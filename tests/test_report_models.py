from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from graph_engineering.models import FinalReport, LiveReport


def test_interrupted_report_discloses_incomplete_and_irreversible_work(
    load_fixture: Any,
) -> None:
    report = FinalReport.model_validate(load_fixture("valid/report.json"))
    assert report.terminal_status.value == "interrupted"
    assert report.unverified_items
    assert any(not effect.reversible for effect in report.external_effects)


def test_invalid_terminal_reason_is_rejected(load_fixture: Any) -> None:
    with pytest.raises(ValidationError, match="incompatible"):
        FinalReport.model_validate(load_fixture("invalid/report.json"))


@pytest.mark.parametrize(
    ("status", "reason"),
    [
        ("succeeded", "completed"),
        ("failed", "acceptance_failed"),
        ("interrupted", "human_interrupted"),
        ("cancelled", "human_cancelled"),
        ("rejected", "human_rejected"),
    ],
)
def test_all_required_terminal_reports_are_expressible(
    load_fixture: Any, status: str, reason: str
) -> None:
    document = load_fixture("valid/report.json")
    document["terminal_status"] = status
    document["terminal_reason"] = reason
    report = FinalReport.model_validate(document)
    assert report.terminal_status.value == status


def test_live_report_rejects_terminal_status(load_fixture: Any) -> None:
    final = load_fixture("valid/report.json")
    with pytest.raises(ValidationError, match="cannot use a terminal"):
        LiveReport.model_validate(
            {
                "schema_version": "1.0",
                "report_id": "live-1",
                "run_id": "run-1",
                "contract": final["contract"],
                "generated_at": final["frozen_at"],
                "run_status": "failed",
                "progress_summary": "Execution stopped",
                "budget": {
                    "schema_version": "1.0",
                    "max_duration_seconds": 100,
                    "max_executor_calls": 2,
                    "max_repair_iterations": 1,
                },
                "budget_usage": final["budget_usage"],
            }
        )
