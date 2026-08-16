"""Structured cross-Session handoff memory."""

from __future__ import annotations

import json
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class HandoffStatus(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    INTERRUPTED = "interrupted"


class Handoff(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: HandoffStatus
    summary: str = Field(min_length=1)
    changed_files: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    remaining_risks: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)

    def normalized(self) -> Handoff:
        return self.model_copy(
            update={
                "changed_files": sorted(set(self.changed_files)),
                "evidence_refs": sorted(set(self.evidence_refs)),
            }
        )

    def canonical_json(self) -> str:
        return json.dumps(
            self.normalized().model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
