"""Durable explicit-start coordinator for the Phase 6D product path."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, cast

from graph_engineering.models import Error, ExecutionGraph, TaskContract
from graph_engineering.models.common import ErrorKind
from graph_engineering.models.results import ExecutorResult, ExecutorStatus
from graph_engineering.runtime import ArtifactStore, GraphRuntime, StateStore
from graph_engineering.runtime.store import timestamp

from .control import HumanDecisionService
from .models import (
    DeliveryBundle,
    HumanAcceptanceRecord,
    ReviewAggregate,
    ReviewVerdict,
)
from .report import DeliveryReportCompiler


class RunStartError(RuntimeError):
    """A typed explicit-start failure."""


class RunStartUncertainError(RunStartError):
    """A previous start claim has no authoritative completion record."""


@dataclass(frozen=True)
class AutonomousRunResult:
    run_id: str
    runtime_status: str
    report_revision: int
    idempotency_key: str


class AutonomousDeliveryCoordinator:
    """Compose a prepared Contract with the existing authoritative Graph Runtime.

    The coordinator owns only the explicit-start claim and product hand-off. Scheduling,
    attempts, checkpoints, barriers, budgets and terminal state remain GraphRuntime facts.
    """

    def __init__(
        self,
        project_root: Path,
        *,
        executor: Any,
        verifier: Any,
        reviewer: Any | None = None,
        delivery_provider: Any | None = None,
    ) -> None:
        self.project_root = project_root.resolve()
        self.control = StateStore(self.project_root / ".ge" / "control" / "phase3.db")
        self.control.migrate()
        self.executor = executor
        self.verifier = verifier
        self.reviewer = reviewer
        self.delivery_provider = delivery_provider

    def run(self, run_id: str, *, request_id: str, idempotency_key: str) -> AutonomousRunResult:
        if not request_id or not idempotency_key:
            raise RunStartError("request and idempotency identities are required")
        planned, graph, contract = self._load_and_verify_prepared(run_id)
        fingerprint = hashlib.sha256(
            "\0".join((run_id, str(planned["graph_hash"]), contract.sha256())).encode()
        ).hexdigest()
        replay = self._claim(run_id, request_id, idempotency_key, fingerprint)
        if replay is not None:
            return replay

        run_root = self._run_root(run_id)
        runtime_executor = _CoordinatorExecutor(
            StateStore(run_root / "state.db"),
            self.executor,
            reviewer=self.reviewer,
            delivery_provider=self.delivery_provider,
        )
        runtime = GraphRuntime(run_root, executor=runtime_executor, verifier=self.verifier)
        try:
            self._copy_frozen_inputs(runtime.state, run_id)
            with runtime.state.read_connection() as connection:
                existing = connection.execute(
                    "SELECT 1 FROM runs WHERE run_id=?", (run_id,)
                ).fetchone()
            if existing is None:
                runtime.create_run(
                    run_id,
                    str(planned["project_id"]),
                    graph,
                    contract.sha256(),
                    contract.budget,
                )
            else:
                runtime.recover(run_id, graph, contract.sha256())
            status = runtime.run(run_id)
            if status.value not in {
                "succeeded",
                "failed",
                "error",
                "interrupted",
                "cancelled",
                "rejected",
            }:
                raise RunStartError(f"Run stopped in nonterminal state: {status.value}")
            compiler = DeliveryReportCompiler(
                runtime.state, runtime.artifacts, run_root / "reports"
            )
            try:
                bundle = compiler.latest(run_id)
            except KeyError:
                bundle = compiler.compile(run_id)
            result = AutonomousRunResult(
                run_id=run_id,
                runtime_status=status.value,
                report_revision=bundle.revision,
                idempotency_key=idempotency_key,
            )
            self._complete(result)
            return result
        except Exception:
            # The claim intentionally remains executing. Recovery cannot guess whether an
            # uncheckpointed Session/provider effect happened, so replay fails closed.
            raise

    def decide(
        self,
        action: str,
        message: Any,
        *,
        reason: str = "",
        report_revision: int,
    ) -> HumanAcceptanceRecord:
        """Persist a terminal Human decision and synchronize immutable revision lineage."""

        if message.run_id is None:
            raise RunStartError("Human decision requires a Run target")
        run_root = self._run_root(str(message.run_id))
        state = StateStore(run_root / "state.db")
        service = HumanDecisionService(state)
        if action == "accept":
            record = service.accept(message, report_revision=report_revision)
        elif action == "reject":
            record = service.reject(message, reason=reason, report_revision=report_revision)
        elif action == "revise":
            record = service.revise(message, reason=reason, report_revision=report_revision)
        else:
            raise RunStartError("unsupported Human terminal decision")
        if record.new_contract_revision is not None:
            self._copy_revision_to_control(
                state, record.run_id, record.new_contract_revision, record.new_run_id
            )
        DeliveryReportCompiler(
            state, ArtifactStore(run_root / "artifacts"), run_root / "reports"
        ).compile(record.run_id)
        return record

    def report(self, run_id: str) -> DeliveryBundle:
        root = self._run_root(run_id)
        return DeliveryReportCompiler(
            StateStore(root / "state.db"), ArtifactStore(root / "artifacts"), root / "reports"
        ).latest(run_id)

    def claim_start_for_test(self, run_id: str, idempotency_key: str) -> None:
        """Create the exact crash-boundary fixture without issuing any side effect."""

        planned, _, contract = self._load_and_verify_prepared(run_id)
        fingerprint = hashlib.sha256(
            "\0".join((run_id, str(planned["graph_hash"]), contract.sha256())).encode()
        ).hexdigest()
        self._claim(run_id, "fixture-claim", idempotency_key, fingerprint)

    def _claim(
        self, run_id: str, request_id: str, idempotency_key: str, fingerprint: str
    ) -> AutonomousRunResult | None:
        with self.control.transaction() as connection:
            row = connection.execute(
                "SELECT * FROM run_start_requests WHERE idempotency_key=?",
                (idempotency_key,),
            ).fetchone()
            if row is not None:
                if str(row["request_fingerprint"]) != fingerprint or str(row["run_id"]) != run_id:
                    raise RunStartError("run-start idempotency identity collision")
                if str(row["state"]) == "completed" and row["result_json"] is not None:
                    return AutonomousRunResult(**json.loads(str(row["result_json"])))
                raise RunStartUncertainError(
                    "run start was claimed but its outcome is unknown; refusing duplicate execution"
                )
            planned = connection.execute(
                "SELECT status FROM planned_runs WHERE run_id=?", (run_id,)
            ).fetchone()
            if planned is None:
                raise RunStartError("prepared Run was not found")
            if str(planned["status"]) == "start_claimed":
                raise RunStartUncertainError(
                    "run start was claimed under another identity; refusing duplicate execution"
                )
            if str(planned["status"]) != "prepared":
                raise RunStartError("Run has already left the prepared state")
            connection.execute(
                "INSERT INTO run_start_requests(idempotency_key,request_id,run_id,"
                "request_fingerprint,state,created_at) VALUES (?,?,?,?, 'executing', ?)",
                (idempotency_key, request_id, run_id, fingerprint, timestamp()),
            )
            connection.execute(
                "UPDATE planned_runs SET status='start_claimed' "
                "WHERE run_id=? AND status='prepared'",
                (run_id,),
            )
            self.control.enqueue_event(
                connection,
                "run.start.claimed",
                run_id,
                payload={"request_id": request_id, "idempotency_key": idempotency_key},
            )
        return None

    def _complete(self, result: AutonomousRunResult) -> None:
        with self.control.transaction() as connection:
            connection.execute(
                "UPDATE run_start_requests SET state='completed',result_json=?,completed_at=? "
                "WHERE idempotency_key=? AND state='executing'",
                (
                    json.dumps(asdict(result), separators=(",", ":"), sort_keys=True),
                    timestamp(),
                    result.idempotency_key,
                ),
            )
            connection.execute(
                "UPDATE planned_runs SET status='started' WHERE run_id=?",
                (result.run_id,),
            )
            self.control.enqueue_event(
                connection,
                "run.start.completed",
                result.run_id,
                payload={"runtime_status": result.runtime_status},
            )

    def _load_and_verify_prepared(self, run_id: str) -> tuple[Any, ExecutionGraph, TaskContract]:
        with self.control.read_connection() as connection:
            planned = connection.execute(
                "SELECT * FROM planned_runs WHERE run_id=?", (run_id,)
            ).fetchone()
            if planned is None:
                raise KeyError(run_id)
            contract_row = connection.execute(
                "SELECT contract_json,contract_hash FROM contract_revisions "
                "WHERE contract_id=? AND revision=?",
                (str(planned["contract_id"]), int(planned["contract_revision"])),
            ).fetchone()
            lock = connection.execute(
                "SELECT contract_hash FROM acceptance_locks "
                "WHERE contract_id=? AND contract_revision=?",
                (str(planned["contract_id"]), int(planned["contract_revision"])),
            ).fetchone()
        if contract_row is None or lock is None:
            raise RunStartError("frozen Contract or acceptance lock is missing")
        contract = TaskContract.model_validate_json(str(contract_row["contract_json"]))
        graph = ExecutionGraph.model_validate_json(str(planned["graph_json"]))
        if (
            contract.sha256() != str(contract_row["contract_hash"])
            or contract.sha256() != str(lock["contract_hash"])
            or graph.sha256() != str(planned["graph_hash"])
            or graph.contract.contract_id != contract.contract_id
            or graph.contract.revision != contract.revision
        ):
            raise RunStartError("frozen Contract, acceptance lock, or Graph drift detected")
        return planned, graph, contract

    def _run_root(self, run_id: str) -> Path:
        if not run_id or any(value in run_id for value in ("/", "\\", "..")):
            raise RunStartError("Run identity is invalid")
        root = (self.project_root / ".ge" / "runs" / run_id).resolve()
        if root.parent != (self.project_root / ".ge" / "runs").resolve():
            raise RunStartError("Run path escaped the project")
        return root

    def _copy_frozen_inputs(self, target: StateStore, run_id: str) -> None:
        with self.control.read_connection() as connection:
            planned = connection.execute(
                "SELECT contract_id,contract_revision FROM planned_runs WHERE run_id=?", (run_id,)
            ).fetchone()
            if planned is None:
                raise KeyError(run_id)
            contract = connection.execute(
                "SELECT * FROM contract_revisions WHERE contract_id=? AND revision=?",
                (planned["contract_id"], planned["contract_revision"]),
            ).fetchone()
            lock = connection.execute(
                "SELECT * FROM acceptance_locks WHERE contract_id=? AND contract_revision=?",
                (planned["contract_id"], planned["contract_revision"]),
            ).fetchone()
        if contract is None or lock is None:
            raise RunStartError("frozen inputs are incomplete")
        with target.transaction() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO contract_revisions(contract_id,revision,contract_json,"
                "contract_hash,confirmation_message_id,frozen_at) VALUES (?,?,?,?,?,?)",
                tuple(contract),
            )
            connection.execute(
                "INSERT OR IGNORE INTO acceptance_locks(lock_id,contract_id,contract_revision,"
                "contract_hash,verifier_hashes_json,confirmation_message_id,created_at) "
                "VALUES (?,?,?,?,?,?,?)",
                tuple(lock),
            )

    def _copy_revision_to_control(
        self, source: StateStore, source_run_id: str, revision: int, new_run_id: str | None
    ) -> None:
        with source.read_connection() as connection:
            run = connection.execute(
                "SELECT contract_id FROM runs WHERE run_id=?", (source_run_id,)
            ).fetchone()
            if run is None:
                raise KeyError(source_run_id)
            contract = connection.execute(
                "SELECT * FROM contract_revisions WHERE contract_id=? AND revision=?",
                (run["contract_id"], revision),
            ).fetchone()
            lock = connection.execute(
                "SELECT * FROM acceptance_locks WHERE contract_id=? AND contract_revision=?",
                (run["contract_id"], revision),
            ).fetchone()
            planned = (
                connection.execute(
                    "SELECT * FROM planned_runs WHERE run_id=?", (new_run_id,)
                ).fetchone()
                if new_run_id is not None
                else None
            )
        with self.control.transaction() as connection:
            if contract is not None:
                connection.execute(
                    "INSERT OR IGNORE INTO contract_revisions(contract_id,revision,contract_json,"
                    "contract_hash,confirmation_message_id,frozen_at) VALUES (?,?,?,?,?,?)",
                    tuple(contract),
                )
            if lock is not None:
                connection.execute(
                    "INSERT OR IGNORE INTO acceptance_locks(lock_id,contract_id,contract_revision,"
                    "contract_hash,verifier_hashes_json,confirmation_message_id,created_at) "
                    "VALUES (?,?,?,?,?,?,?)",
                    tuple(lock),
                )
            if planned is not None:
                connection.execute(
                    "INSERT OR IGNORE INTO planned_runs(run_id,project_id,contract_id,"
                    "contract_revision,graph_json,graph_hash,parent_run_id,supersedes_run_id,"
                    "restart_from_json,status,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    tuple(planned),
                )


class _CoordinatorExecutor:
    """Map Review/delivery outcomes into existing Graph node results and checkpoints."""

    def __init__(
        self,
        state: StateStore,
        delegate: Any,
        *,
        reviewer: Any | None,
        delivery_provider: Any | None,
    ) -> None:
        self.state = state
        self.delegate = delegate
        self.reviewer = reviewer
        self.delivery_provider = delivery_provider

    def execute(self, run_id: str, node: Any, attempt_id: str) -> ExecutorResult:
        if node.node_id == "review" and self.reviewer is not None:
            aggregate: ReviewAggregate = self.reviewer(run_id, attempt_id)
            if aggregate.review_errors:
                result = self._error("review.infrastructure_error", "Reviewer infrastructure error")
                classification = "review_infrastructure_error"
            elif aggregate.verdict is ReviewVerdict.BLOCKED:
                result = self._error("review.blocked", "Review blocked")
                classification = "review_blocked"
            elif aggregate.verdict is ReviewVerdict.CHANGES_REQUESTED:
                result = ExecutorResult(
                    schema_version="1.0",
                    status=ExecutorStatus.FAILED,
                    summary="Review changes requested",
                    failure_reason="review_changes_requested",
                    remaining_risks=[item.impact for item in aggregate.findings],
                )
                classification = "review_changes_requested"
            else:
                result = ExecutorResult(
                    schema_version="1.0",
                    status=ExecutorStatus.SUCCEEDED,
                    summary="Independent multidimensional Review approved",
                )
                classification = "review_approved"
            self._checkpoint(run_id, "review", attempt_id, classification, result)
            return result
        if node.node_id == "deliver" and self.delivery_provider is not None:
            result = cast(ExecutorResult, self.delivery_provider(run_id, f"{run_id}:deliver"))
            classification = (
                "delivery_succeeded"
                if result.status is ExecutorStatus.SUCCEEDED
                else "delivery_failure"
                if result.status is ExecutorStatus.FAILED
                else "delivery_infrastructure_error"
            )
            self._checkpoint(
                run_id,
                "delivery",
                attempt_id,
                classification,
                result,
                external_effect_key=f"{run_id}:deliver",
            )
            return result
        return cast(ExecutorResult, self.delegate.execute(run_id, node, attempt_id))

    @staticmethod
    def _error(code: str, message: str) -> ExecutorResult:
        return ExecutorResult(
            schema_version="1.0",
            status=ExecutorStatus.ERROR,
            summary=message,
            error=Error(
                schema_version="1.0",
                kind=ErrorKind.INFRASTRUCTURE if "infrastructure" in code else ErrorKind.POLICY,
                code=code,
                message=message,
                retryable=False,
            ),
        )

    def _checkpoint(
        self,
        run_id: str,
        stage: str,
        attempt_id: str,
        classification: str,
        result: ExecutorResult,
        *,
        external_effect_key: str | None = None,
    ) -> None:
        with self.state.transaction() as connection:
            connection.execute(
                "INSERT INTO delivery_stage_checkpoints(run_id,stage,attempt_identity,status,"
                "classification,external_effect_key,result_json,created_at,completed_at) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    run_id,
                    stage,
                    attempt_id,
                    "completed",
                    classification,
                    external_effect_key,
                    result.canonical_json(),
                    timestamp(),
                    timestamp(),
                ),
            )
            self.state.enqueue_event(
                connection,
                f"delivery.{stage}.checkpointed",
                run_id,
                attempt_id=attempt_id,
                payload={
                    "classification": classification,
                    "external_effect_key": external_effect_key,
                },
            )
