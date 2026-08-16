from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from graph_engineering.cli import app

runner = CliRunner()
FIXTURES = Path(__file__).parent / "fixtures"


def test_cli_accepts_valid_graph() -> None:
    result = runner.invoke(app, ["graph", "validate", str(FIXTURES / "valid/graph.yaml")])
    assert result.exit_code == 0
    assert "Valid Execution Graph" in result.stdout


def test_cli_rejects_invalid_graph_with_field_paths() -> None:
    result = runner.invoke(app, ["graph", "validate", str(FIXTURES / "invalid/graph.yaml")])
    assert result.exit_code == 2
    output = result.output
    assert "nodes[0].node_type" in output
    assert "edges[0].condition" in output


def test_cli_rejects_malformed_document(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{not json", encoding="utf-8")
    result = runner.invoke(app, ["graph", "validate", str(path)])
    assert result.exit_code == 2
    assert "document: invalid JSON/YAML" in result.output


def test_cli_exports_schemas(tmp_path: Path) -> None:
    output = tmp_path / "schema-output"
    result = runner.invoke(app, ["schema", "export", "--output", str(output)])
    assert result.exit_code == 0
    assert list(output.glob("*.schema.json"))
