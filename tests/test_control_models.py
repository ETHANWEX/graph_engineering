from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from graph_engineering.models import (
    ControlIntent,
    HumanMessage,
    RunRelationship,
    StateChangeControlIntent,
)


def test_query_control_intent_is_read_only_type(load_fixture: Any) -> None:
    intent = ControlIntent.model_validate(load_fixture("valid/control.json")).root
    assert intent.intent_kind == "query"
    assert intent.requires_confirmation is False


def test_query_cannot_carry_mutating_action(load_fixture: Any) -> None:
    with pytest.raises(ValidationError):
        ControlIntent.model_validate(load_fixture("invalid/control.json"))


@pytest.mark.parametrize("action", ["pause", "resume", "interrupt", "accept", "reject"])
def test_state_change_actions_are_typed(action: str) -> None:
    intent = ControlIntent.model_validate(
        {
            "schema_version": "1.0",
            "intent_kind": "state_change",
            "intent_id": f"intent-{action}",
            "source_message_id": "message-1",
            "actor_id": "human-1",
            "project_id": "project-1",
            "run_id": "run-1",
            "action": action,
            "reason": {"schema_version": "1.0", "code": "human_request"},
            "urgency": "normal",
            "confidence": 1,
            "requires_confirmation": action in {"accept", "reject"},
        }
    ).root
    assert intent.intent_kind == "state_change"


def test_revise_and_restart_require_versioned_details() -> None:
    revise = ControlIntent.model_validate(
        {
            "schema_version": "1.0",
            "intent_kind": "state_change",
            "intent_id": "intent-revise",
            "source_message_id": "message-1",
            "actor_id": "human-1",
            "project_id": "project-1",
            "run_id": "run-1",
            "action": "revise",
            "reason": {"schema_version": "1.0", "code": "direction_change"},
            "urgency": "immediate",
            "confidence": 0.99,
            "requires_confirmation": True,
            "proposed_contract_revision": 2,
        }
    ).root
    assert isinstance(revise, StateChangeControlIntent)
    assert revise.proposed_contract_revision == 2

    restart = ControlIntent.model_validate(
        {
            "schema_version": "1.0",
            "intent_kind": "state_change",
            "intent_id": "intent-restart",
            "source_message_id": "message-2",
            "actor_id": "human-1",
            "project_id": "project-1",
            "run_id": "run-1",
            "action": "restart",
            "reason": {"schema_version": "1.0", "code": "human_request"},
            "urgency": "normal",
            "confidence": 1,
            "requires_confirmation": True,
            "restart_from": {
                "schema_version": "1.0",
                "strategy": "checkpoint",
                "reference": "checkpoint-7",
            },
        }
    ).root
    assert isinstance(restart, StateChangeControlIntent)
    assert restart.restart_from is not None


def test_human_message_is_natural_language_boundary() -> None:
    message = HumanMessage.model_validate(
        {
            "schema_version": "1.0",
            "message_id": "message-1",
            "actor_id": "human-1",
            "project_id": "project-1",
            "content": "Please pause while I inspect the evidence.",
            "created_at": "2026-08-16T08:00:00Z",
        }
    )
    assert "pause" in message.content


def test_run_relationship_supports_parent_and_supersedes() -> None:
    relationship = RunRelationship.model_validate(
        {
            "schema_version": "1.0",
            "run_id": "run-2",
            "parent_run_id": "run-1",
            "supersedes_run_id": "run-1",
        }
    )
    assert relationship.parent_run_id == relationship.supersedes_run_id
