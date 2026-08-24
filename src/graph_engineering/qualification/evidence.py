"""Local evidence collection and append-only document storage."""

from __future__ import annotations

import base64
import json
import os
import platform
import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

from graph_engineering import __version__
from graph_engineering.service.protocol import IPC_VERSION, MCP_TOOLS_VERSION, RUNTIME_API_VERSION

from .models import (
    AuthenticationState,
    CleanupState,
    EvidenceClassification,
    EvidenceCounts,
    EvidenceResult,
    GitIdentity,
    HostIdentity,
    ProductVersions,
    QualificationClaim,
    QualificationEvidence,
    ToolIdentity,
)

_PROHIBITED_KEYS = ("token", "cookie", "password", "authorization", "credential", "secret")


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        result: list[str] = []
        for key, item in value.items():
            if any(part in str(key).casefold() for part in _PROHIBITED_KEYS):
                raise ValueError("secret-bearing evidence key is prohibited")
            result.extend(_strings(item))
        return result
    if isinstance(value, (list, tuple)):
        return [text for item in value for text in _strings(item)]
    return []


def assert_secret_safe(document: object, *, secret_values: tuple[str, ...] = ()) -> None:
    """Reject secret-bearing keys and configured raw/encoded/cross-chunk values."""

    strings = _strings(document)
    joined = "".join(strings)
    haystacks = [item.casefold() for item in strings] + [joined.casefold()]
    for value in secret_values:
        if not value:
            continue
        variants = {
            value,
            quote(value, safe=""),
            base64.b64encode(value.encode("utf-8")).decode("ascii"),
        }
        if any(variant.casefold() in haystack for variant in variants for haystack in haystacks):
            raise ValueError("secret value detected in qualification evidence")


def _run(root: Path, argv: list[str]) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            argv,
            cwd=root,
            check=False,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            shell=False,
            timeout=10,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return None


def _first_line(result: subprocess.CompletedProcess[str] | None) -> str | None:
    if result is None or result.returncode != 0:
        return None
    text = result.stdout.strip() or result.stderr.strip()
    return text.splitlines()[0] if text else None


def _tool(root: Path, name: str, argv: list[str]) -> ToolIdentity:
    result = _run(root, argv)
    return ToolIdentity(name=name, available=result is not None, version=_first_line(result))


def _git_identity(root: Path) -> GitIdentity:
    commit = _first_line(_run(root, ["git", "rev-parse", "HEAD"])) or "unavailable"
    branch = _first_line(_run(root, ["git", "branch", "--show-current"])) or "detached"
    status = _run(root, ["git", "status", "--porcelain", "--untracked-files=normal"])
    dirty = status is None or bool(status.stdout.strip())
    return GitIdentity(repository=str(root.resolve()), commit=commit, branch=branch, dirty=dirty)


def _codex(root: Path) -> ToolIdentity:
    version = _run(root, ["codex", "--version"])
    if version is None:
        return ToolIdentity(
            name="codex", available=False, authentication=AuthenticationState.UNAVAILABLE
        )
    auth = _run(root, ["codex", "login", "status"])
    auth_text = "" if auth is None else f"{auth.stdout}\n{auth.stderr}"
    authenticated = bool(auth and auth.returncode == 0 and "logged in" in auth_text.casefold())
    return ToolIdentity(
        name="codex",
        available=True,
        version=_first_line(version),
        authentication=(
            AuthenticationState.AUTHENTICATED
            if authenticated
            else AuthenticationState.UNAUTHENTICATED
        ),
    )


def _github(root: Path) -> ToolIdentity:
    version = _run(root, ["gh", "--version"])
    if version is None:
        return ToolIdentity(
            name="github-cli", available=False, authentication=AuthenticationState.UNAVAILABLE
        )
    auth = _run(root, ["gh", "auth", "status"])
    return ToolIdentity(
        name="github-cli",
        available=True,
        version=_first_line(version),
        authentication=(
            AuthenticationState.AUTHENTICATED
            if auth is not None and auth.returncode == 0
            else AuthenticationState.UNAUTHENTICATED
        ),
    )


def _blocked_claim(claim_id: str, claim: str, environment: str, reason: str) -> QualificationClaim:
    return QualificationClaim(
        claim_id=claim_id,
        product_claim=claim,
        required_environment=environment,
        evidence_classification=EvidenceClassification.BLOCKED,
        operation="not executed",
        result=EvidenceResult.BLOCKED,
        counts=EvidenceCounts(blocked=1),
        limitation=reason,
        cleanup=CleanupState.NOT_REQUIRED,
        recovery_guidance=(
            "Resolve the exact target and cleanup plan, then obtain Human authorization."
        ),
        conclusion="blocked",
    )


