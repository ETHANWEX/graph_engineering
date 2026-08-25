"""Escaped semantic HTML rendering; untrusted Markdown remains inert text."""

# ruff: noqa: E501

from __future__ import annotations

import html
import json
from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import quote


def _text(value: object) -> str:
    if value is None:
        return "Not available"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (Mapping, Sequence)) and not isinstance(value, (str, bytes, bytearray)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def _escaped(value: object) -> str:
    return html.escape(_text(value), quote=True)


def _section(title: str, value: object, section_id: str) -> str:
    return (
        f'<section aria-labelledby="{section_id}-title">'
        f'<h2 id="{section_id}-title">{html.escape(title)}</h2>'
        f'<pre class="facts" tabindex="0">{_escaped(value)}</pre></section>'
    )


def _hidden(name: str, value: object) -> str:
    return f'<input type="hidden" name="{html.escape(name)}" value="{_escaped(value)}">'


def _conversation_id(
    snapshot: Mapping[str, Any], selected_run_id: str | None, actor_id: str
) -> str | None:
    conversation = snapshot.get("conversation")
    if not isinstance(conversation, Mapping):
        return None
    direct = conversation.get("conversation_id")
    if isinstance(direct, str):
        return direct
    rows = conversation.get("conversations")
    if not isinstance(rows, list):
        return None
    for row in reversed(rows):
        if (
            isinstance(row, Mapping)
            and row.get("actor_id") == actor_id
            and row.get("status") == "active"
            and (selected_run_id is None or row.get("active_run_id") in {None, selected_run_id})
            and isinstance(row.get("conversation_id"), str)
        ):
            return str(row["conversation_id"])
    return None


def _control_forms(snapshot: Mapping[str, Any], run_id: str, actor_id: str, session_id: str) -> str:
    conversation_id = _conversation_id(snapshot, run_id, actor_id)
    if conversation_id is None or run_id == "none":
        return (
            '<section aria-labelledby="controls-title"><h2 id="controls-title">Human controls</h2>'
            '<p role="status">No active Human Gateway conversation is available.</p></section>'
        )
    common = _hidden("conversation_id", conversation_id) + _hidden("run_id", run_id)
    message = (
        '<form data-ge-form="message" data-endpoint="/api/v1/messages">'
        '<label for="human-message">Human message</label>'
        '<textarea id="human-message" name="content" maxlength="65536" required></textarea>'
        f'{common}<button type="submit">Submit through Human Gateway</button></form>'
    )
    action = (
        f'<form data-ge-form="action" data-run-id="{_escaped(run_id)}">'
        '<label for="control-action">Structured action</label><select id="control-action" name="action">'
        + "".join(
            f'<option value="{name}">{name}</option>'
            for name in ("pause", "resume", "interrupt", "cancel", "accept", "reject", "revise")
        )
        + '</select><label for="control-reason">Message or reason</label>'
        '<textarea id="control-reason" name="content" maxlength="65536" required></textarea>'
        f'{common}<button type="submit">Request action</button></form>'
    )
    source = snapshot.get("source")
    snapshot_id = source.get("snapshot_id") if isinstance(source, Mapping) else None
    confirmations: list[str] = []
    cards = snapshot.get("pending_confirmations")
    if isinstance(cards, list):
        fields = (
            "pending_action_id",
            "conversation_id",
            "project_id",
            "actor_id",
            "source_message_id",
            "intent_id",
            "action",
            "run_id",
            "contract_id",
            "contract_revision",
            "contract_hash",
            "created_at",
            "expires_at",
        )
        for index, card in enumerate(cards):
            if not isinstance(card, Mapping) or card.get("status") != "pending":
                continue
            pending_id = card.get("pending_action_id")
            if not isinstance(pending_id, str):
                continue
            hidden = "".join(_hidden(name, card.get(name)) for name in fields)
            hidden += _hidden("session_id", session_id) + _hidden("snapshot_id", snapshot_id)
            confirmations.append(
                '<form data-ge-form="confirmation" '
                f'data-endpoint="/api/v1/confirmations/{quote(pending_id, safe="")}">'
                f"<h3>Confirm {_escaped(card.get('action'))} for {_escaped(card.get('run_id'))}</h3>"
                f'<label for="confirmation-{index}">Confirmation message</label>'
                f'<textarea id="confirmation-{index}" name="content" maxlength="65536" required></textarea>'
                f'{hidden}<button type="submit">Confirm persisted action</button></form>'
            )
    return (
        '<section aria-labelledby="controls-title"><h2 id="controls-title">Human controls</h2>'
        + message
        + action
        + "".join(confirmations)
        + "</section>"
    )


def render_page(
    snapshot: Mapping[str, Any],
    *,
    selected_run_id: str | None = None,
    actor_id: str = "human",
    session_id: str = "ui-session",
) -> bytes:
    runs = snapshot.get("runs")
    run_values = runs if isinstance(runs, list) else []
    selected = next(
        (
            item
            for item in run_values
            if isinstance(item, dict)
            and (selected_run_id is None or item.get("run_id") == selected_run_id)
        ),
        {},
    )
    run_id = selected.get("run_id", "none") if isinstance(selected, dict) else "none"
    run_sections = "".join(
        (
            _section("Contract", selected.get("contract"), "contract"),
            _section(
                "Requirement Matrix", selected.get("requirement_matrix"), "requirement-matrix"
            ),
            _section("Verifier and CI", selected.get("verifiers"), "verifier"),
            _section("Review", selected.get("review"), "review"),
            _section("Final Report", selected.get("report"), "report"),
            _section("Artifacts", selected.get("artifacts"), "artifacts"),
            _section(
                "Nodes and attempts",
                {
                    "nodes": selected.get("nodes"),
                    "attempts": selected.get("attempts"),
                    "parallel_branches": selected.get("parallel_branches"),
                    "sessions": selected.get("sessions"),
                },
                "execution",
            ),
            _section(
                "Risks and budget",
                {"risks": selected.get("risks"), "budget": selected.get("budget")},
                "risk-budget",
            ),
            _section("GitHub delivery (read-only)", selected.get("github"), "github"),
        )
    )
    pending = snapshot.get("pending_confirmations") or []
    confirmation = (
        '<aside class="confirmation" aria-labelledby="confirmation-title">'
        '<h2 id="confirmation-title">Confirmation required</h2>'
        f'<pre tabindex="0">{_escaped(pending)}</pre></aside>'
    )
    controls = _control_forms(snapshot, str(run_id), actor_id, session_id)
    source = snapshot.get("source")
    snapshot_id = source.get("snapshot_id", "unknown") if isinstance(source, Mapping) else "unknown"
    instance_id = source.get("instance_id", "unknown") if isinstance(source, Mapping) else "unknown"
    stale_after = source.get("stale_after_seconds", 10) if isinstance(source, Mapping) else 10
    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Graph Engineering Project UI</title><link rel="stylesheet" href="/assets/ui.css">
<script src="/assets/ui.js" defer></script></head>
<body><a class="skip" href="#main">Skip to main content</a>
<header><h1>Project overview</h1><p id="connection-status" aria-live="polite" role="status">Authoritative snapshot loaded.</p></header>
<main id="main" tabindex="-1" data-snapshot-id="{_escaped(snapshot_id)}" data-instance-id="{_escaped(instance_id)}" data-stale-after="{_escaped(stale_after)}"><section aria-labelledby="runs-title"><h2 id="runs-title">Run list</h2>
<pre class="facts" tabindex="0">{_escaped(run_values)}</pre></section>
<section aria-labelledby="run-title"><h2 id="run-title">Run {_escaped(run_id)}</h2>{run_sections}</section>
{confirmation}<section aria-labelledby="conversation-title"><h2 id="conversation-title">Human Control Conversation</h2>
<pre class="facts" tabindex="0">{_escaped(snapshot.get("conversation"))}</pre>
{controls}</section></main>
<footer><p>Statuses use text and symbols, never color alone. UI state is non-authoritative.</p></footer>
</body></html>"""
    return document.encode("utf-8")
