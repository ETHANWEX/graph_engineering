from __future__ import annotations

import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from runtime_helpers import budget, graph

from graph_engineering.compiler import ExecutionGraphCompiler
from graph_engineering.contracts import ContractRepository
from graph_engineering.control import NaturalLanguageControlService
from graph_engineering.conversation import ConversationRepository, IntentCompiler
from graph_engineering.models import HumanMessage
from graph_engineering.models.graph import NodeType, RouteField
from graph_engineering.runtime import (
    ArtifactStore,
    FakeExecutor,
    FakeVerifier,
    GraphRuntime,
    PersistedBarrierGuard,
    StateStore,
)
from graph_engineering.verifier import (
    CommandVerifier,
    CommandVerifierSpec,
    VerificationBarrierError,
)
from graph_engineering.workspace import GitWorkspaceManager, WorkspaceError


def human(message_id: str, content: str, run_id: str | None = None) -> HumanMessage:
    return HumanMessage(
        schema_version="1.0",
        message_id=message_id,
        actor_id="human",
        project_id="project",
        run_id=run_id,
        content=content,
        created_at=datetime(2026, 8, 17, tzinfo=UTC),
    )


def test_contract_compilation_is_deterministic_and_uses_restricted_routes(tmp_path: Path) -> None:
    repository = ContractRepository(StateStore(tmp_path / "state.db"))
    draft = repository.example_draft("contract-1", "Implement greeting", "python -m pytest")
    frozen = repository.freeze(repository.stage("conversation", draft), human("c", "confirm"))
    compiler = ExecutionGraphCompiler()

    first = compiler.compile(frozen.contract)
    second = compiler.compile(frozen.contract)
    assert first.canonical_json() == second.canonical_json()
    assert first.sha256() == second.sha256()
    assert all(
        edge.condition is None or edge.condition.field is RouteField.RESULT_STATUS
        for edge in first.edges
    )


def test_query_is_noninterfering_and_pause_persists_before_control_returns(tmp_path: Path) -> None:
    definition = graph([("implement", NodeType.AGENT, None)], [])
    runtime = GraphRuntime(tmp_path / "run", executor=FakeExecutor(), verifier=FakeVerifier())
    runtime.create_run("run-1", "project", definition, "a" * 64, budget())
    conversations = ConversationRepository(StateStore(tmp_path / "conversation.db"))
    conversations.create("conversation", "project", "human", active_run_id="run-1")
    observed: list[str] = []
    service = NaturalLanguageControlService(
        conversations,
        IntentCompiler(),
        runtime_resolver=lambda run_id: runtime,
        observer=lambda intent: observed.append(intent.action.value),
    )
    before = runtime.snapshot("run-1").execution_fingerprint()

    query_result = service.handle("conversation", human("q", "当前状态", "run-1"))
    assert query_result.applied is True and observed == ["query_progress"]
    assert runtime.snapshot("run-1").execution_fingerprint() == before

    pause_result = service.handle("conversation", human("p", "立即暂停", "run-1"))
    assert pause_result.applied is True
    assert runtime.snapshot("run-1").barrier == "pause"
    assert [item.message_id for item in conversations.messages("conversation")] == ["q", "p"]


def test_destructive_confirmation_and_duplicate_confirmation_are_idempotent(tmp_path: Path) -> None:
    definition = graph([("implement", NodeType.AGENT, None)], [])
    runtime = GraphRuntime(tmp_path / "run", executor=FakeExecutor(), verifier=FakeVerifier())
    runtime.create_run("run-1", "project", definition, "a" * 64, budget())
    conversations = ConversationRepository(StateStore(tmp_path / "conversation.db"))
    conversations.create("conversation", "project", "human", active_run_id="run-1")
    service = NaturalLanguageControlService(
        conversations, IntentCompiler(), runtime_resolver=lambda run_id: runtime
    )

    pending = service.handle("conversation", human("accept", "接受交付", "run-1"))
    assert pending.applied is False and pending.pending_confirmation_id
    recovered_conversations = ConversationRepository(StateStore(tmp_path / "conversation.db"))
    recovered_service = NaturalLanguageControlService(
        recovered_conversations, IntentCompiler(), runtime_resolver=lambda run_id: runtime
    )
    first = recovered_service.confirm(
        "conversation", pending.pending_confirmation_id, human("confirm", "明确确认", "run-1")
    )
    second = recovered_service.confirm(
        "conversation", pending.pending_confirmation_id, human("confirm-2", "再次确认", "run-1")
    )
    assert first == second


def test_natural_pause_blocks_verifier_and_worktree_side_effect_boundaries(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "fixture@example.invalid"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Fixture"], cwd=repo, check=True)
    (repo / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "app.py"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "base"], cwd=repo, check=True, capture_output=True)
    definition = graph([("implement", NodeType.AGENT, None)], [])
    runtime = GraphRuntime(tmp_path / "run", executor=FakeExecutor(), verifier=FakeVerifier())
    runtime.create_run("run-1", "project", definition, "a" * 64, budget())
    conversations = ConversationRepository(StateStore(tmp_path / "conversation.db"))
    conversations.create("conversation", "project", "human", active_run_id="run-1")
    service = NaturalLanguageControlService(
        conversations, IntentCompiler(), runtime_resolver=lambda run_id: runtime
    )
    guard = PersistedBarrierGuard(runtime.state, "run-1")
    workspace = GitWorkspaceManager(repo, tmp_path / "control-root", can_start=guard.is_open)
    verifier = CommandVerifier(ArtifactStore(tmp_path / "artifacts"), can_start=guard.is_open)

    service.handle("conversation", human("pause", "立即暂停", "run-1"))

    assert guard.is_open() is False
    with pytest.raises(VerificationBarrierError):
        verifier.run(CommandVerifierSpec(argv=(sys.executable, "--version"), cwd=repo))
    with pytest.raises(WorkspaceError):
        workspace.create("run-1")
