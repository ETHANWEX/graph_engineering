"""Hash locks for frozen control inputs used during recovery."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path


class FrozenInputMismatch(RuntimeError):
    pass


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True)
class FrozenInputs:
    contract: tuple[Path, str]
    graph: tuple[Path, str]
    verifiers: tuple[tuple[Path, str], ...]
    acceptance_lock: tuple[Path, str]

    @classmethod
    def capture(
        cls,
        contract: Path,
        graph: Path,
        verifiers: tuple[Path, ...],
        acceptance_lock: Path,
    ) -> FrozenInputs:
        return cls(
            (contract, _digest(contract)),
            (graph, _digest(graph)),
            tuple((path, _digest(path)) for path in sorted(verifiers)),
            (acceptance_lock, _digest(acceptance_lock)),
        )

    def verify(self) -> None:
        self._verify_one("contract", self.contract)
        self._verify_one("graph", self.graph)
        for verifier in self.verifiers:
            self._verify_one("verifier", verifier)
        self._verify_one("acceptance lock", self.acceptance_lock)

    @staticmethod
    def _verify_one(label: str, item: tuple[Path, str]) -> None:
        path, expected = item
        try:
            actual = _digest(path)
        except OSError as exc:
            raise FrozenInputMismatch(f"{label} is unavailable: {path}") from exc
        if actual != expected:
            raise FrozenInputMismatch(f"{label} hash mismatch: {path}")
