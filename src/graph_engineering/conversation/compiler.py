"""Fail-closed compilation from HumanMessage text to typed ControlIntent."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from graph_engineering.models import (
    ControlReason,
    HumanMessage,
    QueryControlIntent,
    RestartFrom,
    StateChangeControlIntent,
)
from graph_engineering.models.common import RestartStrategy
from graph_engineering.models.control import (
    ControlReasonCode,
    QueryAction,
    StateChangeAction,
    Urgency,
)


@dataclass(frozen=True)
class IntentCompilation:
    intent: QueryControlIntent | StateChangeControlIntent | None
    confidence: float
    clarification: str | None = None


class IntentCompiler:
    minimum_confidence = 0.75

    _QUERY: ClassVar[dict[QueryAction, tuple[str, ...]]] = {
        QueryAction.QUERY_PROGRESS: ("状态", "进展", "做到", "status", "progress"),
        QueryAction.QUERY_RISK: ("风险", "risk"),
        QueryAction.QUERY_EVIDENCE: ("报告", "证据", "report", "evidence"),
    }
    _MUTATION: ClassVar[dict[StateChangeAction, tuple[str, ...]]] = {
        StateChangeAction.PAUSE: ("暂停", "pause"),
        StateChangeAction.RESUME: ("恢复", "继续", "resume"),
        StateChangeAction.INTERRUPT: ("中断", "停止当前", "interrupt"),
        StateChangeAction.REVISE: ("修订", "修改方向", "改方向", "revise"),
        StateChangeAction.RESTART: ("重新开始", "重启", "restart"),
        StateChangeAction.ACCEPT: ("接受", "验收通过", "accept"),
        StateChangeAction.REJECT: ("拒绝", "验收不通过", "reject"),
    }

    def compile(
        self,
        message: HumanMessage,
        *,
        active_run_id: str | None,
        next_contract_revision: int = 2,
    ) -> IntentCompilation:
        text = message.content.casefold()
        matches: list[QueryAction | StateChangeAction] = []
        for query_action, words in self._QUERY.items():
            if any(word.casefold() in text for word in words):
                matches.append(query_action)
        for mutation_action, words in self._MUTATION.items():
            if any(word.casefold() in text for word in words):
                matches.append(mutation_action)
        distinct = list(dict.fromkeys(matches))
        if distinct and all(isinstance(item, QueryAction) for item in distinct):
            distinct = [
                next(
                    preferred
                    for preferred in (
                        QueryAction.QUERY_PROGRESS,
                        QueryAction.QUERY_RISK,
                        QueryAction.QUERY_EVIDENCE,
                    )
                    if preferred in distinct
                )
            ]
        if len(distinct) != 1:
            if len(distinct) > 1:
                return IntentCompilation(None, 0.2, "检测到多个控制动作, 请明确只选择一个。")
            return IntentCompilation(None, 0.25, "无法可靠识别控制意图, 请明确说明查询或动作。")
        selected_action = distinct[0]
        run_id = message.run_id or active_run_id
        if run_id is None:
            return IntentCompilation(None, 0.4, "缺少明确的目标 Run, 不能执行该动作。")
        if isinstance(selected_action, QueryAction):
            return IntentCompilation(
                QueryControlIntent(
                    schema_version="1.0",
                    intent_kind="query",
                    intent_id=f"intent:{message.message_id}",
                    source_message_id=message.message_id,
                    actor_id=message.actor_id,
                    project_id=message.project_id,
                    run_id=run_id,
                    action=selected_action,
                    reason=ControlReason(
                        schema_version="1.0", code=ControlReasonCode.HUMAN_REQUEST
                    ),
                    confidence=0.99,
                ),
                0.99,
            )
        requires_confirmation = selected_action in {
            StateChangeAction.REVISE,
            StateChangeAction.RESTART,
            StateChangeAction.ACCEPT,
            StateChangeAction.REJECT,
        }
        return IntentCompilation(
            StateChangeControlIntent(
                schema_version="1.0",
                intent_kind="state_change",
                intent_id=f"intent:{message.message_id}",
                source_message_id=message.message_id,
                actor_id=message.actor_id,
                project_id=message.project_id,
                run_id=run_id,
                action=selected_action,
                reason=ControlReason(
                    schema_version="1.0",
                    code=(
                        ControlReasonCode.DIRECTION_CHANGE
                        if selected_action is StateChangeAction.REVISE
                        else ControlReasonCode.HUMAN_REQUEST
                    ),
                ),
                urgency=(
                    Urgency.IMMEDIATE
                    if selected_action in {StateChangeAction.PAUSE, StateChangeAction.INTERRUPT}
                    else Urgency.NORMAL
                ),
                confidence=0.99,
                requires_confirmation=requires_confirmation,
                proposed_contract_revision=(
                    next_contract_revision if selected_action is StateChangeAction.REVISE else None
                ),
                restart_from=(
                    RestartFrom(schema_version="1.0", strategy=RestartStrategy.CLEAN_BASE)
                    if selected_action is StateChangeAction.RESTART
                    else None
                ),
            ),
            0.99,
        )
