from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from graph_engineering.conversation import ConversationRepository, IntentCompiler
from graph_engineering.models import HumanMessage, QueryControlIntent, StateChangeControlIntent
from graph_engineering.runtime import StateStore


def message(message_id: str, content: str, *, run_id: str | None = None) -> HumanMessage:
    return HumanMessage(
        schema_version="1.0",
        message_id=message_id,
        actor_id="human",
        project_id="project",
        run_id=run_id,
        content=content,
        created_at=datetime(2026, 8, 17, tzinfo=UTC),
    )


def test_human_messages_are_append_only_and_recover_after_restart(tmp_path: Path) -> None:
    state = StateStore(tmp_path / "state.db")
    repository = ConversationRepository(state)
    repository.create("conversation-1", "project", "human", active_run_id="run-1")
    repository.append("conversation-1", message("message-1", "现在进展如何?", run_id="run-1"))

    recovered = ConversationRepository(StateStore(tmp_path / "state.db"))
    assert recovered.get("conversation-1").active_run_id == "run-1"
    assert [item.content for item in recovered.messages("conversation-1")] == ["现在进展如何?"]


def test_query_and_mutation_compile_to_separate_protocol_types() -> None:
    compiler = IntentCompiler()
    query = compiler.compile(message("q", "请报告 run-1 的当前状态"), active_run_id="run-1")
    pause = compiler.compile(message("p", "立即暂停 run-1"), active_run_id="run-1")

    assert isinstance(query.intent, QueryControlIntent)
    assert query.intent.intent_kind == "query"
    assert isinstance(pause.intent, StateChangeControlIntent)
    assert pause.intent.action.value == "pause"


def test_ambiguous_low_confidence_and_targetless_destructive_intents_fail_closed() -> None:
    compiler = IntentCompiler()
    ambiguous = compiler.compile(message("a", "暂停然后恢复"), active_run_id="run-1")
    unclear = compiler.compile(message("u", "也许处理一下"), active_run_id="run-1")
    targetless = compiler.compile(message("t", "接受交付"), active_run_id=None)

    assert ambiguous.intent is None and ambiguous.clarification
    assert unclear.intent is None and unclear.confidence < compiler.minimum_confidence
    assert targetless.clarification is not None
    assert targetless.intent is None and "目标" in targetless.clarification


def test_revise_restart_accept_and_reject_require_confirmation() -> None:
    compiler = IntentCompiler()
    for index, content in enumerate(("修订方向", "重新开始", "接受交付", "拒绝交付")):
        compiled = compiler.compile(
            message(f"m-{index}", content, run_id="run-1"), active_run_id="run-1"
        )
        assert isinstance(compiled.intent, StateChangeControlIntent)
        assert compiled.intent.requires_confirmation is True
