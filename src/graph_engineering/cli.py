"""Phase 0 command-line interface."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any

import typer
import yaml
from pydantic import ValidationError

from .models import ExecutionGraph
from .schema import export_schemas

app = typer.Typer(help="Graph Engineering protocol tools.", no_args_is_help=True)
graph_app = typer.Typer(help="Static Execution Graph tools.", no_args_is_help=True)
schema_app = typer.Typer(help="JSON Schema tools.", no_args_is_help=True)
app.add_typer(graph_app, name="graph")
app.add_typer(schema_app, name="schema")


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
