"""Append-only canonical JSONL event sink."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from .store import StateStore


class EventStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._flush_lock = threading.Lock()

    def _existing_ids(self) -> set[str]:
        if not self.path.exists():
            return set()
        ids: set[str] = set()
        with self.path.open(encoding="utf-8") as stream:
            for line in stream:
                if line.strip():
                    value = json.loads(line)
                    event_id = value.get("event_id")
                    if isinstance(event_id, str):
                        ids.add(event_id)
        return ids

    def flush(self, state: StateStore) -> int:
        with self._flush_lock:
            return self._flush_locked(state)

    def _flush_locked(self, state: StateStore) -> int:
        existing = self._existing_ids()
        delivered = 0
        for row in state.outbox_rows():
            event_id = str(row["event_id"])
            if event_id not in existing:
                with self.path.open("a", encoding="utf-8", newline="\n") as stream:
                    stream.write(str(row["event_json"]))
                    stream.write("\n")
                    stream.flush()
                    os.fsync(stream.fileno())
                existing.add(event_id)
            state.mark_event_delivered(event_id)
            delivered += 1
        return delivered
