"""Bridge Phase 4 SDK Verifiers into the serial Graph Runtime boundary."""

from __future__ import annotations

from pathlib import Path

from graph_engineering.models import VerifierResult
from graph_engineering.models.graph import Node

from .lifecycle import VerifierRepository
from .types import VerifierProtocol, VerifierRequest


class RuntimeVerifierAdapter:
    def __init__(
        self,
        repository: VerifierRepository,
        implementations: dict[tuple[str, int], VerifierProtocol],
        *,
        working_directory: Path,
        artifact_directory: Path,
    ) -> None:
        self.repository = repository
        self.implementations = dict(implementations)
        self.working_directory = working_directory
        self.artifact_directory = artifact_directory
        self._handles: dict[str, tuple[str, int]] = {}

    def execute(
        self,
        run_id: str,
        node: Node,
        attempt_id: str,
        *,
        idempotency_key: str | None = None,
    ) -> VerifierResult:
        verifier_id = str(node.config.get("verifier_id", node.node_id))
        revision = int(node.config.get("verifier_revision", 1))
        self.repository.verify_frozen(verifier_id, revision)
        implementation = self._implementation(verifier_id, revision)
        outcome = implementation.execute(
            VerifierRequest(
                run_id=run_id,
                node_id=node.node_id,
                attempt_id=attempt_id,
                working_directory=self.working_directory,
                artifact_directory=self.artifact_directory,
                idempotency_key=idempotency_key,
                payload=dict(node.config),
            )
        )
        if outcome.result.external_handle:
            self._handles[outcome.result.external_handle] = (verifier_id, revision)
        return outcome.result

    def query(self, handle: str) -> VerifierResult:
        verifier_id, revision = self._handle_owner(handle)
        return self.query_for(verifier_id, revision, handle)

    def query_for(self, verifier_id: str, revision: int, handle: str) -> VerifierResult:
        self.repository.verify_frozen(verifier_id, revision)
        return self._implementation(verifier_id, revision).poll(handle).result

    def cancel(self, handle: str) -> VerifierResult:
        verifier_id, revision = self._handle_owner(handle)
        return self.cancel_for(verifier_id, revision, handle)

    def cancel_for(self, verifier_id: str, revision: int, handle: str) -> VerifierResult:
        return self._implementation(verifier_id, revision).cancel(handle).result

    def _handle_owner(self, handle: str) -> tuple[str, int]:
        owner = self._handles.get(handle)
        if owner is not None:
            return owner
        external = [key for key, value in self.implementations.items() if hasattr(value, "poll")]
        if len(external) != 1:
            raise RuntimeError("cannot identify the external Verifier owner after recovery")
        self._handles[handle] = external[0]
        return external[0]

    def _implementation(self, verifier_id: str, revision: int) -> VerifierProtocol:
        try:
            return self.implementations[(verifier_id, revision)]
        except KeyError as exc:
            raise RuntimeError(
                f"Verifier implementation is unavailable: {verifier_id} r{revision}"
            ) from exc
