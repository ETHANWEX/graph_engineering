"""Transactional append-only frozen Contract repository."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from graph_engineering.models import ContractRef, HumanMessage, TaskContract
from graph_engineering.models.contract import ContractStatus
from graph_engineering.runtime.store import StateStore, timestamp

from .models import AcceptanceLock, ContractDelta, FrozenContract


class ContractRevisionError(RuntimeError):
    pass


def _confirmed(message: HumanMessage) -> bool:
    value = message.content.casefold()
    return any(token in value for token in ("confirm", "确认", "同意", "批准"))


class ContractRepository:
    def __init__(self, state: StateStore) -> None:
        self.state = state
        self.state.migrate()

    @staticmethod
    def example_draft(contract_id: str, description: str, test_command: str) -> TaskContract:
        from graph_engineering.discovery.models import (
            DiscoverySession,
            DiscoveryState,
            ProjectScan,
        )
        from graph_engineering.discovery.service import DiscoveryService

        session = DiscoverySession(
            session_id="example",
            conversation_id=contract_id,
            source_message_id="example",
            initial_request=description,
            project_root=".",
            state=DiscoveryState.AWAITING_CONFIRMATION,
            scan=ProjectScan(project_root=".", entries=(), included_bytes=0, truncated=False),
            unknowns=(),
            answers={},
        )
        return DiscoveryService._draft(
            session,
            {
                "acceptance": description,
                "verification": test_command,
                "dependencies": "No interface changes",
                "conventions": "Follow repository conventions",
                "permissions": "No network or secrets",
                "delivery": "report only",
                "budget": "default",
            },
        ).model_copy(update={"contract_id": contract_id})

    def stage(self, conversation_id: str, contract: TaskContract) -> str:
        if contract.status is not ContractStatus.DRAFT:
            raise ContractRevisionError("only a draft Contract can be staged")
        digest = contract.sha256()
        draft_id = f"draft:{contract.contract_id}:{contract.revision}:{digest[:16]}"
        with self.state.transaction() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO contract_drafts("
                "draft_id, conversation_id, contract_id, revision, contract_json, "
                "contract_hash, status, created_at) VALUES (?, ?, ?, ?, ?, ?, 'staged', ?)",
                (
                    draft_id,
                    conversation_id,
                    contract.contract_id,
                    contract.revision,
                    contract.canonical_json(),
                    digest,
                    timestamp(),
                ),
            )
            self.state.enqueue_event(
                connection,
                "contract.draft.staged",
                f"conversation:{conversation_id}",
                payload={"draft_id": draft_id, "contract_hash": digest},
            )
        return draft_id

    def freeze(self, draft_id: str, confirmation: HumanMessage) -> FrozenContract:
        if not _confirmed(confirmation):
            raise ContractRevisionError("explicit Human confirmation is required")
        with self.state.transaction() as connection:
            draft = connection.execute(
                "SELECT * FROM contract_drafts WHERE draft_id = ?", (draft_id,)
            ).fetchone()
            if draft is None:
                raise KeyError(draft_id)
            contract = TaskContract.model_validate_json(str(draft["contract_json"]))
            frozen = contract.model_copy(update={"status": ContractStatus.FROZEN})
            existing = connection.execute(
                "SELECT contract_hash FROM contract_revisions "
                "WHERE contract_id = ? AND revision = ?",
                (frozen.contract_id, frozen.revision),
            ).fetchone()
            if existing is not None:
                if str(existing["contract_hash"]) != frozen.sha256():
                    raise ContractRevisionError(
                        "a different frozen Contract already owns this revision"
                    )
                return self._frozen(connection, frozen.contract_id, frozen.revision)
            self._insert_frozen(connection, frozen, confirmation.message_id)
            connection.execute(
                "UPDATE contract_drafts SET status = 'frozen' WHERE draft_id = ?", (draft_id,)
            )
            self.state.enqueue_event(
                connection,
                "contract.frozen",
                confirmation.run_id or f"contract:{frozen.contract_id}",
                payload={"contract_id": frozen.contract_id, "revision": frozen.revision},
            )
            return self._frozen(connection, frozen.contract_id, frozen.revision)

    def apply_delta(self, delta: ContractDelta, confirmation: HumanMessage) -> FrozenContract:
        if not _confirmed(confirmation):
            raise ContractRevisionError("explicit Human confirmation is required")
        with self.state.transaction() as connection:
            row = connection.execute(
                "SELECT contract_json FROM contract_revisions "
                "WHERE contract_id = ? AND revision = ?",
                (delta.contract_id, delta.source_revision),
            ).fetchone()
            if row is None:
                raise ContractRevisionError("source Contract revision does not exist")
            latest = connection.execute(
                "SELECT MAX(revision) FROM contract_revisions WHERE contract_id = ?",
                (delta.contract_id,),
            ).fetchone()
            if latest is None or int(latest[0]) != delta.source_revision:
                raise ContractRevisionError("delta must apply to the latest frozen revision")
            source = TaskContract.model_validate_json(str(row["contract_json"]))
            revision = source.revision + 1
            revised = source.model_copy(
                update={
                    "revision": revision,
                    "supersedes": ContractRef(
                        schema_version="1.0",
                        contract_id=source.contract_id,
                        revision=source.revision,
                    ),
                    "task": source.task.model_copy(
                        update={"description": delta.replacement_description}
                    ),
                    "status": ContractStatus.FROZEN,
                }
            )
            revised = TaskContract.model_validate(revised.model_dump(mode="python"))
            self._insert_frozen(connection, revised, confirmation.message_id)
            connection.execute(
                "INSERT INTO contract_deltas(delta_id, contract_id, source_revision, "
                "new_revision, delta_json, confirmation_message_id, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    delta.delta_id,
                    delta.contract_id,
                    delta.source_revision,
                    revision,
                    delta.model_dump_json(),
                    confirmation.message_id,
                    timestamp(),
                ),
            )
            self.state.enqueue_event(
                connection,
                "contract.revision.created",
                confirmation.run_id or f"contract:{revised.contract_id}",
                payload={"delta_id": delta.delta_id, "revision": revision},
            )
            return self._frozen(connection, revised.contract_id, revision)

    def revisions(self, contract_id: str) -> list[TaskContract]:
        with self.state.read_connection() as connection:
            rows = list(
                connection.execute(
                    "SELECT contract_json FROM contract_revisions WHERE contract_id = ? "
                    "ORDER BY revision",
                    (contract_id,),
                )
            )
        return [TaskContract.model_validate_json(str(row["contract_json"])) for row in rows]

    def locks(self, contract_id: str) -> list[AcceptanceLock]:
        with self.state.read_connection() as connection:
            rows = list(
                connection.execute(
                    "SELECT * FROM acceptance_locks WHERE contract_id = ? "
                    "ORDER BY contract_revision",
                    (contract_id,),
                )
            )
        return [self._lock(row) for row in rows]

    def replace_frozen(self, contract: TaskContract) -> None:
        if self.revisions(contract.contract_id):
            raise ContractRevisionError("frozen Contract revisions cannot be replaced")
        raise ContractRevisionError("replacement is not a supported Contract operation")

    def _insert_frozen(
        self, connection: object, contract: TaskContract, confirmation_message_id: str
    ) -> None:
        import sqlite3

        if not isinstance(connection, sqlite3.Connection):
            raise TypeError("connection must be SQLite")
        digest = contract.sha256()
        verifier_hashes = {
            verifier.verifier_id: hashlib.sha256(
                verifier.canonical_json().encode("utf-8")
            ).hexdigest()
            for verifier in sorted(contract.verifiers, key=lambda item: item.verifier_id)
        }
        lock_id = f"acceptance:{contract.contract_id}:{contract.revision}:{digest[:16]}"
        now = timestamp()
        connection.execute(
            "INSERT INTO contract_revisions(contract_id, revision, contract_json, contract_hash, "
            "confirmation_message_id, frozen_at) VALUES (?, ?, ?, ?, ?, ?)",
            (
                contract.contract_id,
                contract.revision,
                contract.canonical_json(),
                digest,
                confirmation_message_id,
                now,
            ),
        )
        connection.execute(
            "INSERT INTO acceptance_locks(lock_id, contract_id, contract_revision, contract_hash, "
            "verifier_hashes_json, confirmation_message_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                lock_id,
                contract.contract_id,
                contract.revision,
                digest,
                json.dumps(verifier_hashes, separators=(",", ":"), sort_keys=True),
                confirmation_message_id,
                now,
            ),
        )

    def _frozen(self, connection: object, contract_id: str, revision: int) -> FrozenContract:
        import sqlite3

        if not isinstance(connection, sqlite3.Connection):
            raise TypeError("connection must be SQLite")
        contract_row = connection.execute(
            "SELECT contract_json FROM contract_revisions WHERE contract_id = ? AND revision = ?",
            (contract_id, revision),
        ).fetchone()
        lock_row = connection.execute(
            "SELECT * FROM acceptance_locks WHERE contract_id = ? AND contract_revision = ?",
            (contract_id, revision),
        ).fetchone()
        if contract_row is None or lock_row is None:
            raise ContractRevisionError("frozen Contract is incomplete")
        return FrozenContract(
            contract=TaskContract.model_validate_json(str(contract_row["contract_json"])),
            acceptance_lock=self._lock(lock_row),
        )

    @staticmethod
    def _lock(row: object) -> AcceptanceLock:
        import sqlite3

        if not isinstance(row, sqlite3.Row):
            raise TypeError("lock row must be SQLite Row")
        return AcceptanceLock(
            lock_id=str(row["lock_id"]),
            contract_id=str(row["contract_id"]),
            contract_revision=int(row["contract_revision"]),
            contract_hash=str(row["contract_hash"]),
            verifier_hashes=json.loads(str(row["verifier_hashes_json"])),
            confirmation_message_id=str(row["confirmation_message_id"]),
            created_at=datetime.fromisoformat(
                str(row["created_at"]).replace("Z", "+00:00")
            ).astimezone(UTC),
        )
