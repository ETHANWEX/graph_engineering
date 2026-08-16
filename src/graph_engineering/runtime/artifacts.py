"""Minimal content-addressed append-only Artifact Store."""

from __future__ import annotations

import hashlib
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

from graph_engineering.models.common import Artifact, ArtifactKind


class ArtifactStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def put_bytes(
        self,
        content: bytes,
        *,
        media_type: str | None = None,
        kind: ArtifactKind = ArtifactKind.EVIDENCE,
    ) -> Artifact:
        digest = hashlib.sha256(content).hexdigest()
        relative = Path("sha256") / digest[:2] / digest
        target = self.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if target.read_bytes() != content:
                raise RuntimeError("artifact digest collision")
        else:
            temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
            with temporary.open("xb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
        created_at = datetime.fromtimestamp(target.stat().st_mtime_ns / 1_000_000_000, UTC)
        return Artifact(
            schema_version="1.0",
            artifact_id=f"sha256:{digest}",
            kind=kind,
            uri=relative.as_posix(),
            sha256_digest=digest,
            media_type=media_type,
            size_bytes=len(content),
            created_at=created_at,
        )

    def read_bytes(self, uri: str) -> bytes:
        path = (self.root / Path(uri)).resolve()
        root = self.root.resolve()
        if path != root and root not in path.parents:
            raise ValueError("artifact URI escapes the store")
        return path.read_bytes()
