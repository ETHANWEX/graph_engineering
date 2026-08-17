"""Phase 0 command-line interface."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

import typer
import yaml
from pydantic import ValidationError

from .contracts import ContractRepository, RunPlanner
from .conversation import ConversationRepository, IntentCompiler
from .discovery import DiscoveryRepository, DiscoveryService, DiscoveryState
from .models import ExecutionGraph, HumanMessage
from .runtime import StateStore
from .schema import export_schemas

app = typer.Typer(help="Graph Engineering protocol tools.", no_args_is_help=True)
graph_app = typer.Typer(help="Static Execution Graph tools.", no_args_is_help=True)
schema_app = typer.Typer(help="JSON Schema tools.", no_args_is_help=True)
app.add_typer(graph_app, name="graph")
app.add_typer(schema_app, name="schema")


def _write_immutable(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_text(encoding="utf-8") != content:
            raise RuntimeError(
                f"immutable control artifact already exists with other content: {path}"
            )
        return
    path.write_text(content, encoding="utf-8")


def _human_message(
    content: str,
    *,
    actor_id: str,
    project_id: str,
    run_id: str | None,
) -> HumanMessage:
    return HumanMessage(
        schema_version="1.0",
        message_id=f"message:{uuid.uuid4()}",
        actor_id=actor_id,
        project_id=project_id,
        run_id=run_id,
        content=content,
        created_at=datetime.now(UTC),
    )


@app.command("start")
def start_conversation(
    project_root: Annotated[
        Path, typer.Option("--project-root", exists=True, file_okay=False, resolve_path=True)
    ] = Path("."),
    conversation_id: Annotated[str, typer.Option("--conversation-id")] = "project-main",
    project_id: Annotated[str, typer.Option("--project-id")] = "project",
    actor_id: Annotated[str, typer.Option("--actor-id")] = "human",
    message: Annotated[str | None, typer.Option("--message", "-m")] = None,
) -> None:
    """Start or resume the persistent Human Control Conversation."""

    root = project_root.resolve()
    control_root = root / ".ge" / "control"
    state = StateStore(control_root / "phase3.db")
    conversations = ConversationRepository(state)
    discovery_repository = DiscoveryRepository(state)
    discovery = DiscoveryService(discovery_repository)
    contracts = ContractRepository(state)
    planner = RunPlanner(state)
    try:
        conversation = conversations.get(conversation_id)
    except KeyError:
        conversation = conversations.create(conversation_id, project_id, actor_id)

    def process(content: str) -> bool:
        nonlocal conversation
        human = _human_message(
            content,
            actor_id=conversation.actor_id,
            project_id=conversation.project_id,
            run_id=conversation.active_run_id,
        )
        current = discovery_repository.latest_for_conversation(conversation_id)
        if (
            current is not None
            and current.state is DiscoveryState.AWAITING_CONFIRMATION
            and current.draft is not None
            and any(token in content.casefold() for token in ("confirm", "确认", "同意"))
        ):
            conversations.append(conversation_id, human)
            draft_id = contracts.stage(conversation_id, current.draft)
            frozen = contracts.freeze(draft_id, human)
            discovery.mark_frozen(current.session_id, frozen.contract)
            planned = planner.create(conversation.project_id, frozen)
            conversations.set_active_run(conversation_id, planned.run_id)
            conversation = conversations.get(conversation_id)
            contract_path = (
                control_root
                / "contracts"
                / (
                    f"{frozen.contract.contract_id.replace(':', '-')}-"
                    f"r{frozen.contract.revision}.json"
                )
            )
            graph_path = control_root / "graphs" / f"{planned.run_id.replace(':', '-')}.json"
            lock_path = (
                control_root
                / "acceptance"
                / f"{frozen.acceptance_lock.lock_id.replace(':', '-')}.json"
            )
            _write_immutable(contract_path, frozen.contract.canonical_json() + "\n")
            _write_immutable(graph_path, planned.graph.canonical_json() + "\n")
            _write_immutable(
                lock_path,
                json.dumps(
                    frozen.acceptance_lock.model_dump(mode="json"),
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
            )
            typer.echo(
                f"Contract r{frozen.contract.revision} frozen; acceptance lock created; "
                f"Execution Graph prepared as {planned.run_id}. "
                "Autonomous execution has not started."
            )
            return True
        if current is not None and current.state is DiscoveryState.AWAITING_ANSWERS:
            conversations.append(conversation_id, human)
            updated = discovery.answer(current.session_id, human)
            if updated.draft is None:
                typer.echo(discovery.next_question(updated.session_id))
            else:
                typer.echo("Contract draft is ready. Review summary:")
                typer.echo(updated.draft.canonical_json())
                typer.echo(
                    "Risk/permission summary: no undeclared network or secrets; "
                    "auto-merge is false. "
                    "Type 'confirm' to freeze, or provide a revision."
                )
            return False
        compiled = IntentCompiler().compile(human, active_run_id=conversation.active_run_id)
        if compiled.intent is not None:
            conversations.append(conversation_id, human)
            typer.echo(compiled.intent.canonical_json())
            if compiled.intent.requires_confirmation:
                typer.echo("This action requires explicit confirmation before Runtime mutation.")
            return False
        conversations.append(conversation_id, human)
        started = discovery.start(conversation_id, human, root)
        typer.echo(discovery.next_question(started.session_id))
        return False

    if message is not None:
        process(message)
        return
    typer.echo(f"Conversation {conversation_id} ready. Enter 'exit' to close the frontend.")
    while True:
        try:
            content = typer.prompt("Human")
        except (EOFError, KeyboardInterrupt):
            typer.echo()
            return
        if content.strip().casefold() in {"exit", "quit"}:
            return
        process(content)


def _load_document(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        return json.loads(text)
    return yaml.safe_load(text)


def _format_location(location: tuple[int | str, ...]) -> str:
    result = ""
    for part in location:
        if isinstance(part, int):
            result += f"[{part}]"
        else:
            result += ("." if result else "") + part
    return result or "document"


@graph_app.command("validate")
def validate_graph(
    file: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
) -> None:
    """Validate an Execution Graph without executing any node."""

    try:
        document = _load_document(file)
        ExecutionGraph.model_validate(document)
    except (json.JSONDecodeError, yaml.YAMLError) as exc:
        typer.echo(f"document: invalid JSON/YAML: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except OSError as exc:
        typer.echo(f"file: could not read input: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except ValidationError as exc:
        typer.echo(f"Invalid Execution Graph ({len(exc.errors())} error(s)):", err=True)
        for error in exc.errors(include_url=False):
            location = _format_location(error["loc"])
            typer.echo(f"- {location}: {error['msg']}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(f"Valid Execution Graph: {file}")


@schema_app.command("export")
def export_schema_command(
    output: Annotated[Path, typer.Option("--output", "-o", file_okay=False)] = Path("schemas"),
) -> None:
    """Export stable schemas for all public Phase 0 models."""

    paths = export_schemas(output)
    typer.echo(f"Exported {len(paths)} schemas to {output}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