def _unverified_claim(
    claim_id: str, claim: str, environment: str, reason: str
) -> QualificationClaim:
    return QualificationClaim(
        claim_id=claim_id,
        product_claim=claim,
        required_environment=environment,
        evidence_classification=EvidenceClassification.UNVERIFIED,
        operation="not executed",
        result=EvidenceResult.UNVERIFIED,
        counts=EvidenceCounts(unverified=1),
        limitation=reason,
        cleanup=CleanupState.NOT_REQUIRED,
        recovery_guidance=(
            "Run the versioned qualification operation on the required real environment."
        ),
        conclusion="unverified",
    )


def collect_local_evidence(
    root: Path, *, external_authorized: bool = False
) -> QualificationEvidence:
    """Collect read-only local identity and an honest default release-claim matrix."""

    started = datetime.now(UTC)
    resolved = root.resolve()
    tools = (
        _tool(resolved, "git", ["git", "--version"]),
        _codex(resolved),
        _github(resolved),
        _tool(resolved, "docker", ["docker", "version", "--format", "{{.Client.Version}}"]),
        _tool(resolved, "podman", ["podman", "version", "--format", "{{.Client.Version}}"]),
    )
    claims = [
        _unverified_claim(
            "packaging-local",
            "wheel/sdist install and upgrade are reproducible on Python 3.12 and 3.13",
            "isolated local Python 3.12 and 3.13",
            "Identity collection does not execute the packaging qualification suite.",
        ),
        _unverified_claim(
            "windows-local",
            "Windows Service/IPC/worktree/subprocess/parallel/recovery boundaries are qualified",
            "real Windows host",
            "Identity collection alone is not supported-platform evidence.",
        ),
        _blocked_claim(
            "codex-plugin-real",
            "Codex loads the Plugin and routes MCP to the persistent Runtime",
            "Human-approved isolated CODEX_HOME and disposable Git repository",
            "Real Plugin installation/load and autonomous Codex execution are not authorized.",
        ),
        _blocked_claim(
            "github-real",
            "GitHub PR/Checks recovery and idempotency are qualified",
            "Human-approved exact disposable GitHub repository and identity",
            "No GitHub repository write scope or cleanup authority was granted.",
        ),
        _blocked_claim(
            "container-real",
            "Pinned-image container isolation and cleanup are qualified",
            "Human-approved existing Docker/Podman daemon and pinned local image",
            "Container execution is not authorized and no compatible runtime is available.",
        ),
        _unverified_claim(
            "linux-platform",
            "Linux is a supported release platform",
            "real approved Linux host or CI runner",
            "No Linux runner or execution authority is available.",
        ),
        _unverified_claim(
            "macos-platform",
            "macOS is a supported release platform",
            "real approved macOS host or CI runner",
            "No macOS runner or execution authority is available.",
        ),
    ]
    if external_authorized:
        raise ValueError("external authorization requires a scoped provider-specific runner")
    ended = datetime.now(UTC)
    counts = EvidenceCounts(
        collected=len(claims),
        blocked=sum(item.result is EvidenceResult.BLOCKED for item in claims),
        unverified=sum(item.result is EvidenceResult.UNVERIFIED for item in claims),
    )
    evidence = QualificationEvidence(
        run_id=f"qualification-{uuid.uuid4()}",
        started_at=started,
        ended_at=ended,
        duration_seconds=max(0.0, (ended - started).total_seconds()),
        versions=ProductVersions(
            product=__version__,
            package=__version__,
            plugin="0.1.0",
            runtime_api=RUNTIME_API_VERSION,
            ipc=IPC_VERSION,
            mcp=MCP_TOOLS_VERSION,
            migration_head=10,
            schema_count=36,
        ),
        git=_git_identity(resolved),
        host=HostIdentity(
            os=platform.system(),
            os_version=platform.version(),
            architecture=platform.machine(),
            shell=os.environ.get("COMSPEC", "unknown"),
            filesystem="Windows path semantics" if os.name == "nt" else "POSIX path semantics",
            python=platform.python_version(),
        ),
        tools=tools,
        claims=tuple(claims),
        counts=counts,
        cleanup=CleanupState.NOT_REQUIRED,
        limitations=("Identity collection is not an integration test.",),
        recovery_guidance=("Run focused qualification suites and attach immutable Artifacts.",),
    )
    assert_secret_safe(evidence.model_dump(mode="json"))
    return evidence


class QualificationRepository:
    """Append-only JSON evidence storage; reads never initialize Runtime state."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def write(self, evidence: QualificationEvidence) -> None:
        if self.path.exists():
            raise FileExistsError(f"qualification evidence already exists: {self.path}")
        document = evidence.model_dump(mode="json")
        assert_secret_safe(document)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.{uuid.uuid4().hex}.tmp")
        temporary.write_text(
            json.dumps(document, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.path)

    def read(self) -> QualificationEvidence:
        document: Any = json.loads(self.path.read_text(encoding="utf-8"))
        assert_secret_safe(document)
        return QualificationEvidence.model_validate(document)
