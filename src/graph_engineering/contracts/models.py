"""Internal Contract lifecycle records; public TaskContract Schema remains 1.0."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from graph_engineering.models import TaskContract


class ContractLifecycleModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AcceptanceLock(ContractLifecycleModel):
    lock_id: str
    contract_id: str
    contract_revision: int = Field(ge=1)
    contract_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    verifier_hashes: dict[str, str]
    confirmation_message_id: str
    created_at: datetime


class FrozenContract(ContractLifecycleModel):
    contract: TaskContract
    acceptance_lock: AcceptanceLock


class ContractDelta(ContractLifecycleModel):
    delta_id: str
    contract_id: str
    source_revision: int = Field(ge=1)
    description: str = Field(min_length=1)
    replacement_description: str = Field(min_length=1)
