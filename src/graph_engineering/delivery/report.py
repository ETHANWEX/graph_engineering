"""Deterministic versioned delivery bundle compiler from persisted facts."""

# ruff: noqa: E501

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from graph_engineering.models.common import ArtifactKind
from graph_engineering.runtime import ArtifactStore, StateStore
from graph_engineering.runtime.store import timestamp
from graph_engineering.verifier.policy import SecretRedactor

from .models import DeliveryBundle

_FILES = (
    "summary.md",
    "requirement-matrix.md",
    "changes.diff",
    "test-results.json",
    "review-report.md",
    "execution-trace.json",
    "cost-report.json",
    "pull-request.json",
    "control-history.json",
    "external-effects.json",
)


class DeliveryReportCompiler:
    def __init__(
        self,
        state: StateStore,
        artifacts: ArtifactStore,
        output_root: Path,
        *,
        secret_values: dict[str, str] | None = None,
    ) -> None:
        self.state = state
        state.migrate()
        self.artifacts = artifacts
        self.output_root = output_root
        self.redactor = SecretRedactor(secret_values or {})

    def compile(self, run_id: str) -> DeliveryBundle:
        facts = self._facts(run_id)
        with self.state.transaction() as connection:
            latest = connection.execute(
                "SELECT MAX(revision) FROM delivery_report_revisions WHERE run_id=?", (run_id,)
            ).fetchone()[0]
            revision = int(latest or 0) + 1
            contents = self._render(facts)
            artifact_refs: dict[str, str] = {}
            target = self.output_root / run_id / str(revision)
            target.mkdir(parents=True, exist_ok=False)
            for name in _FILES:
                raw = self.redactor.redact(contents[name]).encode("utf-8")
                artifact = self.artifacts.put_bytes(
                    raw,
                    media_type="text/markdown"
                    if name.endswith(".md")
                    else "application/json"
                    if name.endswith(".json")
                    else "text/plain",
                    kind=ArtifactKind.REPORT
                    if name.endswith(".md") or name.endswith(".json")
                    else ArtifactKind.PATCH,
                )
                (target / name).write_bytes(raw)
                artifact_refs[name] = artifact.artifact_id
            bundle = DeliveryBundle(
                run_id=run_id,
                revision=revision,
                terminal_status=str(facts["status"]),
                terminal_reason=str(facts["reason"]),
                files=artifact_refs,
            )
            connection.execute(
                "INSERT INTO delivery_report_revisions(run_id, revision, terminal_status, terminal_reason, manifest_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    run_id,
                    revision,
                    bundle.terminal_status,
                    bundle.terminal_reason,
                    bundle.model_dump_json(),
                    timestamp(),
                ),
            )
            self.state.enqueue_event(
                connection,
                "report.delivery.frozen",
                run_id,
                payload={"revision": revision, "artifacts": artifact_refs},
            )
        return bundle

    def latest(self, run_id: str) -> DeliveryBundle:
        """Read the latest frozen revision without creating Artifacts, events, or state."""

        with self.state.read_connection() as connection:
            row = connection.execute(
                "SELECT manifest_json FROM delivery_report_revisions "
                "WHERE run_id=? ORDER BY revision DESC LIMIT 1",
                (run_id,),
            ).fetchone()
        if row is None:
            raise KeyError(run_id)
        return DeliveryBundle.model_validate_json(str(row["manifest_json"]))

    def _facts(self, run_id: str) -> dict[str, Any]:
        with self.state.read_connection() as connection:
            fixture = connection.execute(
                "SELECT * FROM delivery_terminal_fixtures WHERE run_id=?", (run_id,)
            ).fetchone()
            run = connection.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if fixture is None and run is None:
                raise KeyError(run_id)
            source = fixture if fixture is not None else run
            status = str(source["status"])
            if status not in {
                "succeeded",
                "failed",
                "error",
                "interrupted",
                "cancelled",
                "rejected",
            }:
                raise ValueError("delivery report requires a terminal Run")
            reason = str(source["reason"] if fixture is not None else source["terminal_reason"])
            contract_id = str(source["contract_id"])
            contract_revision = int(source["contract_revision"])
            matrix = connection.execute(
                "SELECT matrix_json FROM requirement_matrix_revisions WHERE contract_id=? AND contract_revision=? ORDER BY matrix_revision DESC LIMIT 1",
                (contract_id, contract_revision),
            ).fetchone()
            reviews = [
                json.loads(str(row[0]))
                for row in connection.execute(
                    "SELECT result_json FROM phase5_review_dimensions WHERE run_id=? AND result_json IS NOT NULL ORDER BY attempt_number, dimension",
                    (run_id,),
                )
            ]
            pr = connection.execute(
                "SELECT * FROM pull_request_handles WHERE run_id=? ORDER BY created_at DESC LIMIT 1",
                (run_id,),
            ).fetchone()
            controls = [
                json.loads(str(row[0]))
                for row in connection.execute(
                    "SELECT intent_json FROM control_intents WHERE run_id=? ORDER BY created_at",
                    (run_id,),
                )
            ]
            decisions = [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM human_acceptance_records WHERE run_id=? ORDER BY created_at",
                    (run_id,),
                )
            ]
            events = [
                json.loads(str(row[0]))
                for row in connection.execute(
                    "SELECT event_json FROM event_outbox WHERE json_extract(event_json, '$.run_id')=? ORDER BY created_at",
                    (run_id,),
                )
            ]
            handles = [
                dict(row)
                for row in connection.execute(
                    "SELECT run_id,node_id,idempotency_key,trigger_state,handle,cancel_state,report_artifact_id,residual_effect FROM external_handles WHERE run_id=? ORDER BY node_id",
                    (run_id,),
                )
            ]
            budget = connection.execute(
                "SELECT * FROM budgets WHERE run_id=?", (run_id,)
            ).fetchone()
            artifacts = [
                dict(row)
                for row in connection.execute(
                    "SELECT m.*,r.role,r.node_id FROM artifact_metadata m "
                    "JOIN run_artifacts r ON r.artifact_id=m.artifact_id "
                    "WHERE r.run_id=? ORDER BY m.artifact_id",
                    (run_id,),
                )
            ]
            patch_texts = [
                self.artifacts.read_bytes(str(item["uri"])).decode("utf-8", errors="replace")
                for item in artifacts
                if item["kind"] == "patch"
            ]
            verifier_manifests = [
                json.loads(str(row[0]))
                for row in connection.execute(
                    "SELECT manifest_json FROM verifier_revisions ORDER BY verifier_id, revision"
                )
            ]
            relationship = {
                "parent_run_id": source["parent_run_id"] if fixture is None else None,
                "supersedes_run_id": source["supersedes_run_id"] if fixture is None else None,
                "restart_from": source["restart_from_json"] if fixture is None else None,
            }
        return {
            "run_id": run_id,
            "contract_id": contract_id,
            "contract_revision": contract_revision,
            "status": status,
            "reason": reason,
            "matrix": json.loads(str(matrix[0])) if matrix else None,
            "reviews": reviews,
            "pr": dict(pr) if pr else None,
            "controls": controls + decisions,
            "events": events,
            "effects": handles,
            "budget": dict(budget) if budget else {},
            "artifacts": artifacts,
            "patch_texts": patch_texts,
            "verifier_manifests": verifier_manifests,
            "relationship": relationship,
        }

    @staticmethod
    def _render(facts: dict[str, Any]) -> dict[str, str]:
        success = facts["status"] == "succeeded"
        secret_refs = sorted(
            {
                str(reference)
                for manifest in facts["verifier_manifests"]
                for reference in manifest.get("capabilities", {}).get("secrets", [])
            }
        )
        summary = f"# Run {facts['run_id']}\n\nTerminal status: **{facts['status']}**\n\nTerminal reason: {facts['reason']}\n\nContract: {facts['contract_id']} r{facts['contract_revision']}\n\nDelivery succeeded: {'yes' if success else 'no'}\n\nLineage: `{json.dumps(facts['relationship'], sort_keys=True)}`\n\nSecret references (names only): {', '.join(secret_refs) if secret_refs else 'none'}\n\nReproduce using the frozen Contract, exact Git baseline/target, and referenced evidence artifacts.\n"
        matrix = facts["matrix"]
        matrix_md = (
            "# Requirement Matrix\n\nNo frozen matrix exists; all criteria remain unverified.\n"
            if matrix is None
            else "# Requirement Matrix\n\n```json\n"
            + json.dumps(matrix, indent=2, sort_keys=True)
            + "\n```\n"
        )
        review_md = (
            "# Review Report\n\n```json\n"
            + json.dumps(facts["reviews"], indent=2, sort_keys=True)
            + "\n```\n"
        )
        return {
            "summary.md": summary,
            "requirement-matrix.md": matrix_md,
            "changes.diff": "\n".join(facts["patch_texts"]),
            "test-results.json": json.dumps(
                {
                    "status": "unverified" if matrix is None else "recorded",
                    "evidence": [
                        item["artifact_id"]
                        for item in facts["artifacts"]
                        if item["role"] == "verifier"
                    ],
                },
                indent=2,
            ),
            "review-report.md": review_md,
            "execution-trace.json": json.dumps(facts["events"], indent=2, sort_keys=True),
            "cost-report.json": json.dumps(facts["budget"], indent=2, sort_keys=True),
            "pull-request.json": json.dumps(facts["pr"], indent=2, sort_keys=True),
            "control-history.json": json.dumps(
                facts["controls"], indent=2, sort_keys=True, default=str
            ),
            "external-effects.json": json.dumps(
                {
                    "effects": facts["effects"],
                    "permissions": [
                        manifest.get("capabilities", {}) for manifest in facts["verifier_manifests"]
                    ],
                },
                indent=2,
                sort_keys=True,
            ),
        }
