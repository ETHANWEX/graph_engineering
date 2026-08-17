"""Exact-name Verifier registry."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


class DuplicateVerifierType(ValueError):
    pass


class UnknownVerifierType(KeyError):
    pass


VerifierFactory = Callable[..., Any]


class VerifierRegistry:
    def __init__(self) -> None:
        self._factories: dict[str, VerifierFactory] = {}

    def register(self, verifier_type: str, factory: VerifierFactory) -> None:
        if not verifier_type or verifier_type in self._factories:
            raise DuplicateVerifierType(verifier_type)
        self._factories[verifier_type] = factory

    def create(self, verifier_type: str, **kwargs: object) -> Any:
        try:
            factory = self._factories[verifier_type]
        except KeyError as exc:
            raise UnknownVerifierType(verifier_type) from exc
        return factory(**kwargs)

    def types(self) -> tuple[str, ...]:
        return tuple(sorted(self._factories))

    def metadata(self) -> dict[str, tuple[str, ...]]:
        return {name: () for name in self.types()}


def builtin_registry() -> VerifierRegistry:
    from .command import CommandVerifier
    from .http_pipeline import HttpPipelineVerifier
    from .subprocess import SubprocessVerifier

    registry = VerifierRegistry()
    registry.register("builtin/command", CommandVerifier)
    registry.register("builtin/http-pipeline", HttpPipelineVerifier)
    registry.register("project/subprocess", SubprocessVerifier)
    return registry
