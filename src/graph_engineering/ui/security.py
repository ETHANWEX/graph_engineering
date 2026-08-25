"""Output secret rejection shared by HTML and JSON UI responses."""

from __future__ import annotations

import base64
from urllib.parse import quote


class SecretLeakError(ValueError):
    pass


class StreamingSecretGuard:
    def __init__(self, secret_values: tuple[str, ...] = ()) -> None:
        variants: set[bytes] = set()
        for secret in secret_values:
            if not secret:
                continue
            raw = secret.encode("utf-8")
            variants.update(
                {
                    raw,
                    quote(secret, safe="").encode("ascii"),
                    base64.b64encode(raw),
                }
            )
        self._variants = tuple(sorted(variants, key=len, reverse=True))
        self._tail = b""
        self._tail_size = max((len(item) for item in self._variants), default=1) - 1

    def check_text(self, value: str) -> None:
        self._reject(value.encode("utf-8"))

    def check_chunk(self, value: bytes) -> None:
        combined = self._tail + value
        self._reject(combined)
        self._tail = combined[-self._tail_size :] if self._tail_size else b""

    def reset(self) -> None:
        self._tail = b""

    def _reject(self, value: bytes) -> None:
        if any(item in value for item in self._variants):
            raise SecretLeakError("UI response contained a configured secret variant")
