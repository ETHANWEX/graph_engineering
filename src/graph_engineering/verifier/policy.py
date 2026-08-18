"""Capability checks, secret resolution, and persistence-safe redaction."""

from __future__ import annotations

import base64
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import quote, urlsplit

from .types import VerifierManifest


class CapabilityViolation(RuntimeError):
    pass


class SecretResolutionError(RuntimeError):
    pass


class CapabilityPolicy:
    @staticmethod
    def require_url(manifest: VerifierManifest, url: str) -> None:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower().rstrip(".")
        if parsed.scheme not in {"http", "https"} or not host:
            raise CapabilityViolation("HTTP verifier URL must use http or https")
        if host not in manifest.capabilities.network.allow:
            raise CapabilityViolation(f"network host is not allowlisted: {host}")

    @staticmethod
    def require_path(
        manifest: VerifierManifest, path: Path, *, writable: bool, roots: tuple[Path, ...]
    ) -> Path:
        resolved = path.resolve()
        declared = (
            manifest.capabilities.filesystem.write
            if writable
            else manifest.capabilities.filesystem.read
        )
        allowed: list[Path] = []
        for item in declared:
            candidate = Path(item)
            if not candidate.is_absolute():
                for root in roots:
                    allowed.append((root / candidate).resolve())
            else:
                allowed.append(candidate.resolve())
        if not any(resolved == root or root in resolved.parents for root in allowed):
            mode = "write" if writable else "read"
            raise CapabilityViolation(f"filesystem {mode} path is outside declared capability")
        return resolved


class SecretResolver:
    def __init__(self, values: Mapping[str, str]) -> None:
        self._values = dict(values)

    def resolve(self, manifest: VerifierManifest) -> dict[str, str]:
        resolved: dict[str, str] = {}
        for reference in manifest.capabilities.secrets:
            try:
                resolved[reference] = self._values[reference]
            except KeyError as exc:
                raise SecretResolutionError(
                    f"declared secret reference is unavailable: {reference}"
                ) from exc
        return resolved


class SecretRedactor:
    marker = "[REDACTED]"

    def __init__(self, secrets: Mapping[str, str] | tuple[str, ...] | list[str]) -> None:
        values = secrets.values() if isinstance(secrets, Mapping) else secrets
        variants: set[str] = set()
        for value in values:
            if not value:
                continue
            variants.update(
                {
                    value,
                    quote(value, safe=""),
                    base64.b64encode(value.encode("utf-8")).decode("ascii"),
                    base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii"),
                }
            )
        self._variants = tuple(sorted(variants, key=len, reverse=True))

    def redact(self, value: str) -> str:
        for secret in self._variants:
            value = value.replace(secret, self.marker)
        return value

    def redact_bytes(self, value: bytes) -> bytes:
        return self.redact(value.decode("utf-8", errors="replace")).encode("utf-8")

    def stream(self) -> StreamingSecretRedactor:
        return StreamingSecretRedactor(self)


class StreamingSecretRedactor:
    def __init__(self, redactor: SecretRedactor) -> None:
        self.redactor = redactor
        self._carry = ""
        self._window = max((len(item) for item in redactor._variants), default=1)

    def feed(self, chunk: str, *, final: bool = False) -> str:
        self._carry += chunk
        if not final:
            return ""
        combined, self._carry = self._carry, ""
        return self.redactor.redact(combined)
