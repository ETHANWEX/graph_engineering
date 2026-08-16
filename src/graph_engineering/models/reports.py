"""Live and immutable terminal report protocols."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field, model_validator

from .common import (
    Artifact,
    Budget,
    ContractRef,
    Error,
    ProtocolModel,
    RunRelationship,
    SchemaVersion,
)


class RunStatus(StrEnum):
    DRAFT = "draft"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    RUNNING = "running"
    PAUSE_REQUESTED = "pause_requested"
    QUIESCING = "quiescing"
    PAUSED = "paused"
    DELIVERY_READY = "delivery_ready"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    ERROR = "error"
    INTERRUPTED = "interrupted"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class TerminalStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    ERROR = "error"
    INTERRUPTED = "interrupted"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class TerminalReason(StrEnum):
    COMPLETED = "completed"
    ACCEPTANCE_FAILED = "acceptance_failed"
    EXECUTION_ERROR = "execution_error"
    HUMAN_INTERRUPTED = "human_interrupted"
    HUMAN_CANCELLED = "human_cancelled"
    HUMAN_REJECTED = "human_rejected"
    BUDGET_EXHAUSTED = "budget_exhausted"
    AUTHORIZATION_BLOCKED = "authorization_blocked"
    CONTRACT_CONFLICT = "contract_conflict"


class BudgetUsage(ProtocolModel):
    schema_version: SchemaVersion
    duration_seconds: int = Field(ge=0)
    executor_calls: int = Field(ge=0)
    repair_iterations: int = Field(ge=0)
    cost_units: float | None = Field(default=None, ge=0)


class UnverifiedItem(ProtocolModel):
    schema_version: SchemaVersion
    item_id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    impact: str = Field(min_length=1)


class ExternalEffect(ProtocolModel):
    schema_version: SchemaVersion
    effect_id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    reversible: bool
    compensation_status: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)


class LiveReport(ProtocolModel):
    schema_version: SchemaVersion
    report_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    contract: ContractRef
    generated_at: datetime
    run_status: RunStatus
    current_node_id: str | None = None
    completed_node_ids: list[str] = Field(default_factory=list)
    progress_summary: str = Field(min_length=1)
    risks: list[str] = Field(default_factory=list)
    unverified_items: list[UnverifiedItem] = Field(default_factory=list)
    budget: Budget
    budget_usage: BudgetUsage
    artifacts: list[Artifact] = Field(default_factory=list)

    @model_validator(mode="after")
    def status_is_not_terminal(self) -> LiveReport:
        if self.run_status.value in {status.value for status in TerminalStatus}:
            raise ValueError("LiveReport cannot use a terminal run_status")
        return self


class FinalReport(ProtocolModel):
    schema_version: SchemaVersion
    report_id: str = Field(min_length=1)
    report_revision: int = Field(ge=1)
    frozen_at: datetime
    relationship: RunRelationship
    contract: ContractRef
    terminal_status: TerminalStatus
    terminal_reason: TerminalReason
    summary: str = Field(min_length=1)
    changed_files: list[str] = Field(default_factory=list)
    completed_node_ids: list[str] = Field(default_factory=list)
    verification_artifacts: list[Artifact] = Field(default_factory=list)
    review_artifacts: list[Artifact] = Field(default_factory=list)
    control_intent_ids: list[str] = Field(default_factory=list)
    unverified_items: list[UnverifiedItem] = Field(default_factory=list)
    external_effects: list[ExternalEffect] = Field(default_factory=list)
    budget_usage: BudgetUsage
    residual_risks: list[str] = Field(default_factory=list)
    error: Error | None = None

    @model_validator(mode="after")
    def status_reason_and_error_are_consistent(self) -> FinalReport:
        allowed_reasons: dict[TerminalStatus, set[TerminalReason]] = {
            TerminalStatus.SUCCEEDED: {TerminalReason.COMPLETED},
            TerminalStatus.FAILED: {
                TerminalReason.ACCEPTANCE_FAILED,
                TerminalReason.BUDGET_EXHAUSTED,
                TerminalReason.AUTHORIZATION_BLOCKED,
                TerminalReason.CONTRACT_CONFLICT,
            },
            TerminalStatus.ERROR: {TerminalReason.EXECUTION_ERROR},
            TerminalStatus.INTERRUPTED: {TerminalReason.HUMAN_INTERRUPTED},
            TerminalStatus.CANCELLED: {TerminalReason.HUMAN_CANCELLED},
            TerminalStatus.REJECTED: {TerminalReason.HUMAN_REJECTED},
        }
        if self.terminal_reason not in allowed_reasons[self.terminal_status]:
            raise ValueError("terminal_reason is incompatible with terminal_status")
        if self.terminal_status is TerminalStatus.ERROR and self.error is None:
            raise ValueError("error is required when terminal_status is error")
        if self.terminal_status is not TerminalStatus.ERROR and self.error is not None:
            raise ValueError("error is only allowed when terminal_status is error")
        return self
