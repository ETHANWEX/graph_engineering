"""Multi-turn unknown resolution and Contract draft generation."""

from __future__ import annotations

from pathlib import Path

from graph_engineering.models import (
    AcceptanceCriterion,
    Budget,
    ContractPolicy,
    DeliveryPolicy,
    HumanControlPolicy,
    HumanMessage,
    TaskContract,
    TaskDefinition,
    VerifierRequirement,
)
from graph_engineering.models.contract import ContractStatus, DeliveryType

from .models import DiscoverySession, DiscoveryState, UnknownItem, UnknownKind
from .repository import DiscoveryRepository
from .scanner import ProjectScanner

_QUESTIONS: tuple[tuple[UnknownKind, str, str | None], ...] = (
    (
        UnknownKind.VERIFICATION,
        "Which test command or acceptance method must run?",
        "Use the repository's existing default test command and record its exact argv.",
    ),
    (UnknownKind.ACCEPTANCE, "What exact behavior proves the task is accepted?", None),
    (UnknownKind.DEPENDENCIES, "What upstream or downstream interfaces may change?", None),
    (UnknownKind.CONVENTIONS, "Which architecture and code-style conventions apply?", None),
    (
        UnknownKind.PERMISSIONS,
        "What filesystem, network, and secret permissions are allowed?",
        None,
    ),
    (UnknownKind.DELIVERY, "Should delivery be a patch, commit, or report only?", None),
    (UnknownKind.BUDGET, "Confirm duration, agent-call, and repair budgets.", None),
)


class DiscoveryService:
    def __init__(
        self, repository: DiscoveryRepository, scanner: ProjectScanner | None = None
    ) -> None:
        self.repository = repository
        self.scanner = scanner or ProjectScanner()

    def start(
        self, conversation_id: str, initial_message: HumanMessage, project_root: Path
    ) -> DiscoverySession:
        scan = self.scanner.scan(project_root, use_git=(project_root / ".git").exists())
        unknowns = tuple(
            UnknownItem(
                unknown_id=f"{initial_message.message_id}:{kind.value}",
                kind=kind,
                question=question,
                recommendation=recommendation,
            )
            for kind, question, recommendation in _QUESTIONS
        )
        session = DiscoverySession(
            session_id=f"discovery:{initial_message.message_id}",
            conversation_id=conversation_id,
            source_message_id=initial_message.message_id,
            initial_request=initial_message.content,
            project_root=str(project_root.resolve()),
            state=DiscoveryState.AWAITING_ANSWERS,
            scan=scan,
            unknowns=unknowns,
            answers={},
        )
        self._save(session)
        return session

    def get(self, session_id: str) -> DiscoverySession:
        return self.repository.get(session_id)

    def next_question(self, session_id: str) -> str:
        session = self.get(session_id)
        if not session.unknowns:
            return "Review and explicitly confirm the Contract draft."
        unknown = session.unknowns[0]
        if unknown.recommendation:
            return f"{unknown.question} Suggested default: {unknown.recommendation}"
        return unknown.question

    def answer(self, session_id: str, message: HumanMessage) -> DiscoverySession:
        session = self.get(session_id)
        if not session.unknowns:
            return session
        current = session.unknowns[0]
        answer = message.content.strip()
        if not answer:
            raise ValueError("Discovery answers must not be blank")
        answers = dict(session.answers)
        answers[current.kind.value] = answer
        remaining = session.unknowns[1:]
        draft = self._draft(session, answers) if not remaining else None
        updated = session.model_copy(
            update={
                "unknowns": remaining,
                "answers": answers,
                "draft": draft,
                "state": (
                    DiscoveryState.AWAITING_CONFIRMATION
                    if draft is not None
                    else DiscoveryState.AWAITING_ANSWERS
                ),
            }
        )
        self._save(updated)
        return updated

    def mark_frozen(self, session_id: str, contract: TaskContract) -> DiscoverySession:
        session = self.get(session_id)
        if session.state is not DiscoveryState.AWAITING_CONFIRMATION:
            raise ValueError("only an awaiting-confirmation Discovery can be frozen")
        updated = session.model_copy(update={"state": DiscoveryState.FROZEN, "draft": contract})
        self._save(updated)
        return updated

    def _save(self, session: DiscoverySession) -> None:
        persisted = session.model_copy(
            update={"answers": {"__initial_request": session.initial_request, **session.answers}}
        )
        self.repository.save(persisted)

    @staticmethod
    def _draft(session: DiscoverySession, answers: dict[str, str]) -> TaskContract:
        delivery_text = answers[UnknownKind.DELIVERY.value].casefold()
        delivery_type = (
            DeliveryType.COMMIT
            if "commit" in delivery_text
            else DeliveryType.PATCH
            if "patch" in delivery_text
            else DeliveryType.REPORT_ONLY
        )
        verifier_id = "project-tests"
        return TaskContract(
            schema_version="1.0",
            contract_id=f"contract:{session.conversation_id}",
            revision=1,
            status=ContractStatus.DRAFT,
            task=TaskDefinition(
                schema_version="1.0",
                task_id=f"task:{session.source_message_id}",
                title=session.initial_request[:100],
                description=session.initial_request,
            ),
            acceptance_criteria=[
                AcceptanceCriterion(
                    schema_version="1.0",
                    criterion_id="requested-behavior",
                    description=answers[UnknownKind.ACCEPTANCE.value],
                    verifier_refs=[verifier_id],
                )
            ],
            constraints=[
                answers[UnknownKind.DEPENDENCIES.value],
                answers[UnknownKind.CONVENTIONS.value],
                answers[UnknownKind.PERMISSIONS.value],
                f"verification argv: {answers[UnknownKind.VERIFICATION.value]}",
            ],
            verifiers=[
                VerifierRequirement(
                    schema_version="1.0",
                    verifier_id=verifier_id,
                    verifier_type="builtin/command",
                    timeout_seconds=600,
                )
            ],
            policy=ContractPolicy(schema_version="1.0"),
            delivery=DeliveryPolicy(schema_version="1.0", delivery_type=delivery_type),
            human_control=HumanControlPolicy(
                schema_version="1.0",
                non_blocking_queries=True,
                pause_allowed=True,
                interrupt_allowed=True,
                final_acceptance_required=True,
            ),
            budget=Budget(
                schema_version="1.0",
                max_duration_seconds=3600,
                max_executor_calls=20,
                max_repair_iterations=3,
            ),
        )
