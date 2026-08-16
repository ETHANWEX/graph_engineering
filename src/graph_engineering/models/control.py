"""Human input and strongly typed runtime-control protocols."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, RootModel, model_validator

from .common import Error, ProtocolModel, RestartFrom, SchemaVersion


class HumanMessage(ProtocolModel):
    """The sole protocol input that carries a Human's natural-language text."""

    schema_version: SchemaVersion
    message_id: str = Field(min_length=1)
    actor_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    run_id: str | None = None
    content: str = Field(min_length=1)
    created_at: datetime


class QueryAction(StrEnum):
    QUERY_PROGRESS = "query_progress"
    QUERY_RISK = "query_risk"
    QUERY_EVIDENCE = "query_evidence"


class StateChangeAction(StrEnum):
    PAUSE = "pause"
    RESUME = "resume"
    INTERRUPT = "interrupt"
    REVISE = "revise"
    RESTART = "restart"
    ACCEPT = "accept"
    REJECT = "reject"


class ControlReasonCode(StrEnum):
    HUMAN_REQUEST = "human_request"
    DIRECTION_CHANGE = "direction_change"
    RISK_REVIEW = "risk_review"
    ACCEPTANCE_DECISION = "acceptance_decision"
    OTHER = "other"


class ControlReason(ProtocolModel):
    schema_version: SchemaVersion
    code: ControlReasonCode
    detail: str | None = None


class Urgency(StrEnum):
    NORMAL = "normal"
    IMMEDIATE = "immediate"


class QueryControlIntent(ProtocolModel):
    schema_version: SchemaVersion
    intent_kind: Literal["query"]
    intent_id: str = Field(min_length=1)
    source_message_id: str = Field(min_length=1)
    actor_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    action: QueryAction
    reason: ControlReason
    confidence: float = Field(ge=0, le=1)
    requires_confirmation: Literal[False] = False


class StateChangeControlIntent(ProtocolModel):
    schema_version: SchemaVersion
    intent_kind: Literal["state_change"]
    intent_id: str = Field(min_length=1)
    source_message_id: str = Field(min_length=1)
    actor_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    action: StateChangeAction
    reason: ControlReason
    urgency: Urgency
    confidence: float = Field(ge=0, le=1)
    requires_confirmation: bool
    proposed_contract_revision: int | None = Field(default=None, ge=1)
    restart_from: RestartFrom | None = None

    @model_validator(mode="after")
    def action_specific_fields(self) -> StateChangeControlIntent:
        if self.action is StateChangeAction.RESTART and self.restart_from is None:
            raise ValueError("restart_from is required for restart")
        if self.action is not StateChangeAction.RESTART and self.restart_from is not None:
            raise ValueError("restart_from is only allowed for restart")
        if self.action is StateChangeAction.REVISE and self.proposed_contract_revision is None:
            raise ValueError("proposed_contract_revision is required for revise")
        if (
            self.action is not StateChangeAction.REVISE
            and self.proposed_contract_revision is not None
        ):
            raise ValueError("proposed_contract_revision is only allowed for revise")
        return self


IntentValue = Annotated[
    QueryControlIntent | StateChangeControlIntent,
    Field(discriminator="intent_kind"),
]


class ControlIntent(RootModel[IntentValue]):
    """Discriminated union preventing query/mutation action confusion."""


class ControlOutcome(StrEnum):
    APPLIED = "applied"
    REJECTED = "rejected"
    NO_OP = "no_op"
    ERROR = "error"


class ControlActionResult(ProtocolModel):
    schema_version: SchemaVersion
    intent_id: str = Field(min_length=1)
    outcome: ControlOutcome
    state_changed: bool
    resulting_run_status: str | None = None
    message: str = Field(min_length=1)
    error: Error | None = None

    @model_validator(mode="after")
    def outcome_matches_error(self) -> ControlActionResult:
        if self.outcome is ControlOutcome.ERROR and self.error is None:
            raise ValueError("error is required when outcome is error")
        if self.outcome is not ControlOutcome.ERROR and self.error is not None:
            raise ValueError("error is only allowed when outcome is error")
        if self.outcome in {ControlOutcome.REJECTED, ControlOutcome.NO_OP} and self.state_changed:
            raise ValueError("rejected and no_op outcomes cannot report state_changed=true")
        return self
