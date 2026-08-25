"""Read-only UI snapshots compiled at the Human Gateway boundary."""

# ruff: noqa: E501

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from graph_engineering.models import HumanMessage, StateChangeControlIntent
from graph_engineering.runtime import StateStore


class UISnapshotReader:
    def __init__(
        self,
        project_root: Path,
        project_id: str,
        control_state: StateStore,
        *,
        instance_id: str | None = None,
    ) -> None:
        self.project_root = project_root.resolve()
        self.project_id = project_id
        self.control_state = control_state
        self.instance_id = instance_id or f"ui-source:{uuid.uuid4()}"

    def project(self, *, run_id: str | None = None) -> dict[str, Any]:
        runs = [self._run(item) for item in self._run_databases(run_id)]
        conversation, pending = self._conversation(runs)
        facts: dict[str, Any] = {
            "contract_version": "1.0",
            "project": {
                "project_id": self.project_id,
                "status": _project_status(runs),
                "authoritative_source": "runtime_sqlite_via_human_gateway",
            },
            "runs": runs,
            "conversation": conversation,
            "pending_confirmations": pending,
        }
        canonical = json.dumps(facts, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        facts["source"] = {
            "instance_id": self.instance_id,
            "snapshot_id": hashlib.sha256(canonical.encode()).hexdigest(),
            "generated_at": datetime.now(UTC).isoformat(),
            "stale_after_seconds": 10,
            "ordering": "persisted identity then stable key",
        }
        return facts

    def _run_databases(self, selected: str | None) -> list[Path]:
        root = (self.project_root / ".ge" / "runs").resolve()
        if selected is not None:
            candidate = (root / selected / "state.db").resolve()
            if candidate.parent.parent != root or not candidate.is_file():
                raise KeyError(selected)
            return [candidate]
        if not root.is_dir():
            return []
        result: list[Path] = []
        for child in sorted(root.iterdir(), key=lambda item: item.name):
            if child.is_dir() and child.resolve().parent == root:
                database = child / "state.db"
                if database.is_file():
                    result.append(database)
        return result

    def _run(self, database: Path) -> dict[str, Any]:
        state = StateStore(database)
        with state.read_connection() as connection:
            run = connection.execute("SELECT * FROM runs ORDER BY created_at LIMIT 1").fetchone()
            if run is None:
                raise KeyError(database.parent.name)
            if str(run["project_id"]) != self.project_id:
                raise PermissionError("Run belongs to another project")
            run_id = str(run["run_id"])
            tables = {
                str(row[0])
                for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            budget = _one(
                connection, "SELECT * FROM budgets WHERE run_id=?", (run_id,), tables, "budgets"
            )
            nodes = _many(
                connection,
                "SELECT * FROM nodes WHERE run_id=? ORDER BY node_id",
                (run_id,),
                tables,
                "nodes",
            )
            attempts = _many(
                connection,
                "SELECT * FROM attempts WHERE run_id=? ORDER BY attempt_id",
                (run_id,),
                tables,
                "attempts",
            )
            branches = _many(
                connection,
                "SELECT * FROM parallel_branches WHERE run_id=? ORDER BY container_node_id,branch_order,branch_id",
                (run_id,),
                tables,
                "parallel_branches",
            )
            sessions = _many(
                connection,
                "SELECT session_id,node_id,attempt_id,role,provider,status,continuation_count,failure_count,created_at,updated_at FROM executor_sessions WHERE run_id=? ORDER BY created_at,session_id",
                (run_id,),
                tables,
                "executor_sessions",
            )
            verifiers = _many(
                connection,
                "SELECT verifier_execution_id,node_id,attempt_id,status,started_at,finished_at FROM verifier_executions WHERE run_id=? ORDER BY started_at,verifier_execution_id",
                (run_id,),
                tables,
                "verifier_executions",
            )
            review_attempts = _many(
                connection,
                "SELECT * FROM phase5_review_attempts WHERE run_id=? ORDER BY attempt_number",
                (run_id,),
                tables,
                "phase5_review_attempts",
            )
            review_dimensions = _many(
                connection,
                "SELECT attempt_number,dimension,session_id,result_json,created_at FROM phase5_review_dimensions WHERE run_id=? ORDER BY attempt_number,dimension",
                (run_id,),
                tables,
                "phase5_review_dimensions",
            )
            stages = _many(
                connection,
                "SELECT stage,attempt_identity,status,classification,artifact_refs_json,external_effect_key,external_handle,result_json,created_at,completed_at FROM delivery_stage_checkpoints WHERE run_id=? ORDER BY created_at,stage",
                (run_id,),
                tables,
                "delivery_stage_checkpoints",
            )
            matrix = _one(
                connection,
                "SELECT matrix_revision,matrix_json,created_at FROM requirement_matrix_revisions WHERE contract_id=? AND contract_revision=? ORDER BY matrix_revision DESC LIMIT 1",
                (run["contract_id"], run["contract_revision"]),
                tables,
                "requirement_matrix_revisions",
            )
            checks = _many(
                connection,
                "SELECT query_id,repository,commit_sha,status_json,created_at FROM github_check_queries WHERE run_id=? ORDER BY created_at,query_id",
                (run_id,),
                tables,
                "github_check_queries",
            )
            pull_request = _one(
                connection,
                "SELECT repository,base_branch,head_branch,pr_number,pr_url,node_id,created_at FROM pull_request_handles WHERE run_id=? ORDER BY created_at DESC LIMIT 1",
                (run_id,),
                tables,
                "pull_request_handles",
            )
            report = _one(
                connection,
                "SELECT revision,terminal_status,terminal_reason,manifest_json,created_at FROM delivery_report_revisions WHERE run_id=? ORDER BY revision DESC LIMIT 1",
                (run_id,),
                tables,
                "delivery_report_revisions",
            )
            artifacts = _many(
                connection,
                "SELECT artifact_id,sha256_digest,media_type,size_bytes,kind,created_at FROM artifact_metadata WHERE run_id=? ORDER BY created_at,artifact_id",
                (run_id,),
                tables,
                "artifact_metadata",
            )
            containers = _many(
                connection,
                "SELECT execution_id,node_id,attempt_id,state,handle,image_digest,cleanup_state,residual_effect,created_at,updated_at FROM container_executions WHERE run_id=? ORDER BY created_at,execution_id",
                (run_id,),
                tables,
                "container_executions",
            )
            decisions = _many(
                connection,
                "SELECT record_id,source_message_id,intent_id,actor_id,action,reason,contract_revision,report_revision,new_contract_revision,new_run_id,created_at FROM human_acceptance_records WHERE run_id=? ORDER BY created_at,record_id",
                (run_id,),
                tables,
                "human_acceptance_records",
            )
        unverified = _json(str(run["unverified_json"]), [])
        external = _json(str(run["external_effects_json"]), [])
        return {
            "run_id": run_id,
            "status": str(run["status"]),
            "barrier": run["barrier"],
            "current_node_id": run["current_node_id"],
            "terminal_reason": run["terminal_reason"],
            "created_at": run["created_at"],
            "updated_at": run["updated_at"],
            "lineage": {
                "parent_run_id": run["parent_run_id"],
                "supersedes_run_id": run["supersedes_run_id"],
                "restart_from": _json(run["restart_from_json"], None),
            },
            "contract": {
                "contract_id": str(run["contract_id"]),
                "revision": int(run["contract_revision"]),
                "hash": str(run["contract_hash"]),
                "frozen": True,
            },
            "graph": {"graph_id": run["graph_id"], "hash": run["graph_hash"]},
            "budget": budget or {},
            "nodes": [_decoded(item) for item in nodes],
            "attempts": [_decoded(item) for item in attempts],
            "parallel_branches": [_decoded(item) for item in branches],
            "sessions": sessions,
            "risks": unverified,
            "unverified": unverified,
            "external_effects": external,
            "verifiers": [_decoded(item) for item in verifiers],
            "repair": [item for item in stages if item.get("stage") in {"repair", "review_fix"}],
            "review": {
                "attempts": review_attempts,
                "dimensions": [_decoded(item) for item in review_dimensions],
            },
            "requirement_matrix": _decoded(matrix)
            if matrix
            else {"status": "unverified", "rows": []},
            "github": {
                "checks": [_decoded(item) for item in checks],
                "pull_request": pull_request,
                "representation": "read_only",
            },
            "report": _decoded(report)
            if report
            else {"status": "unverified", "reason": "not_frozen"},
            "artifacts": artifacts,
            "containers": containers,
            "human_decisions": decisions,
        }

    def _conversation(
        self, runs: list[dict[str, Any]]
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        run_contracts = {item["run_id"]: item["contract"] for item in runs}
        with self.control_state.read_connection() as connection:
            conversations = [
                dict(row)
                for row in connection.execute(
                    "SELECT conversation_id,project_id,actor_id,active_run_id,status,created_at,updated_at FROM conversations WHERE project_id=? ORDER BY created_at,conversation_id",
                    (self.project_id,),
                )
            ]
            messages = [
                dict(row)
                for row in connection.execute(
                    "SELECT conversation_id,message_json,created_at FROM human_messages ORDER BY created_at,rowid"
                )
            ]
            pending = [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM pending_confirmations ORDER BY created_at,confirmation_id"
                )
            ]
        rendered_messages: list[dict[str, Any]] = []
        for row in messages:
            message = HumanMessage.model_validate_json(str(row["message_json"]))
            if message.project_id == self.project_id:
                rendered_messages.append(message.model_dump(mode="json", exclude_none=True))
        cards: list[dict[str, Any]] = []
        for row in pending:
            try:
                intent = StateChangeControlIntent.model_validate_json(str(row["intent_json"]))
            except ValueError:
                continue
            if (row.get("project_id") or intent.project_id) != self.project_id:
                continue
            contract = run_contracts.get(intent.run_id, {})
            cards.append(
                {
                    "pending_action_id": str(row["confirmation_id"]),
                    "conversation_id": str(row["conversation_id"]),
                    "project_id": self.project_id,
                    "actor_id": str(row.get("actor_id") or intent.actor_id),
                    "source_message_id": intent.source_message_id,
                    "intent_id": intent.intent_id,
                    "action": intent.action.value,
                    "run_id": intent.run_id,
                    "contract_id": contract.get("contract_id"),
                    "contract_revision": contract.get("revision"),
                    "contract_hash": contract.get("hash"),
                    "created_at": str(row["created_at"]),
                    "expires_at": row.get("expires_at"),
                    "status": str(row["status"]),
                }
            )
        return {
            "project_id": self.project_id,
            "conversations": conversations,
            "messages": rendered_messages,
        }, cards


def _one(
    connection: Any, sql: str, parameters: tuple[object, ...], tables: set[str], table: str
) -> dict[str, Any] | None:
    if table not in tables:
        return None
    row = connection.execute(sql, parameters).fetchone()
    return dict(row) if row is not None else None


def _many(
    connection: Any, sql: str, parameters: tuple[object, ...], tables: set[str], table: str
) -> list[dict[str, Any]]:
    if table not in tables:
        return []
    return [dict(row) for row in connection.execute(sql, parameters)]


def _json(value: object, default: Any) -> Any:
    if value is None:
        return default
    try:
        return json.loads(str(value))
    except json.JSONDecodeError:
        return default


def _decoded(value: dict[str, Any]) -> dict[str, Any]:
    result = dict(value)
    for key in tuple(result):
        if key.endswith("_json"):
            result[key.removesuffix("_json")] = _json(result.pop(key), None)
    return result


def _project_status(runs: list[dict[str, Any]]) -> str:
    if not runs:
        return "unverified"
    statuses = {str(item["status"]) for item in runs}
    if statuses <= {"succeeded", "accepted"}:
        return "healthy"
    if statuses & {"failed", "error", "interrupted", "cancelled", "rejected"}:
        return "partial"
    return "active"
