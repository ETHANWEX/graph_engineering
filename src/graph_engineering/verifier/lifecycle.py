"""Append-only Verifier lifecycle and hash enforcement."""

from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path

from graph_engineering.models import TaskContract
from graph_engineering.runtime.store import StateStore, timestamp

from .types import VerifierLifecycle, VerifierManifest, VerifierRevisionHashes


class VerifierLifecycleError(RuntimeError):
    pass


def _hash_path(path: Path | None) -> str | None:
    if path is None:
        return None
    if path.is_file():
        return hashlib.sha256(path.read_bytes()).hexdigest()
    if not path.is_dir():
        raise VerifierLifecycleError(f"Verifier input does not exist: {path}")
    digest = hashlib.sha256()
    for child in sorted(item for item in path.rglob("*") if item.is_file()):
        digest.update(child.relative_to(path).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(child.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


class VerifierRepository:
    def __init__(self, state: StateStore) -> None:
        self.state = state
        self.state.migrate()

    def stage(
        self,
        manifest: VerifierManifest,
        *,
        source: Path,
        tests: Path,
        fixtures: Path | None = None,
    ) -> VerifierRevisionHashes:
        hashes = self.hashes(manifest, source=source, tests=tests, fixtures=fixtures)
        with self.state.transaction() as connection:
            existing = connection.execute(
                "SELECT manifest_hash, lifecycle FROM verifier_revisions "
                "WHERE verifier_id = ? AND revision = ?",
                (manifest.verifier_id, manifest.revision),
            ).fetchone()
            if existing is not None:
                raise VerifierLifecycleError("Verifier revision already exists and is immutable")
            latest = connection.execute(
                "SELECT MAX(revision) FROM verifier_revisions WHERE verifier_id = ?",
                (manifest.verifier_id,),
            ).fetchone()[0]
            if latest is not None and manifest.revision != int(latest) + 1:
                raise VerifierLifecycleError("Verifier revisions must be append-only")
            connection.execute(
                "INSERT INTO verifier_revisions(verifier_id, revision, verifier_type, "
                "manifest_json, manifest_hash, source_hash, tests_hash, fixtures_hash, "
                "source_path, tests_path, fixtures_path, lifecycle, permission_summary, "
                "created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'draft', ?, ?)",
                (
                    manifest.verifier_id,
                    manifest.revision,
                    manifest.verifier_type,
                    manifest.model_dump_json(),
                    hashes.manifest_sha256,
                    hashes.source_sha256,
                    hashes.tests_sha256,
                    hashes.fixtures_sha256,
                    str(source.resolve()),
                    str(tests.resolve()),
                    str(fixtures.resolve()) if fixtures else None,
                    self.permission_summary(manifest),
                    timestamp(),
                ),
            )
            self.state.enqueue_event(
                connection,
                "verifier.revision.staged",
                f"verifier:{manifest.verifier_id}:{manifest.revision}",
                payload={"verifier_id": manifest.verifier_id, "revision": manifest.revision},
            )
        return hashes

    def record(
        self,
        verifier_id: str,
        revision: int,
        lifecycle: VerifierLifecycle,
        result: dict[str, object],
        *,
        artifact_id: str | None = None,
    ) -> None:
        allowed = {
            VerifierLifecycle.DRAFT: VerifierLifecycle.VALIDATED,
            VerifierLifecycle.VALIDATED: VerifierLifecycle.TESTED,
            VerifierLifecycle.TESTED: VerifierLifecycle.DRY_RUN,
        }
        with self.state.transaction() as connection:
            row = connection.execute(
                "SELECT lifecycle FROM verifier_revisions WHERE verifier_id = ? AND revision = ?",
                (verifier_id, revision),
            ).fetchone()
            if row is None:
                raise KeyError((verifier_id, revision))
            current = VerifierLifecycle(str(row["lifecycle"]))
            if allowed.get(current) is not lifecycle:
                raise VerifierLifecycleError(
                    f"invalid Verifier lifecycle: {current} -> {lifecycle}"
                )
            if result.get("passed") is not True:
                raise VerifierLifecycleError(f"{lifecycle} evidence did not pass")
            connection.execute(
                "UPDATE verifier_revisions SET lifecycle = ? "
                "WHERE verifier_id = ? AND revision = ?",
                (lifecycle.value, verifier_id, revision),
            )
            connection.execute(
                "INSERT INTO verifier_lifecycle_evidence(evidence_id, verifier_id, revision, "
                "lifecycle, result_json, artifact_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    f"verifier-evidence:{uuid.uuid4()}",
                    verifier_id,
                    revision,
                    lifecycle.value,
                    json.dumps(result, separators=(",", ":"), sort_keys=True),
                    artifact_id,
                    timestamp(),
                ),
            )

    def freeze(
        self,
        verifier_id: str,
        revision: int,
        *,
        contract_id: str,
        contract_revision: int,
        confirmation_message_id: str,
    ) -> VerifierRevisionHashes:
        if not confirmation_message_id:
            raise VerifierLifecycleError("Human confirmation is required before freeze")
        with self.state.transaction() as connection:
            row = connection.execute(
                "SELECT * FROM verifier_revisions WHERE verifier_id = ? AND revision = ?",
                (verifier_id, revision),
            ).fetchone()
            if row is None:
                raise KeyError((verifier_id, revision))
            if str(row["lifecycle"]) != VerifierLifecycle.DRY_RUN.value:
                raise VerifierLifecycleError("validate, test, and dry-run must pass before freeze")
            contract_row = connection.execute(
                "SELECT contract_json FROM contract_revisions "
                "WHERE contract_id = ? AND revision = ?",
                (contract_id, contract_revision),
            ).fetchone()
            if contract_row is None:
                raise VerifierLifecycleError(
                    "Verifier freeze requires an existing frozen Contract revision"
                )
            contract = TaskContract.model_validate_json(str(contract_row["contract_json"]))
            requirement = next(
                (item for item in contract.verifiers if item.verifier_id == verifier_id), None
            )
            if requirement is None or requirement.verifier_type != str(row["verifier_type"]):
                raise VerifierLifecycleError(
                    "frozen Contract does not declare this Verifier ID and type"
                )
            previous = connection.execute(
                "SELECT MAX(verifier_revision), MAX(contract_revision) "
                "FROM contract_verifier_bindings "
                "WHERE verifier_id = ?",
                (verifier_id,),
            ).fetchone()
            if (
                previous[0] is not None
                and revision > int(previous[0])
                and contract_revision <= int(previous[1])
            ):
                raise VerifierLifecycleError(
                    "a new Verifier revision requires a new Contract revision"
                )
            hashes = self._row_hashes(row)
            connection.execute(
                "UPDATE verifier_revisions SET lifecycle = 'frozen', confirmation_message_id = ?, "
                "frozen_at = ? WHERE verifier_id = ? AND revision = ?",
                (confirmation_message_id, timestamp(), verifier_id, revision),
            )
            connection.execute(
                "INSERT INTO contract_verifier_bindings("
                "contract_id, contract_revision, verifier_id, "
                "verifier_revision, hashes_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    contract_id,
                    contract_revision,
                    verifier_id,
                    revision,
                    hashes.model_dump_json(),
                    timestamp(),
                ),
            )
            self.state.enqueue_event(
                connection,
                "verifier.revision.frozen",
                f"contract:{contract_id}:{contract_revision}",
                payload={"verifier_id": verifier_id, "revision": revision},
            )
            return hashes

    def verify_frozen(self, verifier_id: str, revision: int) -> VerifierRevisionHashes:
        with self.state.read_connection() as connection:
            row = connection.execute(
                "SELECT * FROM verifier_revisions WHERE verifier_id = ? AND revision = ?",
                (verifier_id, revision),
            ).fetchone()
        if row is None or str(row["lifecycle"]) != VerifierLifecycle.FROZEN.value:
            raise VerifierLifecycleError("Verifier revision is not frozen")
        manifest = VerifierManifest.model_validate_json(str(row["manifest_json"]))
        actual = self.hashes(
            manifest,
            source=Path(str(row["source_path"])),
            tests=Path(str(row["tests_path"])),
            fixtures=Path(str(row["fixtures_path"])) if row["fixtures_path"] else None,
        )
        expected = self._row_hashes(row)
        if actual != expected:
            raise VerifierLifecycleError("frozen Verifier hash drift; refusing execution")
        return expected

    @staticmethod
    def hashes(
        manifest: VerifierManifest,
        *,
        source: Path,
        tests: Path,
        fixtures: Path | None,
    ) -> VerifierRevisionHashes:
        return VerifierRevisionHashes(
            manifest_sha256=hashlib.sha256(
                json.dumps(
                    manifest.model_dump(mode="json"), separators=(",", ":"), sort_keys=True
                ).encode("utf-8")
            ).hexdigest(),
            source_sha256=_hash_path(source) or hashlib.sha256(b"").hexdigest(),
            tests_sha256=_hash_path(tests) or hashlib.sha256(b"").hexdigest(),
            fixtures_sha256=_hash_path(fixtures),
        )

    @staticmethod
    def permission_summary(manifest: VerifierManifest) -> str:
        return json.dumps(
            {
                "entrypoint": list(manifest.entrypoint),
                "network_hosts": list(manifest.capabilities.network.allow),
                "filesystem_read": list(manifest.capabilities.filesystem.read),
                "filesystem_write": list(manifest.capabilities.filesystem.write),
                "secret_references": list(manifest.capabilities.secrets),
                "external_side_effects": manifest.external_side_effects,
            },
            separators=(",", ":"),
            sort_keys=True,
        )

    @staticmethod
    def _row_hashes(row: object) -> VerifierRevisionHashes:
        import sqlite3

        if not isinstance(row, sqlite3.Row):
            raise TypeError("Verifier row must be SQLite Row")
        return VerifierRevisionHashes(
            manifest_sha256=str(row["manifest_hash"]),
            source_sha256=str(row["source_hash"]),
            tests_sha256=str(row["tests_hash"]),
            fixtures_sha256=str(row["fixtures_hash"]) if row["fixtures_hash"] else None,
        )
