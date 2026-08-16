from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from graph_engineering.models import TaskContract


def test_valid_contract_is_deterministic(load_fixture: Any) -> None:
    document = load_fixture("valid/contract.json")
    first = TaskContract.model_validate(document)
    second = TaskContract.model_validate(document)

    assert first.canonical_json() == second.canonical_json()
    assert first.sha256() == second.sha256()
    assert len(first.sha256()) == 64


def test_invalid_contract_rejected(load_fixture: Any) -> None:
    with pytest.raises(ValidationError) as error:
        TaskContract.model_validate(load_fixture("invalid/contract.json"))

    locations = {tuple(item["loc"]) for item in error.value.errors()}
    assert ("acceptance_criteria",) in locations
    assert ("delivery", "auto_merge") in locations


def test_contract_revision_requires_older_reference(load_fixture: Any) -> None:
    document = load_fixture("valid/contract.json")
    document["revision"] = 2
    document["supersedes"] = {
        "schema_version": "1.0",
        "contract_id": "contract-orders",
        "revision": 2,
    }

    with pytest.raises(ValidationError, match="must be lower"):
        TaskContract.model_validate(document)
