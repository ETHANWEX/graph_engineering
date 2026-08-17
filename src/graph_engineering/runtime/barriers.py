"""Reusable persisted barrier guard for Phase 2-3 side-effect boundaries."""

from __future__ import annotations

from .store import StateStore


class PersistedBarrierGuard:
    def __init__(self, state: StateStore, run_id: str) -> None:
        self.state = state
        self.run_id = run_id

    def is_open(self) -> bool:
        with self.state.read_connection() as connection:
            row = connection.execute(
                "SELECT status, barrier FROM runs WHERE run_id = ?", (self.run_id,)
            ).fetchone()
        return row is not None and str(row["status"]) == "running" and row["barrier"] is None

    def require_open(self, effect: str) -> None:
        if not self.is_open():
            raise RuntimeError(f"persisted Run barrier forbids {effect}")
