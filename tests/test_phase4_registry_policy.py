from __future__ import annotations

import base64
from pathlib import Path
from urllib.parse import quote

import pytest
from pydantic import ValidationError

from graph_engineering.verifier import (
    CapabilityPolicy,
    CapabilityViolation,
    DuplicateVerifierType,
    FilesystemCapabilities,
    NetworkCapabilities,
    SecretRedactor,
    UnknownVerifierType,
    VerifierCapabilities,
    VerifierManifest,
    VerifierRegistry,
    builtin_registry,
)


def manifest(**updates: object) -> VerifierManifest:
    data: dict[str, object] = {
        "verifier_id": "company-ci",
        "revision": 1,
        "verifier_type": "builtin/http-pipeline",
        "runtime": "http",
        "capabilities": {"network": {"allow": ["ci.example.test"]}},
        "external_side_effects": True,
    }
    data.update(updates)
    return VerifierManifest.model_validate(data)


def test_registry_registers_builtins_and_rejects_duplicates_and_unknowns() -> None:
    assert builtin_registry().types() == (
        "builtin/command",
        "builtin/http-pipeline",
        "project/subprocess",
    )
    registry = VerifierRegistry()
    registry.register("custom", lambda: object())
    with pytest.raises(DuplicateVerifierType):
        registry.register("custom", lambda: object())
    with pytest.raises(UnknownVerifierType):
        registry.create("missing")


def test_manifest_rejects_wildcards_secret_values_and_missing_entrypoint() -> None:
    with pytest.raises(ValidationError):
        manifest(capabilities={"network": {"allow": ["*.example.test"]}})
    with pytest.raises(ValidationError):
        manifest(capabilities={"secrets": ["token=actual-value"]})
    with pytest.raises(ValidationError):
        manifest(verifier_type="project/subprocess", runtime="python", entrypoint=[])


def test_network_is_default_deny_and_hosts_are_exact() -> None:
    denied = manifest(capabilities={})
    with pytest.raises(CapabilityViolation):
        CapabilityPolicy.require_url(denied, "https://ci.example.test/runs")
    allowed = manifest()
    CapabilityPolicy.require_url(allowed, "https://ci.example.test/runs")
    with pytest.raises(CapabilityViolation):
        CapabilityPolicy.require_url(allowed, "https://evil.ci.example.test/runs")


def test_filesystem_capabilities_remain_under_declared_roots(tmp_path: Path) -> None:
    item = manifest(
        capabilities=VerifierCapabilities(
            filesystem=FilesystemCapabilities(read=("repo",), write=("artifacts",)),
            network=NetworkCapabilities(),
        )
    )
    CapabilityPolicy.require_path(
        item, tmp_path / "repo" / "file.txt", writable=False, roots=(tmp_path,)
    )
    with pytest.raises(CapabilityViolation):
        CapabilityPolicy.require_path(
            item, tmp_path / "outside.txt", writable=False, roots=(tmp_path,)
        )


def test_secret_redaction_handles_overlaps_encodings_and_chunk_boundaries() -> None:
    short = "token"
    long = "token-very-secret"
    redactor = SecretRedactor([short, long])
    encoded = quote(long, safe="")
    b64 = base64.b64encode(long.encode()).decode()
    value = redactor.redact(f"{long}|{short}|{encoded}|{b64}")
    assert short not in value and long not in value and encoded not in value and b64 not in value
    stream = redactor.stream()
    assert stream.feed("prefix token-very-") == ""
    result = stream.feed("secret suffix", final=True)
    assert long not in result and "[REDACTED]" in result
