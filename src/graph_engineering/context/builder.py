"""Bounded Context Package construction with immutable high-priority sections."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ContextInput:
    node_responsibility: str
    contract: str
    global_policy: str
    git_status: str
    upstream_handoff: str
    failure_evidence: str
    file_refs: tuple[str, ...]
    artifact_refs: tuple[str, ...]
    output_schema: str


@dataclass(frozen=True)
class ContextPackage:
    rendered: str
    file_refs: tuple[str, ...]
    artifact_refs: tuple[str, ...]
    truncated_sections: tuple[str, ...]


class ContextBuilder:
    def __init__(self, *, max_bytes: int = 64 * 1024) -> None:
        if max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        self.max_bytes = max_bytes

    def build(self, source: ContextInput) -> ContextPackage:
        files = tuple(sorted(set(source.file_refs)))
        artifacts = tuple(sorted(set(source.artifact_refs)))
        required = self._render(
            (
                ("NODE RESPONSIBILITY", source.node_responsibility),
                ("IMMUTABLE CONTRACT", source.contract),
                ("GLOBAL POLICY", source.global_policy),
                ("OUTPUT SCHEMA", source.output_schema),
            )
        )
        if len(required.encode("utf-8")) > self.max_bytes:
            raise ValueError("immutable context exceeds size limit")
        optional = [
            ("GIT STATUS", source.git_status),
            ("UPSTREAM HANDOFF", source.upstream_handoff),
            ("FAILURE EVIDENCE", source.failure_evidence),
            ("FILE REFERENCES", "\n".join(files)),
            ("ARTIFACT REFERENCES", "\n".join(artifacts)),
        ]
        rendered = required
        truncated: list[str] = []
        for title, content in optional:
            if not content:
                continue
            candidate = rendered + self._render(((title, content),))
            if len(candidate.encode("utf-8")) <= self.max_bytes:
                rendered = candidate
                continue
            remaining = self.max_bytes - len(rendered.encode("utf-8"))
            prefix = f"\n## {title}\n"
            room = remaining - len(prefix.encode("utf-8"))
            if room > 24:
                rendered += prefix + self._truncate_utf8(content, room)
            truncated.append(title.lower().replace(" ", "_"))
        return ContextPackage(rendered, files, artifacts, tuple(truncated))

    @staticmethod
    def _render(sections: tuple[tuple[str, str], ...]) -> str:
        return "".join(f"\n## {title}\n{content.strip()}\n" for title, content in sections)

    @staticmethod
    def _truncate_utf8(value: str, max_bytes: int) -> str:
        suffix = "\n[truncated]"
        allowance = max(0, max_bytes - len(suffix.encode("utf-8")))
        encoded = value.encode("utf-8")[:allowance]
        while encoded:
            try:
                return encoded.decode("utf-8") + suffix
            except UnicodeDecodeError:
                encoded = encoded[:-1]
        return suffix[-max_bytes:]
