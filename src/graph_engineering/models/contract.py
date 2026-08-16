"""Immutable Task Contract protocol."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from .common import Budget, ContractRef, ProtocolModel, SchemaVersion


class ContractStatus(StrEnum):
    DRAFT = "draft"
    FROZEN = "frozen"


class TaskDefinition(ProtocolModel):
    schema_version: SchemaVersion
    task_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)


class AcceptanceCriterion(ProtocolModel):
    schema_version: SchemaVersion
    criterion_id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    verifier_refs: list[str] = Field(min_length=1)


class VerifierRequirement(ProtocolModel):
    schema_version: SchemaVersion
    verifier_id: str = Field(min_length=1)
    verifier_type: str = Field(min_length=1)
    timeout_seconds: int = Field(gt=0)
    required: bool = True


class ContractPolicy(ProtocolModel):
    schema_version: SchemaVersion
    protected_paths: list[str] = Field(default_factory=list)
    allowed_network_hosts: list[str] = Field(default_factory=list)
    allowed_secret_refs: list[str] = Field(default_factory=list)


class DeliveryType(StrEnum):
    PATCH = "patch"
    COMMIT = "commit"
    PULL_REQUEST = "pull_request"
    REPORT_ONLY = "report_only"


class DeliveryPolicy(ProtocolModel):
    schema_version: SchemaVersion
    delivery_type: DeliveryType
    auto_merge: Literal[False] = False


class HumanControlPolicy(ProtocolModel):
    schema_version: SchemaVersion
    non_blocking_queries: bool
    pause_allowed: bool
    interrupt_allowed: bool
    revision_creates_new_contract: Literal[True] = True
    final_acceptance_required: bool


class TaskContract(ProtocolModel):
    schema_version: SchemaVersion
    contract_id: str = Field(min_length=1)
    revision: int = Field(ge=1)
    status: ContractStatus
    supersedes: ContractRef | None = None
    task: TaskDefinition
    acceptance_criteria: list[AcceptanceCriterion] = Field(min_length=1)
    constraints: list[str] = Field(default_factory=list)
    verifiers: list[VerifierRequirement] = Field(min_length=1)
    policy: ContractPolicy
    delivery: DeliveryPolicy
    human_control: HumanControlPolicy
    budget: Budget

    @model_validator(mode="after")
    def revision_is_append_only(self) -> TaskContract:
        if self.revision == 1 and self.supersedes is not None:
            raise ValueError("revision 1 must not supersede another contract revision")
        if self.revision > 1:
            if self.supersedes is None:
                raise ValueError("revision greater than 1 must reference the superseded revision")
            if self.supersedes.contract_id != self.contract_id:
                raise ValueError("supersedes.contract_id must match contract_id")
            if self.supersedes.revision >= self.revision:
                raise ValueError("supersedes.revision must be lower than revision")
        criterion_ids = [item.criterion_id for item in self.acceptance_criteria]
        if len(criterion_ids) != len(set(criterion_ids)):
            raise ValueError("acceptance criterion IDs must be unique")
        verifier_ids = {item.verifier_id for item in self.verifiers}
        unknown = {
            ref
            for criterion in self.acceptance_criteria
            for ref in criterion.verifier_refs
            if ref not in verifier_ids
        }
        if unknown:
            raise ValueError(f"acceptance criteria reference unknown verifiers: {sorted(unknown)}")
        return self
