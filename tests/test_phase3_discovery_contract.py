from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from graph_engineering.contracts import (
    ContractDelta,
    ContractRepository,
    ContractRevisionError,
    RunPlanner,
)
from graph_engineering.discovery import DiscoveryRepository, DiscoveryService, ProjectScanner
from graph_engineering.models import HumanMessage, RestartFrom
from graph_engineering.models.common import RestartStrategy
from graph_engineering.runtime import StateStore


def human(message_id: str, content: str) -> HumanMessage:
    return HumanMessage(
        schema_version="1.0",
        message_id=message_id,
        actor_id="human",
        project_id="project",
        content=content,
        created_at=datetime(2026, 8, 17, tzinfo=UTC),
    )


def test_project_scan_is_deterministic_bounded_and_windows_safe(tmp_path: Path) -> None:
    (tmp_path / "b.py").write_text("b" * 20, encoding="utf-8")
    (tmp_path / "a.py").write_text("a" * 20, encoding="utf-8")
    scan = ProjectScanner(max_files=1, max_total_bytes=20).scan(tmp_path, use_git=False)

    assert [entry.path for entry in scan.entries] == ["a.py"]
    assert scan.truncated is True
    assert ProjectScanner(max_files=1, max_total_bytes=20).scan(tmp_path, use_git=False) == scan


def test_discovery_persists_unknowns_asks_for_tests_and_recovers(tmp_path: Path) -> None:
    state = StateStore(tmp_path / "state.db")
    repository = DiscoveryRepository(state)
    service = DiscoveryService(repository)
    session = service.start("conversation-1", human("m-1", "Add a greeting endpoint"), tmp_path)

    assert "verification" in {item.kind.value for item in session.unknowns if item.blocking}
    assert "test" in service.next_question(session.session_id).lower()

    recovered = DiscoveryService(DiscoveryRepository(StateStore(tmp_path / "state.db")))
    assert recovered.get(session.session_id) == session


def test_multi_turn_answers_produce_draft_but_not_acceptance_lock(tmp_path: Path) -> None:
    state = StateStore(tmp_path / "state.db")
    discovery = DiscoveryService(DiscoveryRepository(state))
    session = discovery.start("conversation-1", human("m-1", "Add a greeting endpoint"), tmp_path)
    number = 2
    while discovery.get(session.session_id).unknowns:
        current = discovery.get(session.session_id)
        unknown = current.unknowns[0]
        answer = {
            "acceptance": "GET /greeting returns 200 and hello",
            "verification": "python -m pytest",
            "dependencies": "No upstream or downstream changes",
            "conventions": "Follow existing Python style",
            "permissions": "No network or secrets",
            "delivery": "commit without merge",
            "budget": "20 calls, 1 hour, 3 repairs",
        }[unknown.kind.value]
        discovery.answer(session.session_id, human(f"m-{number}", answer))
        number += 1

    ready = discovery.get(session.session_id)
    assert ready.draft is not None and ready.state.value == "awaiting_confirmation"
    assert ContractRepository(state).locks(ready.draft.contract_id) == []


def test_explicit_confirmation_freezes_idempotently_and_revision_is_append_only(
    tmp_path: Path,
) -> None:
    state = StateStore(tmp_path / "state.db")
    repository = ContractRepository(state)
    draft = repository.example_draft("contract-1", "Implement greeting", "python -m pytest")
    draft_id = repository.stage("conversation-1", draft)
    confirmation = human("confirm-1", "I explicitly confirm this Contract")

    first = repository.freeze(draft_id, confirmation)
    second = repository.freeze(draft_id, confirmation)
    assert first == second
    assert first.contract.status.value == "frozen"
    assert len(repository.revisions("contract-1")) == 1

    with pytest.raises(ContractRevisionError):
        repository.replace_frozen(first.contract)

    revised = repository.apply_delta(
        ContractDelta(
            delta_id="delta-1",
            contract_id="contract-1",
            source_revision=1,
            description="Clarify the greeting text",
            replacement_description="Return hello world",
        ),
        human("confirm-2", "I confirm the revision"),
    )
    assert revised.contract.revision == 2
    assert revised.contract.supersedes is not None
    assert [item.revision for item in repository.revisions("contract-1")] == [1, 2]


def test_revision_creates_new_run_lineage_without_modifying_source(tmp_path: Path) -> None:
    state = StateStore(tmp_path / "state.db")
    repository = ContractRepository(state)
    first = repository.freeze(
        repository.stage(
            "conversation",
            repository.example_draft("contract-1", "Greeting v1", "python -m pytest"),
        ),
        human("confirm-1", "confirm"),
    )
    planner = RunPlanner(state)
    source = planner.create("project", first, run_id="run-1")
    source_before = planner.get(source.run_id)
    revised = repository.apply_delta(
        ContractDelta(
            delta_id="delta-1",
            contract_id="contract-1",
            source_revision=1,
            description="change greeting",
            replacement_description="Greeting v2",
        ),
        human("confirm-2", "confirm"),
    )
    child = planner.create(
        "project",
        revised,
        source_run_id="run-1",
        restart_from=RestartFrom(schema_version="1.0", strategy=RestartStrategy.CLEAN_BASE),
        run_id="run-2",
    )

    assert child.relationship.parent_run_id == "run-1"
    assert child.relationship.supersedes_run_id == "run-1"
    assert planner.get("run-1") == source_before
    assert child.graph.contract.revision == 2


def test_phase3_storage_migration_is_repeatable_and_compatibility_is_preserved(
    tmp_path: Path,
) -> None:
    state = StateStore(tmp_path / "state.db")
    state.migrate()
    state.migrate()
    assert state.storage_migration_version == 4
    assert state.latest_migration_version == 3
