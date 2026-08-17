"""Internal Phase 3 Discovery state models."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from graph_engineering.models import TaskContract


class DiscoveryModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DiscoveryState(StrEnum):
    COLLECTING = "collecting"
    AWAITING_ANSWERS = "awaiting_answers"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    FROZEN = "frozen"
    SUPERSEDED = "superseded"


class UnknownKind(StrEnum):
    ACCEPTANCE = "acceptance"
    VERIFICATION = "verification"
    DEPENDENCIES = "dependencies"
    CONVENTIONS = "conventions"
    PERMISSIONS = "permissions"
    DELIVERY = "delivery"
    BUDGET = "budget"


class UnknownItem(DiscoveryModel):
    unknown_id: str
    kind: UnknownKind
    question: str = Field(min_length=1)
    blocking: bool = True
    recommendation: str | None = None


class ProjectEntry(DiscoveryModel):
    path: str
    size_bytes: int = Field(ge=0)


class ProjectScan(DiscoveryModel):
    project_root: str
    entries: tuple[ProjectEntry, ...]
    included_bytes: int = Field(ge=0)
    truncated: bool


class DiscoverySession(DiscoveryModel):
    session_id: str
    conversation_id: str
    source_message_id: str
    initial_request: str
    project_root: str
    state: DiscoveryState
    scan: ProjectScan
    unknowns: tuple[UnknownItem, ...]
    answers: dict[str, str]
    draft: TaskContract | None = None
