"""Append-only requirement matrix with explicit evidence trust."""

# ruff: noqa: E501

from __future__ import annotations

import hashlib
from collections.abc import Mapping

from graph_engineering.runtime.store import StateStore, timestamp

from .models import (
    EvidenceRef,
    MatrixStatus,
    RequirementMatrixRevision,
    RequirementMatrixRow,
)

_CATEGORIES = ("implementation", "test", "verifier", "ci", "review", "human")


class RequirementMatrixRepository:
    def __init__(self, state: StateStore) -> None:
        self.state = state
        state.migrate()

    def create(
        self,
        *,
        contract_id: str,
        contract_revision: int,
        criterion_ids: tuple[str, ...],
        evidence: Mapping[str, Mapping[str, tuple[EvidenceRef, ...]]],
    ) -> RequirementMatrixRevision:
        if not criterion_ids or len(set(criterion_ids)) != len(criterion_ids):
            raise ValueError("criterion IDs must be non-empty and unique")
        if set(evidence) - set(criterion_ids):
            raise ValueError("evidence references an unknown acceptance criterion")
        rows: list[RequirementMatrixRow] = []
        for criterion_id in criterion_ids:
            categories = evidence.get(criterion_id, {})
            if set(categories) - set(_CATEGORIES):
                raise ValueError("unknown requirement matrix evidence category")
            flattened = tuple(item for name in _CATEGORIES for item in categories.get(name, ()))
            failed = any(item.outcome == "failed" and item.trusted for item in flattened)
            trusted = tuple(item for item in flattened if item.trusted)
            if failed:
                status = MatrixStatus.FAILED
                reason = None
            elif trusted:
                status = MatrixStatus.VERIFIED
                reason = None
            else:
                status = MatrixStatus.UNVERIFIED
                reason = "no immutable or content-addressed evidence"
            rows.append(
                RequirementMatrixRow(
                    criterion_id=criterion_id,
                    **{name: categories.get(name, ()) for name in _CATEGORIES},
                    status=status,
                    unverified_reason=reason,
                    artifact_refs=tuple(sorted({item.ref for item in trusted})),
                )
            )
        with self.state.transaction() as connection:
            latest = connection.execute(
                "SELECT MAX(matrix_revision) FROM requirement_matrix_revisions WHERE contract_id=? AND contract_revision=?",
                (contract_id, contract_revision),
            ).fetchone()[0]
            revision = int(latest or 0) + 1
            matrix = RequirementMatrixRevision(
                contract_id=contract_id,
                contract_revision=contract_revision,
                matrix_revision=revision,
                rows=tuple(rows),
            )
            payload = matrix.model_dump_json()
            connection.execute(
                "INSERT INTO requirement_matrix_revisions(contract_id, contract_revision, matrix_revision, matrix_json, matrix_hash, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    contract_id,
                    contract_revision,
                    revision,
                    payload,
                    hashlib.sha256(payload.encode()).hexdigest(),
                    timestamp(),
                ),
            )
            self.state.enqueue_event(
                connection,
                "requirement_matrix.frozen",
                f"contract:{contract_id}",
                payload={"contract_revision": contract_revision, "matrix_revision": revision},
            )
        return matrix

    def get(
        self, contract_id: str, contract_revision: int, matrix_revision: int
    ) -> RequirementMatrixRevision:
        with self.state.read_connection() as connection:
            row = connection.execute(
                "SELECT matrix_json FROM requirement_matrix_revisions WHERE contract_id=? AND contract_revision=? AND matrix_revision=?",
                (contract_id, contract_revision, matrix_revision),
            ).fetchone()
        if row is None:
            raise KeyError((contract_id, contract_revision, matrix_revision))
        return RequirementMatrixRevision.model_validate_json(str(row["matrix_json"]))

    def fingerprint(self) -> tuple[tuple[object, ...], ...]:
        with self.state.read_connection() as connection:
            return tuple(
                tuple(row)
                for row in connection.execute(
                    "SELECT contract_id, contract_revision, matrix_revision, matrix_hash FROM requirement_matrix_revisions ORDER BY contract_id, contract_revision, matrix_revision"
                )
            )
