"""Deterministic declaration-first Verifier planning."""

from __future__ import annotations

from dataclasses import dataclass

from graph_engineering.verifier import (
    HttpPipelineSpec,
    HttpRequestSpec,
    HttpStatusMapping,
)


@dataclass(frozen=True)
class VerifierDiscoveryDecision:
    declarative: bool
    reason: str
    http_pipeline: HttpPipelineSpec | None = None


def plan_http_pipeline(
    *,
    trigger_url: str | None,
    poll_url: str | None,
    external_id_path: str | None,
    status_path: str | None,
    pending: tuple[str, ...] = ("pending", "queued", "running"),
    passed: tuple[str, ...] = ("passed", "succeeded", "success"),
    failed: tuple[str, ...] = ("failed", "failure"),
) -> VerifierDiscoveryDecision:
    missing = [
        name
        for name, value in (
            ("trigger URL", trigger_url),
            ("poll URL", poll_url),
            ("external ID JSON path", external_id_path),
            ("status JSON path", status_path),
        )
        if not value
    ]
    if missing:
        return VerifierDiscoveryDecision(
            False,
            "declarative HTTP is insufficient because these fields are missing: "
            + ", ".join(missing),
        )
    return VerifierDiscoveryDecision(
        True,
        "declarative HTTP pipeline fully expresses trigger, poll, and status mapping",
        HttpPipelineSpec(
            trigger=HttpRequestSpec(method="POST", url=trigger_url or ""),
            external_id_path=external_id_path or "",
            poll=HttpRequestSpec(url=poll_url or ""),
            statuses=HttpStatusMapping(
                json_path=status_path or "", pending=pending, passed=passed, failed=failed
            ),
        ),
    )
